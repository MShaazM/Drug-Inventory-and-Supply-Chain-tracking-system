# TrackRx

**Real-time drug inventory & supply chain tracking for multi-institution healthcare networks.**

Built for Smart India Hackathon 2026 — Problem Statement **PSS04: Drug Inventory and Supply Chain Tracking System** — by Team **UnderCTRL**.

---

## The Problem

Hospitals, primary health centres (PHCs), and rural clinics typically track drug stock through manual registers or disconnected spreadsheets. This leads to:

- Stockouts of essential medicines with no early warning
- Expired drugs going undetected until it's too late
- No visibility into which vendors are reliable
- No easy way to move surplus stock between institutions that need it
- No audit trail of who consumed, transferred, or received what, and when

## The Solution

TrackRx gives every institution in a network live visibility into stock, expiry, QC status, and shipments — in one place, with role-based views and an AI layer that answers questions about the data in plain English.

## Features

### 📊 Dashboard
Real-time metrics, low-stock alerts, a Smart Reorder Engine that flags drugs likely to run out before the next delivery (based on actual consumption rate + vendor lead time, not a fixed threshold), expiry notifications (Urgent ≤30 days / Watch 31–90 days), consumption trend charts, and vendor on-time delivery performance.

### 🤖 Ask TrackRx
A natural-language query layer powered by Google's Gemini API. Ask things like *"Which drugs are critical this week?"* or *"How are our vendors performing?"* and get answers grounded strictly in the live data snapshot — no hallucinated numbers. If the API is unavailable, an offline rule-based engine mirrors the same logic so queries never hard-fail.

### 💊 Inventory
View and filter current stock, record consumption (dispensing to patients), update QC status per batch, add new batches manually, or bulk-import via CSV.

### 🚚 Shipments
Track active shipments from vendors, create new vendor orders, transfer stock directly between institutions (with automatic stock validation so a transfer can never oversend), and bulk-import shipment records via CSV.

### 📜 Activity Log
A full, filterable, exportable audit trail of every stock movement — consumption, transfers, deliveries — with date range, drug, and reason filters.

### 👥 Role-based views
Pharmacist, Procurement Officer, QC staff, and Institution Admin each see a view scoped to what's relevant to them.

### 🔄 Reset Demo Data
One-click wipe and reseed with fresh randomized demo data, for clean testing and demos.

## Tech Stack

| Layer | Technology |
|---|---|
| UI / App framework | [Streamlit](https://streamlit.io/) |
| Database | SQLite |
| Charts | [Plotly](https://plotly.com/python/) |
| AI / NL queries | Google Gemini API (native `google-genai` SDK) |
| Data handling | pandas |

## Getting Started

### Prerequisites
- Python 3.9+
- A free [Gemini API key](https://aistudio.google.com/) (optional — the app works offline without one)

### Installation

```bash
git clone <your-repo-url>
cd trackrx
pip install -r requirements.txt
```

### Configuration

Create `.streamlit/secrets.toml` in the project root:

```toml
GEMINI_API_KEY = "your-gemini-api-key-here"
```

Alternatively, set it as an environment variable:

```bash
export GEMINI_API_KEY="your-gemini-api-key-here"
```

If no key is configured, **Ask TrackRx** automatically falls back to offline rule-based analysis — the rest of the app is unaffected either way.

### Run the app

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`. On first run, it seeds itself with randomized demo data automatically.

## Bulk CSV Import Format

**Inventory** (`drug_name, batch_no, quantity, reorder_threshold, expiry_date, vendor_name, institution_name, qc_status, category`) — vendors and institutions are auto-created if they don't already exist.

**Shipments** (`drug_name, quantity, vendor_name, institution_name, status, order_date, expected_delivery_date, delivered_date`) — leave `expected_delivery_date` blank to auto-compute it from the vendor's lead time.

## Project Structure

```
├── app.py            # Streamlit UI — all pages and interactions
├── database.py        # SQLite schema, queries, seeding, bulk import logic
├── nl_query.py         # Ask TrackRx — Gemini integration + offline fallback
├── requirements.txt
└── .streamlit/
    └── secrets.toml     # API key config (not committed)
```

## Team UnderCTRL

Built for Smart India Hackathon 2026.

---

