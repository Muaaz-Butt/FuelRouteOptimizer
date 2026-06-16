# Fuel Prices CSV Structure

Analysis of `data/fuel-prices-for-be-assessment.csv` for the FuelRouteOptimizer backend assessment.

## Overview

| Metric | Value |
|---|---|
| Total rows | 8,151 |
| Unique OPIS Truckstop IDs | 6,738 |
| Exact duplicate rows | 26 |
| States/provinces covered | 57 (US + Canada) |
| Retail price range | $2.69 – $6.40 / gallon |
| Missing coordinates | **Yes — no latitude/longitude columns** |

Each row represents a fuel price observation tied to a truck stop location. The file is sufficient for price storage and regional filtering, but **not sufficient on its own for route-based optimization** without a geocoding step.

---

## Columns

### 1. `OPIS Truckstop ID`

| Property | Detail |
|---|---|
| Type | Positive integer |
| Example | `7`, `105`, `52520` |
| Purpose | External identifier from the OPIS fuel pricing network |
| Notes | Best candidate for a **natural business key**. One ID maps to one physical location in this dataset (no ID spans multiple cities/states). |

**Data quality:** 6,738 unique IDs across 8,151 rows. ~1,413 IDs appear more than once, usually with different prices or alternate brand names.

---

### 2. `Truckstop Name`

| Property | Detail |
|---|---|
| Type | String (max ~45 chars) |
| Example | `PILOT TRAVEL CENTER #1243`, `LOVES TRAVEL STOP #766` |
| Purpose | Human-readable brand/location name |
| Notes | Branding variants exist for the same OPIS ID (e.g. `PILOT TRAVEL CENTER #87` vs `PILOT TRAVEL CENTERS #87`). |

**Data quality:** 227 OPIS IDs have more than one name. Treat as display metadata, not a unique key.

---

### 3. `Address`

| Property | Detail |
|---|---|
| Type | String (max ~53 chars) |
| Example | `I-44, EXIT 283 & US-69`, `US-13 & US-40` |
| Purpose | Location description, often highway-oriented |
| Notes | **Not a postal street address.** Most values are interstate exits, mile markers, or highway intersections. This is the primary geocoding challenge. |

---

### 4. `City`

| Property | Detail |
|---|---|
| Type | String (max ~25 chars) |
| Example | `Big Cabin`, `Council Bluffs` |
| Purpose | Nearest city/town |
| Notes | Some values contain trailing whitespace in the raw file; strip on import. |

---

### 5. `State`

| Property | Detail |
|---|---|
| Type | 2-letter region code |
| Example | `OK`, `TX`, `ON` (Ontario) |
| Purpose | US state or Canadian province |
| Notes | 57 distinct codes. Includes Canadian provinces (`AB`, `BC`, `MB`, `NB`, `NS`, `ON`, `QC`, `SK`, `YT`). Useful for pre-filtering before geocoding. |

---

### 6. `Rack ID`

| Property | Detail |
|---|---|
| Type | Positive integer |
| Example | `307`, `930`, `523` |
| Purpose | OPIS wholesale rack / pricing region identifier |
| Notes | Consistent per OPIS ID in this dataset (0 IDs with conflicting rack IDs). Useful for regional price analysis but not for route geometry. |

---

### 7. `Retail Price`

| Property | Detail |
|---|---|
| Type | Decimal (up to 8 decimal places) |
| Example | `3.00733333`, `3.72566666` |
| Purpose | Retail fuel price in USD per gallon |
| Notes | 597 OPIS IDs have multiple prices (likely snapshots or product variants). Range: $2.68733333 – $6.399. |

---

## Required Database Tables

The CSV maps cleanly to a normalized schema. A flat single-table import works for ingestion, but route optimization benefits from separation of concerns.

### Recommended schema

```
┌─────────────────────┐       ┌─────────────────────┐
│      Truckstop      │       │        Rack         │
├─────────────────────┤       ├─────────────────────┤
│ id (PK)             │       │ id (PK)             │
│ opis_truckstop_id ◄─┼──┐    │ rack_id (unique)    │
│ canonical_name      │  │    │ region_label (opt)  │
│ address             │  │    └─────────────────────┘
│ city                │  │
│ state               │  │
│ latitude  (nullable)│  │    ┌─────────────────────┐
│ longitude (nullable)│  │    │     FuelPrice       │
│ geocode_status      │  │    ├─────────────────────┤
│ geocoded_at         │  └───►│ id (PK)             │
└─────────────────────┘       │ truckstop_id (FK)   │
                              │ retail_price        │
                              │ observed_at (opt)   │
                              │ source_row_hash     │
                              └─────────────────────┘
```

### Table responsibilities

| Table | Required? | Role |
|---|---|---|
| **Truckstop** | Yes | One row per physical location (keyed by `opis_truckstop_id`). Holds address fields and geocoded coordinates once resolved. |
| **FuelPrice** | Yes | One or more price records per truck stop. Preserves multiple prices from the CSV instead of collapsing them. |
| **Rack** | Optional | Reference table for rack pricing regions. Can be deferred; `rack_id` can live on `FuelPrice` initially. |
| **Route / Trip** | Yes (app domain) | User trip input: origin, destination, vehicle MPG, tank capacity, fuel range. Not in CSV. |
| **GeocodeCache** | Recommended | Stores geocoding API responses to avoid repeat lookups and rate-limit issues. |

### Import deduplication strategy

Because the CSV has duplicate and conflicting rows:

| Scenario | Count | Recommended handling |
|---|---|---|
| Exact duplicate rows | 26 | Skip on import (hash or unique constraint) |
| Same OPIS ID, same location, different name | 227 | Upsert one `Truckstop`; store latest or most common name as canonical |
| Same OPIS ID, different prices | 597 | Insert multiple `FuelPrice` rows; use **lowest price** or **most recent** for optimization (business rule) |

### Indexes

| Index | Purpose |
|---|---|
| `opis_truckstop_id` (unique on Truckstop) | Fast lookup by external ID |
| `(state, city)` | Regional filtering |
| `(state, rack_id)` | Rack-based price queries |
| `(latitude, longitude)` or PostGIS `PointField` | Proximity / corridor searches after geocoding |
| `retail_price` | Cheapest-stop queries within a region |

---

## Challenges Due to Missing Coordinates

The CSV provides **where** a stop is described in words, but not **where** it is on a map. Route optimization requires knowing whether a truck stop lies near the driven path.

### 1. Cannot compute route proximity

Without `(latitude, longitude)`, you cannot:

- Find stops within N miles of a route polyline
- Rank stops by detour distance
- Enforce a vehicle's fuel range (e.g. 500 miles between fill-ups)

You must derive coordinates from `Address + City + State` via geocoding.

### 2. Addresses are not geocoder-friendly

Most `Address` values are highway references, not street addresses:

```
I-44, EXIT 283 & US-69
I-75, EXIT 144-B
I-80, EXIT 27
```

Geocoders often:

- Return the geographic center of a city instead of the exit
- Fail or return low-confidence matches
- Place a pin on the wrong side of an interstate

**Mitigation:** Geocode using `"<Address>, <City>, <State>"` as a composite query; store confidence scores; flag low-confidence results for manual review or a secondary data source.

### 3. Geocoding is slow, rate-limited, and costs money

~6,738 unique locations require external API calls (Google, Mapbox, Nominatim, etc.). At typical free-tier limits, batch geocoding takes hours or days without caching.

**Mitigation:** Run geocoding as an offline management command; persist results in `Truckstop.latitude/longitude`; never geocode at request time for all 8k stops.

### 4. Ambiguous locations

City + state alone is insufficient (many stops share a metro area). Two different OPIS IDs in the same city need distinct coordinates, but the CSV gives no sub-city precision beyond the highway exit string.

### 5. Multiple prices per stop complicate "cheapest on route"

597 truck stops have more than one price in the CSV. Even after geocoding, the optimizer must decide which price to use (minimum, average, latest).

### 6. No spatial index possible until geocoded

Database indexes on `(state, city)` only support coarse filtering (e.g. "stops in Texas"). Fine-grained "stops within 10 miles of I-40 between mile 100–300" requires coordinates and either:

- PostGIS / `django.contrib.gis` with spatial indexes, or
- Pre-segmenting stops by route corridor using an external routing engine

---

## Best Architecture

For a Django REST API that finds optimal fuel stops on US road trips:

```
┌──────────────────────────────────────────────────────────────┐
│                     Django REST API                          │
│  POST /api/trips/optimize   GET /api/truckstops/             │
└───────────────┬──────────────────────────┬───────────────────┘
                │                          │
    ┌───────────▼──────────┐    ┌──────────▼──────────┐
    │  Trip Optimizer      │    │  Truckstop Service  │
    │  (domain logic)      │    │  (queries + filters)│
    └───────────┬──────────┘    └──────────┬──────────┘
                │                          │
    ┌───────────▼──────────────────────────▼──────────┐
    │              Repository / ORM Layer              │
    │         Truckstop · FuelPrice · GeocodeCache    │
    └───────────┬──────────────────────────┬──────────┘
                │                          │
    ┌───────────▼──────────┐    ┌──────────▼──────────┐
    │   Routing Provider   │    │  Geocoding Provider │
    │  (OSRM / Mapbox /    │    │  (Mapbox / Google / │
    │   Google Directions) │    │   Nominatim)        │
    └──────────────────────┘    └─────────────────────┘
```

### Layer breakdown

| Layer | Responsibility |
|---|---|
| **Import pipeline** | `import_fuel_prices` management command: validate CSV rows, upsert `Truckstop`, insert `FuelPrice`, skip invalid rows with logging |
| **Geocoding pipeline** | Separate `geocode_truckstops` command: batch-geocode unlocated stops, cache results, set `geocode_status` (`pending`, `ok`, `failed`, `low_confidence`) |
| **Routing service** | External API returns route polyline + distance between origin/destination |
| **Optimizer service** | Core business logic: given route geometry, vehicle range, and tank rules, select stops that minimize cost without running out of fuel |
| **API layer** | DRF serializers/views; no business logic in views |

### Optimization algorithm (high level)

1. **Route** — Get driving route from origin → destination (polyline + total miles).
2. **Corridor filter** — Select geocoded truck stops within X miles of the route (spatial query or bounding-box pre-filter + distance check).
3. **Range segmentation** — Divide the route into ~500-mile (or vehicle-specific) segments based on max range.
4. **Stop selection** — In each segment, pick a stop (typically cheapest reachable option before fuel runs out).
5. **Cost calculation** — Sum fuel needed × retail price per segment; return stops + total cost.

### Key design decisions

| Decision | Recommendation | Rationale |
|---|---|---|
| Flat vs normalized tables | **Normalized** (`Truckstop` + `FuelPrice`) | Handles duplicate prices and name variants cleanly |
| Geocoding timing | **Offline batch**, not per-request | 6,738 API calls; must be cached in DB |
| Coordinate storage | `DecimalField` or `PointField` (PostGIS) | Enables spatial indexes and proximity queries |
| Price selection | **Minimum price** per truck stop | Conservative cost estimate for optimization |
| Routing provider | OSRM (free/self-hosted) or Mapbox | Route geometry is required input to optimizer |
| Idempotent imports | Unique constraint on `(opis_truckstop_id, retail_price, ...)` or row hash | Safe re-runs of import command |

### Suggested Django apps

```
fuel/              # Truckstop, FuelPrice, Rack models + import command
geocoding/         # GeocodeCache, geocode_truckstops command
routing/           # Route provider abstraction
optimizer/         # Trip optimization domain logic
api/               # DRF endpoints
```

### MVP path

1. Import CSV into `Truckstop` + `FuelPrice` (current `import_fuel_prices` command).
2. Batch-geocode truck stops; store lat/lng.
3. Integrate one routing API.
4. Implement corridor filter + greedy cheapest-stop selection per fuel range segment.
5. Expose `POST /api/trips/optimize` with `{origin, destination, mpg, tank_gallons}`.

---

## Sample Rows

```csv
OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,3.00733333
105,TA SAGINAW I 75 TRAVEL CENTER,"I-75, EXIT 144-B",Bridgeport,MI,260,3.269
105,TA SAGINAW I 75 TRAVEL CENTER,"I-75, EXIT 144-B",Bridgeport,MI,260,3.339
20,PILOT TRAVEL CENTER #1243,"I-8, EXIT 119 & SR-85",Gila Bend,AZ,930,3.899
20,PILOT #1243,"I-8, EXIT 119 & SR-85",Gila Bend,AZ,930,3.899
```

Row 1: canonical single-price stop.
Rows 2–3: same location, multiple prices — store one `Truckstop`, two `FuelPrice` records.
Rows 4–5: same location, different brand spelling — one `Truckstop`, pick canonical name.

---

## Summary

The CSV is a **price catalog with textual locations**, not a spatial dataset. Columns cover identity (`OPIS Truckstop ID`), location text (`Address`, `City`, `State`), pricing context (`Rack ID`), and cost (`Retail Price`). The minimum viable database needs **Truckstop** and **FuelPrice** tables, plus a geocoding pipeline to add coordinates. The dominant engineering challenge is converting highway-exit descriptions into reliable map points so stops can be matched to a driven route.
