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

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from azure.identity import DefaultAzureCredential
from azure.iot.device import IoTHubDeviceClient, Message
from azure.iot.hub import IoTHubRegistryManager

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FRIDGE_CSV = DATA_DIR / "fridges_freezers.csv"

IOT_HUB_NAME = "KWtelemetry"
IOT_HUB_HOSTNAME = f"{IOT_HUB_NAME}.azure-devices.net"
INTERVAL = 300        # default 300 (5 min)
SPEEDUP = 1           # >1 to accelerate for demos (e.g. 60 = 1s per fridge cycle)

# Authenticate using the caller's Entra ID security principal.
# Needs the "IoT Hub Data Contributor" (or stronger) role on the hub to read
# device keys from the registry. Telemetry itself is then sent per-device
# using each device's symmetric key.
credential = DefaultAzureCredential()
registry = IoTHubRegistryManager.from_token_credential(IOT_HUB_HOSTNAME, credential)

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
# Connect one IoT Hub device client per fridge
# ---------------------------------------------------------------------------

device_clients: dict[str, IoTHubDeviceClient] = {}
for fr in fridges:
    fid = fr["fridge_id"]
    device = registry.get_device(fid)
    primary_key = device.authentication.symmetric_key.primary_key
    client = IoTHubDeviceClient.create_from_symmetric_key(
        symmetric_key=primary_key,
        hostname=IOT_HUB_HOSTNAME,
        device_id=fid,
    )
    client.connect()
    device_clients[fid] = client
print(f"Connected {len(device_clients):,} device clients to {IOT_HUB_HOSTNAME}")

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
    for fr in fridges:
        fid = fr["fridge_id"]
        ev = build_event(fr)
        msg = Message(json.dumps(ev))
        msg.content_type = "application/json"
        msg.content_encoding = "utf-8"
        device_clients[fid].send_message(msg)


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
    for client in device_clients.values():
        try:
            client.shutdown()
        except Exception:
            pass
    credential.close()
    print("All device clients closed.")
