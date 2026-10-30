"""
KW truck GPS telemetry producer.

Emits one event per active truck every 30 minutes. Each truck simulates a route
from its home warehouse to a destination store, interpolating lat/lon along the
straight-line path with realistic jitter. When a truck arrives, it picks a new
destination.

Event payload:
    event_time, truck_id, trip_id, origin_warehouse_id, destination_store_id,
    latitude, longitude, speed_kmh, heading_deg, cargo_temp_c, progress_pct

Usage:
    pip install azure-eventhub python-dotenv
    EH_CONNECTION_STRING=... EH_NAME=truck-telemetry python truck_telemetry_producer.py
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from azure.eventhub import EventHubProducerClient, EventData
from azure.identity import DefaultAzureCredential

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

EVENT_HUB_FULLY_QUALIFIED_NAMESPACE="Koleworth.servicebus.windows.net"   # optional override
EH_NAME="truck-telemetry"                        # optional override
INTERVAL=1800        # default 300 (5 min)
SPEEDUP=1 

credential = DefaultAzureCredential()


# ---------------------------------------------------------------------------
# Load reference data
# ---------------------------------------------------------------------------

def read_csv(name: str) -> list[dict]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

trucks     = [t for t in read_csv("trucks.csv") if t["status"] == "Active"]
warehouses = read_csv("warehouses.csv")
stores     = read_csv("stores.csv")
routes     = read_csv("routes.csv")

wh_coords = {w["warehouse_id"]: (float(w["latitude"]), float(w["longitude"])) for w in warehouses}
st_coords = {s["store_id"]:     (float(s["latitude"]), float(s["longitude"])) for s in stores}
stores_by_wh: dict[str, list[str]] = {}
for s in stores:
    stores_by_wh.setdefault(s["state"], []).append(s["store_id"])
wh_by_state = {w["state"]: w["warehouse_id"] for w in warehouses}
state_by_wh = {w["warehouse_id"]: w["state"]  for w in warehouses}

print(f"Loaded {len(trucks)} active trucks, {len(stores)} stores")

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1)*math.sin(phi2) - math.sin(phi1)*math.cos(phi2)*math.cos(dlam)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# ---------------------------------------------------------------------------
# Per-truck state
# ---------------------------------------------------------------------------

def new_trip(truck) -> dict:
    home_wh = truck["home_warehouse_id"]
    state = state_by_wh[home_wh]
    dest = random.choice(stores_by_wh.get(state, [s["store_id"] for s in stores]))
    avg_speed = random.uniform(70, 95) if truck["temperature_zone"] != "Refrigerated" else random.uniform(65, 85)
    return {
        "trip_id": f"LIVE-{uuid.uuid4().hex[:8].upper()}",
        "origin_wh": home_wh,
        "dest_store": dest,
        "start_lat": wh_coords[home_wh][0],
        "start_lon": wh_coords[home_wh][1],
        "end_lat":   st_coords[dest][0],
        "end_lon":   st_coords[dest][1],
        "progress": 0.0,
        "avg_speed_kmh": avg_speed,
        "cargo_target_c": -20 if truck["temperature_zone"] == "Refrigerated" and "Freezer" in truck["model"] else (
                           3 if truck["temperature_zone"] == "Refrigerated" else 22),
    }

state: dict[str, dict] = {t["truck_id"]: new_trip(t) for t in trucks}

# ---------------------------------------------------------------------------
# Producer loop
# ---------------------------------------------------------------------------

producer = EventHubProducerClient(
    fully_qualified_namespace=EVENT_HUB_FULLY_QUALIFIED_NAMESPACE,
    eventhub_name=EH_NAME,
    credential=credential,
)

stop = False
def _sigterm(*_):
    global stop
    stop = True
signal.signal(signal.SIGINT, _sigterm)
signal.signal(signal.SIGTERM, _sigterm)


def build_event(truck: dict) -> dict:
    s = state[truck["truck_id"]]
    total_km = haversine_km(s["start_lat"], s["start_lon"], s["end_lat"], s["end_lon"])
    # Distance advanced per interval (30 min default)
    hours_per_cycle = (INTERVAL / SPEEDUP) / 3600.0
    advanced_km = s["avg_speed_kmh"] * hours_per_cycle
    increment = min(1.0 - s["progress"], advanced_km / max(total_km, 0.1))
    s["progress"] += increment

    lat = s["start_lat"] + (s["end_lat"] - s["start_lat"]) * s["progress"] + random.uniform(-0.002, 0.002)
    lon = s["start_lon"] + (s["end_lon"] - s["start_lon"]) * s["progress"] + random.uniform(-0.002, 0.002)
    speed = s["avg_speed_kmh"] * random.uniform(0.85, 1.1)
    if s["progress"] >= 1.0:
        speed = 0
    cargo_temp = round(s["cargo_target_c"] + random.uniform(-1.5, 1.5), 2)

    payload = {
        "event_time": datetime.now(timezone.utc).isoformat(),
        "truck_id": truck["truck_id"],
        "rego": truck["rego"],
        "trip_id": s["trip_id"],
        "origin_warehouse_id": s["origin_wh"],
        "destination_store_id": s["dest_store"],
        "latitude":  round(lat, 6),
        "longitude": round(lon, 6),
        "speed_kmh": round(speed, 1),
        "heading_deg": round(bearing_deg(s["start_lat"], s["start_lon"], s["end_lat"], s["end_lon"]), 1),
        "cargo_temp_c": cargo_temp,
        "progress_pct": round(s["progress"] * 100, 1),
        "status": "Arrived" if s["progress"] >= 1.0 else "In Transit",
    }

    # if arrived, queue up a new trip for next cycle
    if s["progress"] >= 1.0:
        state[truck["truck_id"]] = new_trip(truck)

    return payload


def send_batch():
    batch = producer.create_batch()
    for t in trucks:
        ev = build_event(t)
        data = EventData(json.dumps(ev))
        try:
            batch.add(data)
        except ValueError:
            producer.send_batch(batch)
            batch = producer.create_batch()
            batch.add(data)
    if len(batch) > 0:
        producer.send_batch(batch)


print(f"Producing truck telemetry every {INTERVAL//SPEEDUP}s (speedup={SPEEDUP})")
try:
    while not stop:
        t0 = time.time()
        send_batch()
        elapsed = time.time() - t0
        print(f"[{datetime.now().isoformat(timespec='seconds')}] sent {len(trucks)} events in {elapsed:.1f}s")
        sleep_for = max(0, (INTERVAL // SPEEDUP) - elapsed)
        for _ in range(int(sleep_for)):
            if stop: break
            time.sleep(1)
finally:
    producer.close()
    print("Producer closed.")

