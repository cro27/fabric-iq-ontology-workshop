# KW — Microsoft Fabric IQ Workshop

Learn how to turn connected retail data into shared business context for AI with
**Microsoft Fabric IQ**. In this hands-on workshop, you build a data foundation,
model business entities and relationships in an ontology, and compare a
Lakehouse-only data agent with an ontology-grounded agent. The purpose is to explore
how explicit business meaning helps agents interpret questions, navigate
relationships, and explain answers across sales, inventory, logistics, and operations.
Optional live telemetry extends the scenario to cold-chain monitoring.

![KW ontology graph showing retail entities and their relationships in Microsoft Fabric](./images/readme/ontology.png)

## Workshop guide

Follow [Instructions.md](./Instructions.md) for the end-to-end workshop, including
Python setup, Fabric ingestion, telemetry, semantic models, ontology rules,
agents, and demonstration exercises.

The workshop is available under the [MIT License](./LICENSE).
Keep local environment files and credentials out of source control; use the
supplied environment templates for configuration.

The workshop is based on a fictional Australian supermarket chain - KW - covering 8 capital cities, 22 stores, 8 state DCs -
designed end-to-end for demonstrating **Microsoft Fabric** — Lakehouse, Eventhouse,
Real-Time Intelligence, Power BI semantic models, and **Fabric IQ** (ontology /
agent layer).

> Every dataset, schema, notebook, and producer in this pack is self-contained.
> No real customer data is used.

---

## What's in the box

```text
fabric-iq-ontology-workshop/
├── Instructions.md                   # end-to-end workshop guide
├── KW Prompt.txt                     # prompt used to generate the dataset, notebooks and scripts
├── data/                             # 27 interlinked synthetic CSVs (~59 MiB)
│   ├── stores.csv, warehouses.csv, fridges_freezers.csv
│   ├── products.csv, suppliers.csv, store_stock.csv, promotions.csv
│   ├── inwards_goods.csv, shipments.csv, shipment_lines.csv
│   ├── forklifts.csv, pick_events.csv
│   ├── trucks.csv, drivers.csv, routes.csv, trips.csv
│   ├── sales.csv, sale_lines.csv, customers.csv
│   ├── employees.csv, employee_skills.csv, performance_kpis.csv, training_records.csv
│   ├── campaigns.csv, campaign_performance.csv
│   └── energy_consumption.csv, wastage.csv
├── notebooks/
│   ├── 01_create_schema.ipynb         # creates the Delta table schema
│   ├── 01_create_schema_nopart.ipynb  # alternative schema without partitioning
│   ├── 02_ingest_csvs.ipynb           # loads CSVs from Files/KW/raw/
│   └── 03_build_semantic_model.ipynb  # builds the Direct Lake semantic model
├── ontology/
│   ├── custom_attributes.json        # property metadata, synonyms, and bindings
│   └── rules.json                    # ontology business rules and references
├── scripts/
│   ├── generate_data.py              # regenerates the historical dataset (seeded)
│   ├── fridge_telemetry_producer.py  # sends fridge events to Event Hubs
│   ├── truck_telemetry_producer.py   # sends truck events to Event Hubs
│   ├── test_fridge.py                # fridge diagnostic script
│   ├── test_fridge_EH.py             # fridge Event Hubs diagnostic script
│   ├── test_truck_EH.py              # truck Event Hubs diagnostic script
│   ├── requirements.txt             # local telemetry dependencies
│   └── .env.example                 # configuration template, no credentials
├── telemetry/
│   ├── fridge_telemetry_1week.csv    # sample fridge readings
│   └── truck_telemetry_1week.csv     # sample truck readings
├── KWagent/                         # optional Foundry Python ontology MCP agent sample
│   ├── agent.py
│   ├── README.md
│   ├── requirements.txt
│   └── .env.example
├── images/
│   ├── instructions/               # workshop logo and Eventstream screenshot
│   └── readme/
│       └── ontology.png            # ontology graph screenshot
├── .gitignore                      # excludes credentials, environments, and caches
├── LICENSE                         # MIT License
└── README.md                       # workshop overview
```

Review notebook configuration before running: imported copies may contain legacy
Lakehouse names. Use `KWlakehouse` and follow the configuration steps in
[Instructions.md](./Instructions.md). Local environment files and virtual
environments are not included in the repository.

---

## Data model at a glance

**Departments covered**: Stores, Sales, Distribution, Fleet Management, Marketing, HR, IT.

**Star schema** (silver layer):

```
              ┌───────────┐
              │  dim_date │
              └─────┬─────┘
        ┌──────────┼──────────────────────┐
        │          │                      │
   ┌────▼────┐ ┌───▼────────┐    ┌────────▼─────────┐
   │  Sales  │ │ Shipments  │    │ Pick Events      │
   └────┬────┘ └────┬───────┘    └────┬─────────────┘
        │           │                  │
   ┌────▼────────┐  │           ┌──────▼─────────┐
   │ Sale Lines  │  │           │   Warehouse    │
   └────┬────────┘  │           └──────┬─────────┘
        │           │                  │
   ┌────▼───┐  ┌────▼───┐               │
   │Product │  │ Store  │◄──────────────┘
   └────────┘  └────────┘
        ▲           ▲
        │           │
   ┌────┴───┐  ┌────┴────────────┐
   │Supplier│  │ Fridge / Freezer │ ◄─ joins to live Eventhouse stream
   └────────┘  └──────────────────┘
```

**Real-time streams (Eventhouse)**:
- `fridge_telemetry`  — every 5 min per fridge (temperature, humidity, door state)
- `truck_telemetry`   — every 30 min per truck (GPS, speed, cargo temp, ETA)

---

## Install

Follow the [workshop instructions](./Instructions.md) for prerequisites, local setup,
data ingestion, semantic model creation, ontology configuration, and agent setup.
The guide also covers live telemetry, demonstrations, and troubleshooting.
