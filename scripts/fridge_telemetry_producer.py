from __future__ import annotations

import csv
import json
import os
import random
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from azure.eventhub import EventHubProducerClient, EventData
from azure.identity import DefaultAzureCredential

load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"))

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FRIDGE_CSV = DATA_DIR / "fridges_freezers.csv"

EVENT_HUB_FULLY_QUALIFIED_NAMESPACE = os.environ.get("EVENT_HUB_FULLY_QUALIFIED_NAMESPACE", "").strip()
EH_NAME_FRIDGE = os.environ.get("EH_NAME_FRIDGE", "kw-fridge-telemetry").strip()
if not EVENT_HUB_FULLY_QUALIFIED_NAMESPACE:
    sys.exit("Set EVENT_HUB_FULLY_QUALIFIED_NAMESPACE in scripts/.env or the environment.")
if not EH_NAME_FRIDGE:
    sys.exit("EH_NAME_FRIDGE must not be empty. Set it in scripts/.env or the environment.")

INTERVAL=300        # default 300 (5 min)
SPEEDUP=1                   # >1 to accelerate for demos (e.g. 60 = 1s per fridge cycle)

# Authenticate using the caller's Entra ID security principal.
# DefaultAzureCredential walks through az CLI, VS Code, managed identity,
# environment variables, etc., and uses the first one that works.
credential = DefaultAzureCredential()

# ---------------------------------------------------------------------------
# Load fridges
# ---------------------------------------------------------------------------

with FRIDGE_CSV.open(newline="", encoding="utf-8") as f:
    fridges = list(csv.DictReader(f))
print(f"Loaded {len(fridges):,} fridges/freezers from {FRIDGE_CSV.name}")

# Per-unit state so temps drift coherently rather than purely random
state: dict[str, dict] = {}
for fr in fridges:
    min_t = float(fr["min_safe_temp_c"])
    max_t = float(fr["max_safe_temp_c"])
    state[fr["fridge_id"]] = {
        "temp": (min_t + max_t) / 2,
        "humidity": 60.0 if fr["unit_type"] == "fridge" else 35.0,
        "door_open_cycles_left": 0,
        "excursion_cycles_left": 0,
    }

# ---------------------------------------------------------------------------
# Producer loop
# ---------------------------------------------------------------------------

producer = EventHubProducerClient(
    fully_qualified_namespace=EVENT_HUB_FULLY_QUALIFIED_NAMESPACE,
    eventhub_name=EH_NAME_FRIDGE,
    credential=credential,
)

stop = False
def _sigterm(*_):
    global stop
    stop = True
    print("\nShutdown requested...")
signal.signal(signal.SIGINT, _sigterm)
signal.signal(signal.SIGTERM, _sigterm)


def build_event(fr: dict) -> dict:
    fid = fr["fridge_id"]
    st = state[fid]
    min_t = float(fr["min_safe_temp_c"])
    max_t = float(fr["max_safe_temp_c"])
    target = (min_t + max_t) / 2

    # Random door open (~3% of cycles, lasting 1-3 cycles)
    if st["door_open_cycles_left"] == 0 and random.random() < 0.03:
        st["door_open_cycles_left"] = random.randint(1, 3)
    door_open = st["door_open_cycles_left"] > 0
    if door_open:
        st["door_open_cycles_left"] -= 1

    # Rare sustained excursion (~0.5% trigger, lasts 6-15 cycles -> 30-75 min)
    if st["excursion_cycles_left"] == 0 and random.random() < 0.005:
        st["excursion_cycles_left"] = random.randint(6, 15)
    excursion = st["excursion_cycles_left"] > 0
    if excursion:
        st["excursion_cycles_left"] -= 1

    # Temperature drift toward target unless door open / excursion
    drift = (target - st["temp"]) * 0.25 + random.uniform(-0.4, 0.4)
    if door_open:
        drift += random.uniform(1.0, 2.5)
    if excursion:
        drift += random.uniform(0.6, 1.4)
    st["temp"] = round(st["temp"] + drift, 2)

    # Humidity drifts mildly, spikes on door open
    h_drift = random.uniform(-1.5, 1.5) + (8.0 if door_open else 0.0)
    st["humidity"] = round(max(10.0, min(95.0, st["humidity"] + h_drift)), 1)

    return {
        "telemetry_type": "fridge",
        "event_time": datetime.now(timezone.utc).isoformat(),
        "store_id": fr["store_id"],
        "fridge_id": fid,
        "unit_type": fr["unit_type"],
        "code_name": fr["code_name"],
        "model": fr["model"],
        "temperature_c": st["temp"],
        "humidity_pct": st["humidity"],
        "door_open": door_open,
        "min_safe_temp_c": min_t,
        "max_safe_temp_c": max_t,
    }


def send_batch():
    batch = producer.create_batch()
    for fr in fridges:
        ev = build_event(fr)
        data = EventData(json.dumps(ev))
        try:
            batch.add(data)
        except ValueError:
            # full -> flush and start new
            producer.send_batch(batch)
            batch = producer.create_batch()
            batch.add(data)
    if len(batch) > 0:
        producer.send_batch(batch)


print(f"Producing fridge telemetry every {INTERVAL//SPEEDUP}s (speedup={SPEEDUP})")
try:
    while not stop:
        t0 = time.time()
        send_batch()
        elapsed = time.time() - t0
        print(f"[{datetime.now().isoformat(timespec='seconds')}] sent {len(fridges)} events in {elapsed:.1f}s")
        sleep_for = max(0, (INTERVAL // SPEEDUP) - elapsed)
        for _ in range(int(sleep_for)):
            if stop: break
            time.sleep(1)
finally:
    producer.close()
    credential.close()
    print("Producer closed.")
