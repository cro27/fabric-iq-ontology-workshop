"""
KW synthetic data generator.

Produces interlinked CSV files under ../data/ covering:
  stores, fridges/freezers, products, suppliers, warehouses,
  inwards goods, shipments, forklifts, pick events,
  trucks, drivers, routes, trips,
  sales (headers + lines),
  employees, skills, kpis, training,
  customers, campaigns, campaign performance,
  energy consumption, wastage, promotions.

Designed for a Microsoft Fabric Lakehouse + Eventhouse demo (Fabric IQ ontology).
"""

from __future__ import annotations

import csv
import math
import os
import random
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from pathlib import Path

random.seed(42)

OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Reference: cities, states, capital lat/lon
# ---------------------------------------------------------------------------

CAPITALS = [
    # (city, state, lat, lon)
    ("Sydney",     "NSW", -33.8688, 151.2093),
    ("Melbourne",  "VIC", -37.8136, 144.9631),
    ("Brisbane",   "QLD", -27.4698, 153.0251),
    ("Perth",      "WA",  -31.9523, 115.8613),
    ("Adelaide",   "SA",  -34.9285, 138.6007),
    ("Hobart",     "TAS", -42.8821, 147.3272),
    ("Darwin",     "NT",  -12.4634, 130.8456),
    ("Canberra",   "ACT", -35.2809, 149.1300),
]

# Multiple store sites per capital
STORE_SITES = {
    "Sydney":    [("Bondi Junction", "500 Oxford St"), ("Chatswood", "1 Anderson St"),
                  ("Parramatta", "159 Church St"), ("Macquarie", "Herring Rd")],
    "Melbourne": [("Chadstone", "1341 Dandenong Rd"), ("Doncaster", "619 Doncaster Rd"),
                  ("Highpoint", "200 Rosamond Rd"), ("CBD", "300 Bourke St")],
    "Brisbane":  [("Indooroopilly", "318 Moggill Rd"), ("Chermside", "395 Hamilton Rd"),
                  ("Garden City", "2049 Logan Rd")],
    "Perth":     [("Karrinyup", "200 Karrinyup Rd"), ("Carousel", "1382 Albany Hwy"),
                  ("Booragoon", "125 Riseley St")],
    "Adelaide":  [("Marion", "297 Diagonal Rd"), ("Tea Tree Plaza", "976 North East Rd")],
    "Hobart":    [("Glenorchy", "367 Main Rd"), ("Eastlands", "30 Bligh St")],
    "Darwin":    [("Casuarina", "247 Trower Rd"), ("Palmerston", "10 Temple Tce")],
    "Canberra":  [("Belconnen", "Benjamin Way"), ("Tuggeranong", "Soward Way")],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_csv(name: str, header: list[str], rows: list[list]):
    path = OUT / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {path.name}: {len(rows):,} rows")


def jitter(value: float, pct: float = 0.001) -> float:
    return round(value + random.uniform(-pct, pct), 6)


def date_range(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


# ---------------------------------------------------------------------------
# 1. Warehouses (one per state)
# ---------------------------------------------------------------------------

print("Warehouses...")
warehouses = []
WAREHOUSE_ID_BY_STATE = {}
for i, (city, state, lat, lon) in enumerate(CAPITALS, start=1):
    wid = f"WH-{state}"
    WAREHOUSE_ID_BY_STATE[state] = wid
    warehouses.append([
        wid,
        f"KW {state} Distribution Centre",
        state,
        f"{random.randint(10, 500)} Industrial Dr, {city}",
        city,
        jitter(lat + random.uniform(-0.15, 0.15), 0.0001),
        jitter(lon + random.uniform(-0.15, 0.15), 0.0001),
        random.randint(8000, 25000),                # size_sqm
        random.choice(["Ambient", "Chilled", "Multi-temp"]),
        f"WH-MGR-{i:03d}",                          # employee_id of manager
    ])
write_csv("warehouses",
    ["warehouse_id", "name", "state", "address", "city",
     "latitude", "longitude", "size_sqm", "warehouse_type", "manager_employee_id"],
    warehouses)


# ---------------------------------------------------------------------------
# 2. Stores
# ---------------------------------------------------------------------------

print("Stores...")
stores = []
store_lookup = []  # for later use: (store_id, state, lat, lon)
sid_counter = 1
for city, state, lat, lon in CAPITALS:
    for site_name, address in STORE_SITES[city]:
        store_id = f"STR-{sid_counter:04d}"
        slat = jitter(lat + random.uniform(-0.05, 0.05), 0.0001)
        slon = jitter(lon + random.uniform(-0.05, 0.05), 0.0001)
        stores.append([
            store_id,
            f"KW {site_name}",
            site_name,
            city,
            state,
            address,
            f"{random.randint(2000, 7999)}",        # postcode
            slat,
            slon,
            random.randint(2500, 6500),             # size_sqm
            (date(2008, 1, 1) + timedelta(days=random.randint(0, 6000))).isoformat(),
            f"STR-MGR-{sid_counter:03d}",
        ])
        store_lookup.append((store_id, state, slat, slon))
        sid_counter += 1
write_csv("stores",
    ["store_id", "name", "site_name", "city", "state", "address", "postcode",
     "latitude", "longitude", "size_sqm", "opened_date", "manager_employee_id"],
    stores)


# ---------------------------------------------------------------------------
# 3. Fridges / Freezers (IoT)
# ---------------------------------------------------------------------------

print("Fridges & freezers...")
fridges = []
fridge_lookup = []  # (fridge_id, store_id, type)
FRIDGE_MODELS = [
    ("ChillMaster 5000", "fridge", 1, 4),
    ("ChillMaster Pro",  "fridge", 0, 5),
    ("DeepFreeze X1",    "freezer", -22, -18),
    ("DeepFreeze X2",    "freezer", -25, -19),
    ("ArcticAir Walk-In","freezer", -24, -18),
]
CODE_NAMES = ["Penguin","Yeti","Glacier","Iceberg","Tundra","Frost","Blizzard","Snowy",
              "Polar","Aurora","Crystal","Avalanche","Cryo","Boreal","Igloo","Nimbus"]

fid_counter = 1
for s in stores:
    store_id = s[0]
    # 8-14 units per store
    for _ in range(random.randint(8, 14)):
        model, type_, min_t, max_t = random.choice(FRIDGE_MODELS)
        code = f"{random.choice(CODE_NAMES)}-{random.randint(1, 99):02d}"
        fid = f"FRG-{fid_counter:05d}"
        fridges.append([
            fid, store_id, code, type_, model,
            min_t, max_t,
            (date(2018, 1, 1) + timedelta(days=random.randint(0, 2900))).isoformat(),
            random.choice(["operational","operational","operational","maintenance"]),
        ])
        fridge_lookup.append((fid, store_id, type_, min_t, max_t))
        fid_counter += 1
write_csv("fridges_freezers",
    ["fridge_id","store_id","code_name","unit_type","model",
     "min_safe_temp_c","max_safe_temp_c","install_date","status"],
    fridges)


# ---------------------------------------------------------------------------
# 4. Suppliers
# ---------------------------------------------------------------------------

print("Suppliers...")
SUPPLIER_NAMES = [
    ("Outback Organics", "AU"), ("Murray Dairy Co-op", "AU"), ("Tasman Seafood", "AU"),
    ("Riverina Produce", "AU"), ("Great Ocean Beverages", "AU"), ("Sunshine Bakery", "AU"),
    ("Top End Tropicals", "AU"), ("Adelaide Hills Wine", "AU"),
    ("Pacific Imports", "NZ"), ("Asia Foods Trading", "SG"),
    ("Euro Gourmet", "IT"), ("California Fresh", "US"),
    ("Highland Meats", "AU"), ("Reef Honey", "AU"), ("Coastal Catch", "AU"),
    ("Snowy Mountains Brewing", "AU"), ("Kakadu Foods", "AU"), ("Yarra Valley Farms", "AU"),
]
suppliers = []
for i, (name, country) in enumerate(SUPPLIER_NAMES, start=1):
    suppliers.append([
        f"SUP-{i:03d}", name, country,
        f"contact{i}@{name.lower().replace(' ','')}.com",
        random.randint(1, 21),                       # lead_time_days
        round(random.uniform(0.85, 0.99), 3),        # quality_score
        random.choice(["Tier 1","Tier 2","Tier 3"]),
    ])
write_csv("suppliers",
    ["supplier_id","name","country","contact_email","lead_time_days","quality_score","tier"],
    suppliers)


# ---------------------------------------------------------------------------
# 5. Products
# ---------------------------------------------------------------------------

print("Products...")
CATEGORIES = {
    "Dairy":      ("chilled", ["Milk 2L","Greek Yoghurt 1kg","Tasty Cheese 500g","Butter 250g","Cream 300ml"]),
    "Bakery":     ("ambient", ["White Loaf 700g","Sourdough 600g","Croissants 4pk","Bagels 6pk"]),
    "Produce":    ("ambient", ["Bananas 1kg","Apples 1kg","Carrots 1kg","Spinach 200g","Avocado each"]),
    "Meat":       ("chilled", ["Beef Mince 500g","Chicken Breast 1kg","Pork Chops 500g","Lamb Shanks 1kg"]),
    "Seafood":    ("chilled", ["Atlantic Salmon 400g","Prawns 500g","Barramundi 400g"]),
    "Frozen":     ("frozen",  ["Frozen Peas 1kg","Ice Cream 2L","Frozen Pizza","Fish Fingers 425g","Berries 500g"]),
    "Pantry":     ("ambient", ["Pasta 500g","Rice 1kg","Olive Oil 1L","Tomato Sauce 700g","Salt 1kg"]),
    "Beverages":  ("ambient", ["Cola 2L","Sparkling Water 1.25L","Orange Juice 2L","Coffee Beans 1kg"]),
    "Snacks":     ("ambient", ["Potato Chips 175g","Chocolate Block 200g","Muesli Bars 6pk"]),
    "Household":  ("ambient", ["Laundry Powder 2kg","Dish Liquid 750ml","Paper Towels 4pk","Toilet Paper 12pk"]),
}
products = []
pid = 1
for cat, (storage, items) in CATEGORIES.items():
    for item in items:
        sku = f"SKU{pid:06d}"
        cost = round(random.uniform(0.8, 18.0), 2)
        margin = random.uniform(0.20, 0.45)
        unit_price = round(cost * (1 + margin), 2)
        is_chilled = storage == "chilled"
        is_frozen = storage == "frozen"
        tax_rate = 0.0 if cat in ("Produce","Bakery","Meat","Dairy","Seafood") else 0.10
        products.append([
            f"PRD-{pid:04d}", sku, item, cat, storage,
            cost, unit_price, tax_rate,
            "true" if is_chilled else "false",
            "true" if is_frozen else "false",
            random.choice(suppliers)[0],
            round(random.uniform(0.15, 3.0), 3),  # weight_kg
            random.randint(50, 400),              # buffer_stock_units
        ])
        pid += 1
write_csv("products",
    ["product_id","sku","name","category","storage_type",
     "unit_cost","unit_price","tax_rate","is_chilled","is_frozen",
     "supplier_id","weight_kg","buffer_stock"],
    products)


# ---------------------------------------------------------------------------
# 6. Store stock levels (snapshot)
# ---------------------------------------------------------------------------

print("Store stock snapshot...")
stock_rows = []
for s in stores:
    store_id = s[0]
    for p in products:
        product_id = p[0]
        buffer = int(p[12])
        qty = max(0, int(random.gauss(buffer * 1.5, buffer * 0.5)))
        stock_rows.append([
            store_id, product_id, qty, buffer,
            (date.today() - timedelta(days=random.randint(0, 7))).isoformat(),
        ])
write_csv("store_stock",
    ["store_id","product_id","qty_on_hand","reorder_point","last_restocked_date"],
    stock_rows)


# ---------------------------------------------------------------------------
# 7. Inwards goods (warehouse receipts from suppliers)
# ---------------------------------------------------------------------------

print("Inwards goods...")
START_DATE = date(2026, 1, 1)
END_DATE   = date(2026, 5, 21)
inwards = []
iid = 1
for w in warehouses:
    wh_id = w[0]
    for d in date_range(START_DATE, END_DATE):
        # 6-18 inwards per warehouse per day
        for _ in range(random.randint(6, 18)):
            p = random.choice(products)
            qty = random.randint(40, 800)
            unit_cost = float(p[5]) * random.uniform(0.95, 1.05)
            inwards.append([
                f"IN-{iid:07d}", wh_id, p[10], p[0], qty,
                round(unit_cost, 2), d.isoformat(),
            ])
            iid += 1
write_csv("inwards_goods",
    ["receipt_id","warehouse_id","supplier_id","product_id","qty_in","unit_cost","receipt_date"],
    inwards)


# ---------------------------------------------------------------------------
# 8. Outbound shipments (warehouse -> store) and shipment lines
# ---------------------------------------------------------------------------

print("Outbound shipments...")
# Map state -> stores
stores_by_state: dict[str, list[str]] = {}
for s in stores:
    stores_by_state.setdefault(s[4], []).append(s[0])

shipments = []
shipment_lines = []
shp_id = 1
for w in warehouses:
    wh_id, _, state = w[0], w[1], w[2]
    target_stores = stores_by_state.get(state, [])
    if not target_stores:
        continue
    for d in date_range(START_DATE, END_DATE):
        for store_id in target_stores:
            # 1-3 shipments per store per day
            for _ in range(random.randint(1, 3)):
                sid_str = f"SHP-{shp_id:07d}"
                line_count = random.randint(8, 30)
                total_w = 0.0
                for _ in range(line_count):
                    p = random.choice(products)
                    qty = random.randint(5, 80)
                    weight = qty * float(p[11])
                    total_w += weight
                    shipment_lines.append([sid_str, p[0], qty, round(weight, 2)])
                shipments.append([
                    sid_str, wh_id, store_id, d.isoformat(),
                    round(total_w, 2), random.choice(["Standard","Express","Refrigerated"]),
                ])
                shp_id += 1
write_csv("shipments",
    ["shipment_id","warehouse_id","store_id","ship_date","total_weight_kg","service_level"],
    shipments)
write_csv("shipment_lines",
    ["shipment_id","product_id","qty","line_weight_kg"],
    shipment_lines)


# ---------------------------------------------------------------------------
# 9. Forklifts & pick events
# ---------------------------------------------------------------------------

print("Forklifts...")
forklifts = []
fk_lookup_by_wh: dict[str, list[str]] = {}
fk_id = 1
for w in warehouses:
    wh_id = w[0]
    for _ in range(random.randint(8, 16)):
        fkid = f"FK-{fk_id:04d}"
        forklifts.append([
            fkid, wh_id,
            random.choice(["Toyota 8FBE","Crown ESR","Hyster H50","Linde E20","Yale ERP"]),
            random.choice([1500, 2000, 2500, 3000]),    # capacity_kg
            (date.today() - timedelta(days=random.randint(10, 365))).isoformat(),
            random.choice(["Available","In Use","Service"]),
        ])
        fk_lookup_by_wh.setdefault(wh_id, []).append(fkid)
        fk_id += 1
write_csv("forklifts",
    ["forklift_id","warehouse_id","model","capacity_kg","last_service_date","status"],
    forklifts)

print("Pick events...")
picks = []
pk_id = 1
priority_customers = [f"STR-{i:04d}" for i in range(1, 9)]  # first 8 stores treated as priority
for w in warehouses:
    wh_id = w[0]
    workers = [f"EMP-W{wh_id[-2:]}-{i:03d}" for i in range(1, 26)]
    for d in date_range(START_DATE, END_DATE):
        for _ in range(random.randint(120, 220)):
            worker = random.choice(workers)
            items = random.randint(15, 90)
            errors = max(0, int(random.gauss(0.6, 1.2)))
            duration = round(items * random.uniform(0.4, 1.1), 1)  # minutes
            pick_rate = round(items / max(duration/60, 0.01), 1)   # items per hour
            tare = random.choice([20, 25, 30])
            destination = random.choice([s[0] for s in stores])
            picks.append([
                f"PK-{pk_id:08d}", wh_id, worker, d.isoformat(),
                items, errors, duration, pick_rate,
                "true" if destination in priority_customers else "false",
                destination, tare,
                round(random.uniform(50, 950), 2),       # bulk_replacement_minutes
            ])
            pk_id += 1
write_csv("pick_events",
    ["pick_id","warehouse_id","worker_employee_id","pick_date",
     "items_picked","errors","duration_minutes","pick_rate_items_per_hour",
     "is_priority_customer","destination_store_id","tare_weight_kg","bulk_replacement_minutes"],
    picks)


# ---------------------------------------------------------------------------
# 10. Trucks, drivers, routes, trips
# ---------------------------------------------------------------------------

print("Trucks...")
trucks = []
truck_lookup = []
truck_id = 1
for w in warehouses:
    wh_id = w[0]
    for _ in range(random.randint(6, 12)):
        tid = f"TRK-{truck_id:04d}"
        capacity = random.choice([12000, 18000, 22000, 26000])
        tare = capacity // 3
        trucks.append([
            tid, f"{random.choice(['NSW','VIC','QLD','WA','SA','TAS','NT','ACT'])}-{random.randint(100,999)}-{random.choice('ABCDEFGHJKLMN')}",
            random.choice(["Volvo FH","Kenworth K200","Scania R450","Isuzu Giga","Mercedes Actros"]),
            capacity, tare, wh_id,
            random.choice(["Refrigerated","Ambient","Multi-temp"]),
            random.choice(["Active","Service","Active","Active"]),
        ])
        truck_lookup.append((tid, wh_id))
        truck_id += 1
write_csv("trucks",
    ["truck_id","rego","model","capacity_kg","tare_weight_kg",
     "home_warehouse_id","temperature_zone","status"],
    trucks)

print("Drivers...")
FIRST_NAMES = ["James","Olivia","William","Charlotte","Jack","Mia","Liam","Sophia",
               "Noah","Amelia","Lucas","Isla","Henry","Ava","Oliver","Grace","Ethan","Ruby"]
LAST_NAMES  = ["Smith","Jones","Williams","Brown","Wilson","Taylor","Nguyen","Lee",
               "Patel","Singh","Kim","Garcia","Murphy","Walker","Chen","Robinson"]
drivers = []
drv_id = 1
for _ in range(80):
    did = f"DRV-{drv_id:04d}"
    drivers.append([
        did, f"EMP-D{drv_id:04d}",
        f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        random.choice(["HR","HC","MC"]),                   # heavy rigid / combination / multi-combination
        (date(2010,1,1) + timedelta(days=random.randint(0, 5000))).isoformat(),
        random.choice([w[0] for w in warehouses]),
        random.choice(["Day","Night","Rotating"]),
    ])
    drv_id += 1
write_csv("drivers",
    ["driver_id","employee_id","name","license_class",
     "license_issued","home_warehouse_id","shift"],
    drivers)

print("Routes...")
routes = []
route_id = 1
wh_coords = {w[0]: (float(w[5]), float(w[6])) for w in warehouses}
store_coords = {s[0]: (float(s[7]), float(s[8])) for s in stores}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))

for w in warehouses:
    wh_id, wh_state = w[0], w[2]
    for store_id in stores_by_state.get(wh_state, []):
        lat1, lon1 = wh_coords[wh_id]
        lat2, lon2 = store_coords[store_id]
        dist = round(haversine(lat1, lon1, lat2, lon2) * random.uniform(1.15, 1.4), 1)
        dur  = round(dist / random.uniform(45, 65), 2)
        routes.append([
            f"RT-{route_id:04d}", wh_id, store_id, dist, dur,
            random.choice(["Direct","Multi-stop","Express"]),
        ])
        route_id += 1
write_csv("routes",
    ["route_id","origin_warehouse_id","destination_store_id",
     "distance_km","estimated_duration_hours","route_type"],
    routes)

print("Trips...")
trips = []
trip_id = 1
for d in date_range(START_DATE, END_DATE):
    for r in routes:
        # 1-3 trips per route per day
        for _ in range(random.randint(1, 3)):
            truck = random.choice([t[0] for t in trucks if t[5] == r[1]])
            driver = random.choice([dr[0] for dr in drivers if dr[5] == r[1]] or [drivers[0][0]])
            dep_h = random.randint(4, 18)
            dep = datetime.combine(d, time(dep_h, random.randint(0, 59)))
            actual_dur = float(r[4]) * random.uniform(0.9, 1.3)
            arr = dep + timedelta(hours=actual_dur)
            trips.append([
                f"TR-{trip_id:07d}", truck, driver, r[0],
                dep.isoformat(timespec="minutes"),
                arr.isoformat(timespec="minutes"),
                round(actual_dur, 2),
                random.choice(["Completed","Completed","Completed","Delayed","Cancelled"]),
                round(random.uniform(2000, 25000), 1),    # cargo_weight_kg
                round(random.uniform(15, 45), 2),         # fuel_litres_per_100km
            ])
            trip_id += 1
write_csv("trips",
    ["trip_id","truck_id","driver_id","route_id",
     "departure_time","arrival_time","actual_duration_hours",
     "status","cargo_weight_kg","fuel_l_per_100km"],
    trips)


# ---------------------------------------------------------------------------
# 11. Sales (heads + lines)
# ---------------------------------------------------------------------------

print("Customers (loyalty)...")
customers = []
for i in range(1, 2001):
    state = random.choice(CAPITALS)[1]
    customers.append([
        f"CUS-{i:05d}",
        f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
        f"customer{i}@example.com",
        (date(1950, 1, 1) + timedelta(days=random.randint(0, 25000))).isoformat(),
        random.choice(["Female","Male","Non-binary","Prefer not to say"]),
        f"{random.randint(2000,7999)}",
        state,
        (date(2018,1,1) + timedelta(days=random.randint(0, 2900))).isoformat(),
        random.choice(["Bronze","Bronze","Silver","Silver","Gold","Platinum"]),
        random.choice(["Email","SMS","App","None"]),
    ])
write_csv("customers",
    ["customer_id","name","email","date_of_birth","gender",
     "postcode","state","joined_date","loyalty_tier","preferred_channel"],
    customers)

print("Sales (this may take a moment)...")
sales = []
sale_lines = []
sale_id = 1
salespeople_by_store = {s[0]: [f"EMP-S{s[0][-4:]}-{i:02d}" for i in range(1, 9)] for s in stores}

# To keep file size sane: 1-Apr to 21-May 2026 sales
SALES_START = date(2026, 4, 1)
for d in date_range(SALES_START, END_DATE):
    weekday_mult = 1.3 if d.weekday() >= 5 else 1.0
    for s in stores:
        store_id = s[0]
        n_sales = int(random.randint(40, 120) * weekday_mult)
        for _ in range(n_sales):
            cust = random.choice(customers)[0] if random.random() < 0.65 else ""
            sp   = random.choice(salespeople_by_store[store_id])
            sale_time = time(random.randint(7, 21), random.randint(0, 59))
            n_lines = random.randint(1, 12)
            subtotal = 0.0
            tax_total = 0.0
            for _ in range(n_lines):
                p = random.choice(products)
                qty = random.randint(1, 5)
                unit_price = float(p[6])
                tax_rate = float(p[7])
                unit_cost = float(p[5])
                line_total = qty * unit_price
                line_tax   = round(line_total * tax_rate, 2)
                profit     = round(qty * (unit_price - unit_cost), 2)
                subtotal  += line_total
                tax_total += line_tax
                sale_lines.append([
                    f"SL-{sale_id:08d}", p[0], qty, unit_price,
                    tax_rate, round(line_total, 2), line_tax, profit,
                ])
            sales.append([
                f"SL-{sale_id:08d}", store_id, d.isoformat(),
                sale_time.isoformat(timespec="seconds"),
                cust, sp, round(subtotal, 2), round(tax_total, 2),
                round(subtotal + tax_total, 2),
                random.choice(["Card","Card","Card","Cash","App"]),
            ])
            sale_id += 1
write_csv("sales",
    ["sale_id","store_id","sale_date","sale_time","customer_id",
     "salesperson_employee_id","subtotal","tax_total","total","payment_method"],
    sales)
write_csv("sale_lines",
    ["sale_id","product_id","qty","unit_price","tax_rate","line_total","line_tax","profit"],
    sale_lines)


# ---------------------------------------------------------------------------
# 12. HR
# ---------------------------------------------------------------------------

print("Employees...")
DEPARTMENTS = ["Stores","Sales","Distribution","Fleet Management","Marketing","HR","IT"]
ROLES = {
    "Stores":           ["Store Manager","Assistant Manager","Department Lead","Checkout Operator","Stocker","Baker","Butcher"],
    "Sales":            ["Sales Associate","Promotions Lead","Customer Service"],
    "Distribution":     ["Warehouse Manager","Picker","Packer","Forklift Operator","Inventory Analyst"],
    "Fleet Management": ["Fleet Manager","Driver","Mechanic","Route Planner"],
    "Marketing":        ["CMO","Campaign Manager","Digital Analyst","Designer"],
    "HR":               ["CHRO","HR Business Partner","Recruiter","Payroll"],
    "IT":               ["CIO","Solution Architect","Data Engineer","Support Engineer","Security Analyst"],
}
EMPLOYMENT_TYPES = ["Full-Time","Part-Time","Casual"]

employees = []
emp_id = 1
# Head office (Melbourne) departments: Marketing, HR, IT
ho_store_id = next(s[0] for s in stores if s[3] == "Melbourne")
for dept in ["Marketing","HR","IT"]:
    for role in ROLES[dept]:
        for _ in range(random.randint(3, 10)):
            employees.append([
                f"EMP-{emp_id:05d}",
                f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                role, dept, "HEAD-OFFICE", "Head Office",
                random.choice(EMPLOYMENT_TYPES),
                (date(2012,1,1) + timedelta(days=random.randint(0, 5000))).isoformat(),
                random.randint(55000, 220000),
                "" if role.startswith(("C","CHRO","CIO","CMO")) else f"EMP-{random.randint(1, max(1, emp_id-1)):05d}",
            ])
            emp_id += 1
# Store staff
for s in stores:
    for role in ROLES["Stores"]:
        for _ in range(random.randint(1, 6)):
            employees.append([
                f"EMP-{emp_id:05d}",
                f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                role, "Stores", s[0], "Store",
                random.choice(EMPLOYMENT_TYPES),
                (date(2015,1,1) + timedelta(days=random.randint(0, 4000))).isoformat(),
                random.randint(45000, 130000),
                f"EMP-{random.randint(1, max(1, emp_id-1)):05d}",
            ])
            emp_id += 1
    for role in ROLES["Sales"]:
        for _ in range(random.randint(1, 4)):
            employees.append([
                f"EMP-{emp_id:05d}",
                f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                role, "Sales", s[0], "Store",
                random.choice(EMPLOYMENT_TYPES),
                (date(2015,1,1) + timedelta(days=random.randint(0, 4000))).isoformat(),
                random.randint(48000, 95000),
                f"EMP-{random.randint(1, max(1, emp_id-1)):05d}",
            ])
            emp_id += 1
# Warehouse staff
for w in warehouses:
    for role in ROLES["Distribution"]:
        for _ in range(random.randint(2, 8)):
            employees.append([
                f"EMP-{emp_id:05d}",
                f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                role, "Distribution", w[0], "Warehouse",
                random.choice(EMPLOYMENT_TYPES),
                (date(2014,1,1) + timedelta(days=random.randint(0, 4500))).isoformat(),
                random.randint(55000, 140000),
                f"EMP-{random.randint(1, max(1, emp_id-1)):05d}",
            ])
            emp_id += 1
    for role in ROLES["Fleet Management"]:
        for _ in range(random.randint(2, 6)):
            employees.append([
                f"EMP-{emp_id:05d}",
                f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                role, "Fleet Management", w[0], "Warehouse",
                random.choice(EMPLOYMENT_TYPES),
                (date(2014,1,1) + timedelta(days=random.randint(0, 4500))).isoformat(),
                random.randint(60000, 145000),
                f"EMP-{random.randint(1, max(1, emp_id-1)):05d}",
            ])
            emp_id += 1
write_csv("employees",
    ["employee_id","name","role","department","location_id","location_type",
     "employment_type","hire_date","base_salary_aud","manager_employee_id"],
    employees)

print("Skills...")
SKILLS = ["Forklift License","Heavy Vehicle (HR)","Heavy Vehicle (MC)","Food Safety",
         "First Aid","Cold Chain Handling","RSA","Inventory Mgmt","Power BI","Excel Advanced",
         "Cash Handling","Dangerous Goods","Customer Service","Coaching"]
skill_rows = []
sk_id = 1
for e in employees:
    n_skills = random.randint(1, 4)
    for sk in random.sample(SKILLS, n_skills):
        issued = date(2020,1,1) + timedelta(days=random.randint(0, 2000))
        skill_rows.append([
            f"SK-{sk_id:06d}", e[0], sk, issued.isoformat(),
            (issued + timedelta(days=random.choice([365, 730, 1095]))).isoformat(),
        ])
        sk_id += 1
write_csv("employee_skills",
    ["skill_record_id","employee_id","skill_name","certified_date","expiry_date"],
    skill_rows)

print("Performance KPIs...")
kpi_rows = []
for e in employees:
    for month_offset in range(6):
        period = (date(2025,12,1) + timedelta(days=30*month_offset)).strftime("%Y-%m")
        kpi_rows.append([
            e[0], period,
            round(random.gauss(78, 12), 1),
            random.randint(0, 4),
            "true" if random.random() < 0.04 else "false",
        ])
write_csv("performance_kpis",
    ["employee_id","period_yyyymm","kpi_score","absenteeism_days","turnover_flag"],
    kpi_rows)

print("Training requirements...")
COURSES = ["Cold Chain 101","Forklift Refresher","Workplace Safety","Cyber Awareness",
           "Fabric for Analysts","Customer Empathy","Leadership Essentials","First Aid Refresher"]
training_rows = []
tr_id = 1
for e in employees:
    n_courses = random.randint(1, 3)
    for course in random.sample(COURSES, n_courses):
        completion = (date(2024,1,1) + timedelta(days=random.randint(0, 800)))
        training_rows.append([
            f"TR-{tr_id:06d}", e[0], course,
            completion.isoformat(),
            random.choice(["Mandatory","Recommended","Optional"]),
            random.choice(["Completed","In Progress","Overdue"]),
        ])
        tr_id += 1
write_csv("training_records",
    ["training_id","employee_id","course_name","completion_date","priority","status"],
    training_rows)


# ---------------------------------------------------------------------------
# 13. Marketing
# ---------------------------------------------------------------------------

print("Campaigns...")
CHANNELS = ["Email","Social","TV","Radio","In-Store","App Push","Loyalty"]
SEGMENTS = ["Families","Singles","Seniors","Students","Foodies","Health-Conscious","Budget"]
campaigns = []
for i in range(1, 41):
    start = date(2025,6,1) + timedelta(days=random.randint(0, 320))
    end = start + timedelta(days=random.randint(7, 60))
    campaigns.append([
        f"CMP-{i:03d}",
        f"{random.choice(['Fresh','Save Big','Winter','Summer','BBQ','Healthy','Pantry','Family'])} {random.choice(['Festival','Sale','Picks','Bonus','Rewards'])}",
        random.choice(CHANNELS),
        start.isoformat(), end.isoformat(),
        random.randint(20000, 1500000),
        random.choice(SEGMENTS),
        random.choice(["Active","Planned","Completed","Paused"]),
    ])
write_csv("campaigns",
    ["campaign_id","name","channel","start_date","end_date",
     "budget_aud","target_segment","status"],
    campaigns)

print("Campaign performance...")
cperf = []
for c in campaigns:
    cid = c[0]
    days_in_window = (date.fromisoformat(c[4]) - date.fromisoformat(c[3])).days + 1
    for offset in range(days_in_window):
        d = date.fromisoformat(c[3]) + timedelta(days=offset)
        impressions = random.randint(2000, 80000)
        clicks      = int(impressions * random.uniform(0.01, 0.08))
        conv        = int(clicks * random.uniform(0.02, 0.15))
        rev         = round(conv * random.uniform(25, 220), 2)
        cperf.append([cid, d.isoformat(), impressions, clicks, conv, rev])
write_csv("campaign_performance",
    ["campaign_id","date","impressions","clicks","conversions","revenue_aud"],
    cperf)


# ---------------------------------------------------------------------------
# 14. Promotions linked to sales (bonus)
# ---------------------------------------------------------------------------

print("Promotions...")
promos = []
for i in range(1, 31):
    p = random.choice(products)
    start = date(2026, random.randint(1,5), random.randint(1,28))
    promos.append([
        f"PRM-{i:03d}", p[0],
        round(float(p[6]) * random.uniform(0.6, 0.9), 2),
        start.isoformat(),
        (start + timedelta(days=random.randint(3, 21))).isoformat(),
        random.choice(CHANNELS),
    ])
write_csv("promotions",
    ["promotion_id","product_id","promo_price","start_date","end_date","channel"],
    promos)


# ---------------------------------------------------------------------------
# 15. Energy consumption per store (great for sustainability narrative)
# ---------------------------------------------------------------------------

print("Energy consumption...")
energy_rows = []
for s in stores:
    for d in date_range(date(2026,1,1), END_DATE):
        base = s[9] * 0.18  # size_sqm * factor
        kwh = round(base + random.uniform(-50, 50), 2)
        energy_rows.append([s[0], d.isoformat(), kwh, round(kwh * 0.28, 2)])
write_csv("energy_consumption",
    ["store_id","date","kwh","cost_aud"],
    energy_rows)


# ---------------------------------------------------------------------------
# 16. Wastage / spoilage
# ---------------------------------------------------------------------------

print("Wastage...")
waste_rows = []
wid = 1
for s in stores:
    for d in date_range(date(2026,4,1), END_DATE):
        for _ in range(random.randint(2, 8)):
            p = random.choice(products)
            qty = random.randint(1, 12)
            waste_rows.append([
                f"WST-{wid:07d}", s[0], p[0], d.isoformat(), qty,
                round(qty * float(p[5]), 2),
                random.choice(["Expired","Damaged","Temperature Excursion","Overstock"]),
            ])
            wid += 1
write_csv("wastage",
    ["wastage_id","store_id","product_id","date","qty","cost_aud","reason"],
    waste_rows)


print("\nDone. Output:", OUT)
