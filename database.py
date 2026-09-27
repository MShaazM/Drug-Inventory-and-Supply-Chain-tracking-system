"""
database.py
Handles all SQLite database setup, seeding, and query logic for the
Drug Inventory and Supply Chain Tracking System (PSS04) prototype.
"""

import sqlite3
import random
from datetime import date, timedelta

DB_PATH = "pss04.db"

# ---- Reference data used for seeding realistic demo data ----
DRUG_NAMES = [
    "Paracetamol 500mg", "Amoxicillin 250mg", "Metformin 500mg",
    "Ibuprofen 400mg", "Azithromycin 500mg", "Cetirizine 10mg",
    "Insulin Glargine", "ORS Sachets", "Amlodipine 5mg", "Omeprazole 20mg",
]
VENDOR_NAMES = ["Sunrise Pharma Distributors", "MedLine Supply Co.", "Apex Healthcare Logistics"]
INSTITUTION_NAMES = ["City General Hospital", "Sector-9 Primary Health Centre", "Rural Health Clinic - Wardha"]
SHIPMENT_STATUSES = ["Ordered", "Shipped", "Delivered"]
QC_STATUSES = ["Passed", "Pending", "Failed"]
DRUG_CATEGORIES = [
    "Analgesic/Antipyretic", "Antibiotic", "Antidiabetic", "Antihypertensive/Cardiac",
    "Antihistamine", "Respiratory", "Gastrointestinal", "Vitamin/Supplement",
    "Rehydration/Emergency", "Other",
]

# Keyword -> category. Matched case-insensitively against the drug name.
# Deterministic and offline — no external calls, so it can't fail live in a demo.
_CATEGORY_KEYWORDS = {
    "paracetamol": "Analgesic/Antipyretic", "ibuprofen": "Analgesic/Antipyretic",
    "aspirin": "Analgesic/Antipyretic", "diclofenac": "Analgesic/Antipyretic",
    "amoxicillin": "Antibiotic", "azithromycin": "Antibiotic", "ciprofloxacin": "Antibiotic",
    "doxycycline": "Antibiotic", "metformin": "Antidiabetic", "insulin": "Antidiabetic",
    "glimepiride": "Antidiabetic", "amlodipine": "Antihypertensive/Cardiac",
    "atenolol": "Antihypertensive/Cardiac", "losartan": "Antihypertensive/Cardiac",
    "cetirizine": "Antihistamine", "loratadine": "Antihistamine",
    "omeprazole": "Gastrointestinal", "pantoprazole": "Gastrointestinal",
    "ranitidine": "Gastrointestinal", "salbutamol": "Respiratory", "montelukast": "Respiratory",
    "ors": "Rehydration/Emergency", "vitamin": "Vitamin/Supplement",
    "calcium": "Vitamin/Supplement", "iron": "Vitamin/Supplement",
}


def categorize_drug(drug_name):
    """Best-effort keyword match against the drug name; falls back to 'Other'."""
    name_lower = str(drug_name).lower()
    for keyword, category in _CATEGORY_KEYWORDS.items():
        if keyword in name_lower:
            return category
    return "Other"


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(reset: bool = False):
    conn = get_connection()
    cur = conn.cursor()

    if reset:
        cur.executescript("""
            DROP TABLE IF EXISTS transactions;
            DROP TABLE IF EXISTS shipments;
            DROP TABLE IF EXISTS inventory;
            DROP TABLE IF EXISTS vendors;
            DROP TABLE IF EXISTS institutions;
        """)

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            lead_time_days INTEGER NOT NULL DEFAULT 5
        );

        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name TEXT NOT NULL,
            batch_no TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            reorder_threshold INTEGER NOT NULL DEFAULT 50,
            expiry_date TEXT NOT NULL,
            vendor_id INTEGER,
            institution_id INTEGER,
            qc_status TEXT NOT NULL DEFAULT 'Passed',
            category TEXT NOT NULL DEFAULT 'Other',
            FOREIGN KEY (vendor_id) REFERENCES vendors(id),
            FOREIGN KEY (institution_id) REFERENCES institutions(id)
        );

        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            vendor_id INTEGER,
            institution_id INTEGER,
            status TEXT NOT NULL DEFAULT 'Ordered',
            order_date TEXT NOT NULL,
            expected_delivery_date TEXT,
            delivered_date TEXT,
            source_type TEXT NOT NULL DEFAULT 'Vendor',
            source_inventory_id INTEGER,
            FOREIGN KEY (vendor_id) REFERENCES vendors(id),
            FOREIGN KEY (institution_id) REFERENCES institutions(id),
            FOREIGN KEY (source_inventory_id) REFERENCES inventory(id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_id INTEGER NOT NULL,
            change_qty INTEGER NOT NULL,
            reason TEXT NOT NULL,
            txn_date TEXT NOT NULL,
            FOREIGN KEY (inventory_id) REFERENCES inventory(id)
        );
    """)
    conn.commit()

    # Only seed if empty
    cur.execute("SELECT COUNT(*) FROM inventory")
    if cur.fetchone()[0] == 0:
        seed_data(conn)

    conn.close()


def seed_data(conn):
    cur = conn.cursor()

    vendor_ids = []
    for v in VENDOR_NAMES:
        lead_time = random.choice([3, 5, 7])
        cur.execute("INSERT INTO vendors (name, lead_time_days) VALUES (?, ?)", (v, lead_time))
        vendor_ids.append(cur.lastrowid)

    institution_ids = []
    for i in INSTITUTION_NAMES:
        cur.execute("INSERT INTO institutions (name) VALUES (?)", (i,))
        institution_ids.append(cur.lastrowid)

    today = date.today()
    inventory_ids = []
    inventory_institution_map = {}

    # Designate a fixed subset of drugs as "fast movers" so the smart-reorder
    # feature has something to reliably surface on every seed — their starting
    # quantity is intentionally kept low, independent of the general random mix.
    fast_movers = set(random.sample(DRUG_NAMES, k=3))

    for drug in DRUG_NAMES:
        if drug in fast_movers:
            qty = random.choice([15, 20, 25])
        else:
            qty = random.choice([45, 80, 120, 200])
        threshold = 50
        expiry = today + timedelta(days=random.randint(30, 540))
        vendor_id = random.choice(vendor_ids)
        institution_id = random.choice(institution_ids)
        # Weight toward "Passed" but seed some Pending/Failed so QC is visibly in use
        qc_status = random.choices(QC_STATUSES, weights=[70, 20, 10])[0]
        category = categorize_drug(drug)
        cur.execute("""
            INSERT INTO inventory (drug_name, batch_no, quantity, reorder_threshold,
                                    expiry_date, vendor_id, institution_id, qc_status, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (drug, f"B{random.randint(1000,9999)}", qty, threshold,
              expiry.isoformat(), vendor_id, institution_id, qc_status, category))
        inv_id = cur.lastrowid
        inventory_ids.append(inv_id)
        inventory_institution_map[inv_id] = institution_id
        if drug in fast_movers:
            # remember by id for the consumption-seeding step below
            pass

    # Map fast-mover drug names to their inventory ids for guaranteed high consumption
    fast_mover_ids = [
        row[0] for row in cur.execute(
            f"SELECT id FROM inventory WHERE drug_name IN ({','.join('?' for _ in fast_movers)})",
            tuple(fast_movers)
        ).fetchall()
    ]

    # Historical consumption transactions over the last 14 days, spread across
    # institutions, so the consumption-trend chart and reorder suggestions have
    # real shape from the start. Fast movers are consumed every day with a
    # deterministic minimum amount, guaranteeing the reorder-suggestion feature
    # has something to show on every run.
    for day_offset in range(14, 0, -1):
        txn_date = (today - timedelta(days=day_offset)).isoformat()

        for inv_id in fast_mover_ids:
            amount = random.randint(10, 18)  # consumed every day, no probability gate
            cur.execute("""
                INSERT INTO transactions (inventory_id, change_qty, reason, txn_date)
                VALUES (?, ?, ?, ?)
            """, (inv_id, -amount, "Dispensed to patient", txn_date))

        # Everything else: light, occasional consumption
        for _ in range(random.randint(1, 3)):
            inv_id = random.choice(inventory_ids)
            amount = random.randint(1, 6)
            cur.execute("""
                INSERT INTO transactions (inventory_id, change_qty, reason, txn_date)
                VALUES (?, ?, ?, ?)
            """, (inv_id, -amount, "Dispensed to patient", txn_date))

    # A couple of sample shipments in flight, with expected delivery dates so
    # vendor on-time performance can be computed.
    for _ in range(6):
        drug = random.choice(DRUG_NAMES)
        order_date = today - timedelta(days=random.randint(1, 15))
        expected = order_date + timedelta(days=5)
        status = random.choice(SHIPMENT_STATUSES)
        delivered_date = None
        if status == "Delivered":
            # Randomly on-time or late, so the demo shows a realistic mix
            delivered_date = (expected + timedelta(days=random.choice([-1, 0, 0, 2, 4]))).isoformat()
        cur.execute("""
            INSERT INTO shipments (drug_name, quantity, vendor_id, institution_id, status,
                                    order_date, expected_delivery_date, delivered_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (drug, random.choice([50, 100, 150]), random.choice(vendor_ids),
              random.choice(institution_ids), status,
              order_date.isoformat(), expected.isoformat(), delivered_date))

    conn.commit()


# ---------- Query helpers ----------

def get_inventory_df(institution_id=None):
    """institution_id=None returns all institutions pooled; pass an id to scope to one."""
    import pandas as pd
    conn = get_connection()
    query = """
        SELECT inv.id, inv.drug_name, inv.batch_no, inv.quantity, inv.reorder_threshold,
               inv.expiry_date, inv.qc_status, inv.category, v.name AS vendor, i.name AS institution
        FROM inventory inv
        LEFT JOIN vendors v ON inv.vendor_id = v.id
        LEFT JOIN institutions i ON inv.institution_id = i.id
    """
    params = ()
    if institution_id is not None:
        query += " WHERE inv.institution_id = ?"
        params = (institution_id,)
    query += " ORDER BY inv.drug_name"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_shipments_df():
    import pandas as pd
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT s.id, s.drug_name, s.quantity,
               s.source_type,
               COALESCE(v.name, src_inst.name) AS source,
               dest.name AS institution,
               s.status, s.order_date, s.expected_delivery_date, s.delivered_date
        FROM shipments s
        LEFT JOIN vendors v ON s.vendor_id = v.id
        LEFT JOIN inventory src_inv ON s.source_inventory_id = src_inv.id
        LEFT JOIN institutions src_inst ON src_inv.institution_id = src_inst.id
        LEFT JOIN institutions dest ON s.institution_id = dest.id
        ORDER BY s.order_date DESC
    """, conn)
    conn.close()
    return df


def get_vendors():
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM vendors").fetchall()
    conn.close()
    return [(r["id"], r["name"]) for r in rows]


def get_institutions():
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM institutions").fetchall()
    conn.close()
    return [(r["id"], r["name"]) for r in rows]


def add_inventory_item(drug_name, batch_no, quantity, threshold, expiry_date, vendor_id, institution_id, category=None):
    if not category:
        category = categorize_drug(drug_name)
    conn = get_connection()
    conn.execute("""
        INSERT INTO inventory (drug_name, batch_no, quantity, reorder_threshold,
                                expiry_date, vendor_id, institution_id, category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (drug_name, batch_no, quantity, threshold, expiry_date, vendor_id, institution_id, category))
    conn.commit()
    conn.close()


def consume_stock(inventory_id, amount, reason="Dispensed to patient"):
    """
    Raises InsufficientStockError if amount exceeds what's on hand — mirrors the
    same check create_transfer_shipment() does, so stock can never go negative
    from either path.
    """
    inventory_id = int(inventory_id)
    amount = int(amount)
    conn = get_connection()

    row = conn.execute("SELECT quantity FROM inventory WHERE id = ?", (inventory_id,)).fetchone()
    if row is None:
        conn.close()
        raise ValueError("Inventory item not found.")
    if row["quantity"] < amount:
        conn.close()
        raise InsufficientStockError(
            f"Only {row['quantity']} units available, cannot dispense {amount}."
        )

    conn.execute("UPDATE inventory SET quantity = quantity - ? WHERE id = ?", (amount, inventory_id))
    conn.execute("""
        INSERT INTO transactions (inventory_id, change_qty, reason, txn_date)
        VALUES (?, ?, ?, ?)
    """, (inventory_id, -amount, reason, date.today().isoformat()))
    conn.commit()
    conn.close()


def create_shipment(drug_name, quantity, vendor_id, institution_id, lead_time_days=5):
    """Creates a shipment FROM a vendor TO an institution. No existing stock is
    consumed — this represents new stock entering the system via procurement."""
    conn = get_connection()
    order_date = date.today()
    expected = order_date + timedelta(days=lead_time_days)
    conn.execute("""
        INSERT INTO shipments (drug_name, quantity, vendor_id, institution_id, status,
                                order_date, expected_delivery_date, source_type)
        VALUES (?, ?, ?, ?, 'Ordered', ?, ?, 'Vendor')
    """, (drug_name, quantity, vendor_id, institution_id, order_date.isoformat(), expected.isoformat()))
    conn.commit()
    conn.close()


class InsufficientStockError(Exception):
    pass


def create_transfer_shipment(source_inventory_id, quantity, destination_institution_id, lead_time_days=2):
    """
    Creates a shipment that transfers existing stock FROM one institution's inventory
    TO another institution — unlike a vendor shipment, this immediately subtracts the
    quantity from the source (it's real stock leaving that location right now, not a
    new order arriving later). The destination only receives it once the shipment is
    marked Delivered, same as any other shipment.
    Raises InsufficientStockError if the source doesn't have enough quantity on hand.
    """
    source_inventory_id = int(source_inventory_id)
    quantity = int(quantity)
    conn = get_connection()

    source_row = conn.execute("SELECT * FROM inventory WHERE id = ?", (source_inventory_id,)).fetchone()
    if source_row is None:
        conn.close()
        raise ValueError("Source inventory item not found.")
    if source_row["quantity"] < quantity:
        conn.close()
        raise InsufficientStockError(
            f"Only {source_row['quantity']} units available, cannot transfer {quantity}."
        )

    drug_name = source_row["drug_name"]
    order_date = date.today()
    expected = order_date + timedelta(days=lead_time_days)

    # Subtract from source immediately — this stock has physically left that location.
    conn.execute("UPDATE inventory SET quantity = quantity - ? WHERE id = ?", (quantity, source_inventory_id))
    conn.execute("""
        INSERT INTO transactions (inventory_id, change_qty, reason, txn_date)
        VALUES (?, ?, ?, ?)
    """, (source_inventory_id, -quantity, "Transferred to another institution", order_date.isoformat()))

    conn.execute("""
        INSERT INTO shipments (drug_name, quantity, vendor_id, institution_id, status,
                                order_date, expected_delivery_date, source_type, source_inventory_id)
        VALUES (?, ?, NULL, ?, 'Ordered', ?, ?, 'Institution', ?)
    """, (drug_name, quantity, destination_institution_id, order_date.isoformat(), expected.isoformat(),
          source_inventory_id))

    conn.commit()
    conn.close()


def update_shipment_status(shipment_id, new_status, add_to_inventory_id=None):
    shipment_id = int(shipment_id)
    if add_to_inventory_id is not None:
        add_to_inventory_id = int(add_to_inventory_id)
    conn = get_connection()
    conn.execute("UPDATE shipments SET status = ? WHERE id = ?", (new_status, shipment_id))

    if new_status == "Delivered":
        conn.execute("UPDATE shipments SET delivered_date = ? WHERE id = ?",
                     (date.today().isoformat(), shipment_id))

    if new_status == "Delivered" and add_to_inventory_id is not None:
        shipment = conn.execute("SELECT quantity FROM shipments WHERE id = ?", (shipment_id,)).fetchone()
        conn.execute("UPDATE inventory SET quantity = quantity + ? WHERE id = ?",
                     (shipment["quantity"], add_to_inventory_id))
        conn.execute("""
            INSERT INTO transactions (inventory_id, change_qty, reason, txn_date)
            VALUES (?, ?, ?, ?)
        """, (add_to_inventory_id, shipment["quantity"], "Shipment delivered", date.today().isoformat()))

    conn.commit()
    conn.close()


def update_qc_status(inventory_id, new_status):
    inventory_id = int(inventory_id)
    conn = get_connection()
    conn.execute("UPDATE inventory SET qc_status = ? WHERE id = ?", (new_status, inventory_id))
    conn.commit()
    conn.close()


def get_transactions_df(
    institution_id=None,
    drug_names=None,
    date_from=None,
    date_to=None,
    reasons=None,
):
    """All stock movements with drug/institution context, newest first.
    institution_id=None returns all institutions; pass an id to scope to one."""
    import pandas as pd
    conn = get_connection()
    query = """
        SELECT t.id, t.txn_date, inv.drug_name, inv.batch_no,
               i.name AS institution, t.change_qty, t.reason
        FROM transactions t
        JOIN inventory inv ON t.inventory_id = inv.id
        LEFT JOIN institutions i ON inv.institution_id = i.id
        WHERE 1=1
    """
    params = []
    if institution_id is not None:
        query += " AND inv.institution_id = ?"
        params.append(institution_id)
    if drug_names:
        placeholders = ",".join("?" for _ in drug_names)
        query += f" AND inv.drug_name IN ({placeholders})"
        params.extend(drug_names)
    if date_from is not None:
        query += " AND t.txn_date >= ?"
        params.append(date_from)
    if date_to is not None:
        query += " AND t.txn_date <= ?"
        params.append(date_to)
    if reasons:
        placeholders = ",".join("?" for _ in reasons)
        query += f" AND t.reason IN ({placeholders})"
        params.extend(reasons)
    query += " ORDER BY t.txn_date DESC, t.id DESC"
    df = pd.read_sql_query(query, conn, params=tuple(params) if params else ())
    conn.close()
    if len(df) > 0:
        df["direction"] = df["change_qty"].apply(lambda q: "Out" if q < 0 else "In")
    return df


def get_transaction_filter_options():
    """Distinct drug names and reasons present in the transactions log."""
    conn = get_connection()
    drugs = [r["drug_name"] for r in conn.execute("""
        SELECT DISTINCT inv.drug_name
        FROM transactions t
        JOIN inventory inv ON t.inventory_id = inv.id
        ORDER BY inv.drug_name
    """).fetchall()]
    reasons = [r["reason"] for r in conn.execute(
        "SELECT DISTINCT reason FROM transactions ORDER BY reason"
    ).fetchall()]
    conn.close()
    return drugs, reasons


def get_consumption_trend_df(days=14, institution_id=None):
    """Daily consumption (absolute units dispensed) grouped by institution, for trend charting.
    institution_id=None returns all institutions pooled; pass an id to scope to one."""
    import pandas as pd
    conn = get_connection()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    query = """
        SELECT t.txn_date AS date, i.name AS institution, SUM(-t.change_qty) AS consumed
        FROM transactions t
        JOIN inventory inv ON t.inventory_id = inv.id
        JOIN institutions i ON inv.institution_id = i.id
        WHERE t.change_qty < 0 AND t.txn_date >= ?
    """
    params = [cutoff]
    if institution_id is not None:
        query += " AND inv.institution_id = ?"
        params.append(institution_id)
    query += " GROUP BY t.txn_date, i.name ORDER BY t.txn_date"
    df = pd.read_sql_query(query, conn, params=tuple(params))
    conn.close()
    return df


def get_vendor_performance_df(institution_id=None):
    """Per-vendor shipment counts and on-time delivery rate.
    institution_id=None returns all institutions pooled; pass an id to scope to one.
    The institution filter lives in the JOIN condition (not a WHERE clause) so a
    vendor with zero shipments to that institution still shows up with 0 rather
    than disappearing from the table entirely."""
    import pandas as pd
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT v.name AS vendor,
               COUNT(s.id) AS total_shipments,
               SUM(CASE WHEN s.status = 'Delivered' THEN 1 ELSE 0 END) AS delivered,
               SUM(CASE WHEN s.status = 'Delivered' AND s.delivered_date <= s.expected_delivery_date
                        THEN 1 ELSE 0 END) AS on_time
        FROM vendors v
        LEFT JOIN shipments s ON s.vendor_id = v.id AND (? IS NULL OR s.institution_id = ?)
        GROUP BY v.name
    """, conn, params=(institution_id, institution_id))
    conn.close()
    df["on_time_rate_pct"] = df.apply(
        lambda r: round(100 * r["on_time"] / r["delivered"], 1) if r["delivered"] > 0 else None, axis=1
    )
    return df


def get_qc_pending_count(institution_id=None):
    """institution_id=None counts across all institutions; pass an id to scope to one."""
    conn = get_connection()
    if institution_id is not None:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM inventory WHERE qc_status != 'Passed' AND institution_id = ?",
            (institution_id,)
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS c FROM inventory WHERE qc_status != 'Passed'").fetchone()
    conn.close()
    return row["c"]


def get_expiry_notifications_df(urgent_days=30, watch_days=90, institution_id=None):
    """
    Returns inventory items expiring within `watch_days`, each tagged with an
    urgency tier and how many units are at risk — so the notification says not
    just "this drug is expiring" but "this many units, worth alerting on."
    institution_id=None returns all institutions pooled; pass an id to scope to one.
    """
    import pandas as pd
    conn = get_connection()
    cutoff = (date.today() + timedelta(days=watch_days)).isoformat()
    today_str = date.today().isoformat()
    query = """
        SELECT inv.id, inv.drug_name, inv.batch_no, inv.quantity, inv.expiry_date,
               inv.category, i.name AS institution
        FROM inventory inv
        LEFT JOIN institutions i ON inv.institution_id = i.id
        WHERE inv.expiry_date <= ? AND inv.expiry_date >= ? AND inv.quantity > 0
    """
    params = [cutoff, today_str]
    if institution_id is not None:
        query += " AND inv.institution_id = ?"
        params.append(institution_id)
    query += " ORDER BY inv.expiry_date"
    df = pd.read_sql_query(query, conn, params=tuple(params))
    conn.close()

    if len(df) == 0:
        df["days_until_expiry"] = []
        df["urgency"] = []
        return df

    df["days_until_expiry"] = df["expiry_date"].apply(
        lambda d: (date.fromisoformat(d) - date.today()).days
    )
    df["urgency"] = df["days_until_expiry"].apply(
        lambda d: "Urgent" if d <= urgent_days else "Watch"
    )
    return df


def get_reorder_suggestions_df(history_days=14, safety_factor=1.2, institution_id=None):
    """
    Suggests a reorder quantity per inventory item based on its actual recent
    consumption rate and its vendor's lead time — instead of a static threshold.

    suggested_qty = ceil(avg_daily_consumption * vendor_lead_time_days * safety_factor) - current_quantity
    Only returned when this is positive (i.e., current stock won't last through the lead time).
    institution_id=None returns all institutions pooled; pass an id to scope to one.
    """
    import pandas as pd
    import math
    conn = get_connection()
    query = """
        WITH consumption AS (
            SELECT inventory_id, SUM(-change_qty) AS total_consumed
            FROM transactions
            WHERE change_qty < 0 AND txn_date >= date('now', ?)
            GROUP BY inventory_id
        )
        SELECT inv.id, inv.drug_name, inv.quantity, inv.reorder_threshold,
               v.name AS vendor, v.lead_time_days,
               COALESCE(c.total_consumed, 0) AS total_consumed
        FROM inventory inv
        LEFT JOIN vendors v ON inv.vendor_id = v.id
        LEFT JOIN consumption c ON c.inventory_id = inv.id
    """
    params = [f"-{history_days} days"]
    if institution_id is not None:
        query += " WHERE inv.institution_id = ?"
        params.append(institution_id)
    df = pd.read_sql_query(query, conn, params=tuple(params))
    conn.close()

    df["avg_daily_consumption"] = (df["total_consumed"] / history_days).round(2)
    df["days_of_stock_left"] = df.apply(
        lambda r: round(r["quantity"] / r["avg_daily_consumption"], 1) if r["avg_daily_consumption"] > 0 else None,
        axis=1
    )
    df["suggested_reorder_qty"] = df.apply(
        lambda r: max(0, math.ceil(r["avg_daily_consumption"] * r["lead_time_days"] * safety_factor) - r["quantity"])
        if r["avg_daily_consumption"] > 0 else 0,
        axis=1
    )
    return df[df["suggested_reorder_qty"] > 0].sort_values("days_of_stock_left")


# ---------- Bulk CSV import ----------

def get_or_create_vendor(conn, name, lead_time_days=5):
    name = str(name).strip()
    row = conn.execute("SELECT id FROM vendors WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO vendors (name, lead_time_days) VALUES (?, ?)", (name, lead_time_days))
    return cur.lastrowid


def get_or_create_institution(conn, name):
    name = str(name).strip()
    row = conn.execute("SELECT id FROM institutions WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO institutions (name) VALUES (?)", (name,))
    return cur.lastrowid


INVENTORY_CSV_COLUMNS = [
    "drug_name", "batch_no", "quantity", "reorder_threshold",
    "expiry_date", "vendor_name", "institution_name", "qc_status", "category",
]

SHIPMENT_CSV_COLUMNS = [
    "drug_name", "quantity", "vendor_name", "institution_name",
    "status", "order_date", "expected_delivery_date", "delivered_date",
]


def bulk_import_inventory(df):
    """
    Imports a DataFrame of inventory rows. Expected columns: INVENTORY_CSV_COLUMNS.
    qc_status defaults to 'Passed' if missing/blank.
    vendor_name / institution_name are matched by exact name, auto-created if new.
    Returns (success_count, list_of_error_strings) — never raises on a bad row,
    so one malformed row doesn't block the rest of the file.
    """
    conn = get_connection()
    success = 0
    errors = []
    for idx, row in df.iterrows():
        try:
            drug_name = str(row["drug_name"]).strip()
            batch_no = str(row["batch_no"]).strip()
            quantity = int(row["quantity"])
            threshold = int(row["reorder_threshold"]) if not pd_isna(row.get("reorder_threshold")) else 50
            expiry_date = str(row["expiry_date"]).strip()
            qc_status = str(row["qc_status"]).strip() if not pd_isna(row.get("qc_status")) else "Passed"
            if qc_status not in QC_STATUSES:
                qc_status = "Passed"
            category = str(row["category"]).strip() if not pd_isna(row.get("category")) else categorize_drug(drug_name)
            if category not in DRUG_CATEGORIES:
                category = categorize_drug(drug_name)

            vendor_id = get_or_create_vendor(conn, row["vendor_name"]) if not pd_isna(row.get("vendor_name")) else None
            institution_id = get_or_create_institution(conn, row["institution_name"]) if not pd_isna(row.get("institution_name")) else None

            conn.execute("""
                INSERT INTO inventory (drug_name, batch_no, quantity, reorder_threshold,
                                        expiry_date, vendor_id, institution_id, qc_status, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (drug_name, batch_no, quantity, threshold, expiry_date, vendor_id, institution_id, qc_status, category))
            success += 1
        except Exception as e:
            errors.append(f"Row {idx + 2}: {e}")  # +2 accounts for header row + 0-index
    conn.commit()
    conn.close()
    return success, errors


def bulk_import_shipments(df):
    """
    Imports a DataFrame of shipment rows. Expected columns: SHIPMENT_CSV_COLUMNS.
    status defaults to 'Ordered', order_date defaults to today,
    expected_delivery_date auto-computed from vendor lead time if missing.
    Returns (success_count, list_of_error_strings).
    """
    conn = get_connection()
    success = 0
    errors = []
    for idx, row in df.iterrows():
        try:
            drug_name = str(row["drug_name"]).strip()
            quantity = int(row["quantity"])
            vendor_id = get_or_create_vendor(conn, row["vendor_name"]) if not pd_isna(row.get("vendor_name")) else None
            institution_id = get_or_create_institution(conn, row["institution_name"]) if not pd_isna(row.get("institution_name")) else None

            status = str(row["status"]).strip() if not pd_isna(row.get("status")) else "Ordered"
            if status not in SHIPMENT_STATUSES:
                status = "Ordered"

            order_date = str(row["order_date"]).strip() if not pd_isna(row.get("order_date")) else date.today().isoformat()

            if not pd_isna(row.get("expected_delivery_date")):
                expected = str(row["expected_delivery_date"]).strip()
            else:
                lead_time = 5
                if vendor_id is not None:
                    vrow = conn.execute("SELECT lead_time_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
                    if vrow:
                        lead_time = vrow["lead_time_days"]
                expected = (date.fromisoformat(order_date) + timedelta(days=lead_time)).isoformat()

            delivered_date = str(row["delivered_date"]).strip() if not pd_isna(row.get("delivered_date")) else None

            conn.execute("""
                INSERT INTO shipments (drug_name, quantity, vendor_id, institution_id, status,
                                        order_date, expected_delivery_date, delivered_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (drug_name, quantity, vendor_id, institution_id, status, order_date, expected, delivered_date))
            success += 1
        except Exception as e:
            errors.append(f"Row {idx + 2}: {e}")
    conn.commit()
    conn.close()
    return success, errors


def pd_isna(val):
    """Local wrapper so this module doesn't need pandas imported at module level."""
    import pandas as pd
    return pd.isna(val) if val is not None else True
