"""
app.py
PSS04 — Drug Inventory and Supply Chain Tracking System (Prototype)

Run with:  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, timedelta

import database as db
import nl_query

st.set_page_config(page_title="TrackRx — Drug Supply Chain", layout="wide", page_icon="⛑")
db.init_db()

# ---------------------------------------------------------------
# DESIGN SYSTEM
# Palette: clinical teal + rust-amber status accents (deliberately not the
# generic cream/terracotta or dark/neon AI-default looks).
# Type: IBM Plex family — Serif for headers (documentation/pharmacopoeia
# feel), Sans for UI, Mono for batch codes and quantities (data should
# read like data).
# ---------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Serif:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
h1, h2, h3 { font-family: 'IBM Plex Serif', serif !important; font-weight: 600 !important; letter-spacing: -0.01em; }

/* Branded header banner, styled like a batch-tracking label strip */
.trx-header {
    background: linear-gradient(135deg, #0B5D5D 0%, #0E7A7A 100%);
    border-radius: 10px;
    padding: 22px 28px;
    margin-bottom: 22px;
    border-left: 6px dashed #C98A1F;
}
.trx-header h1 {
    color: #FFFFFF !important;
    margin: 0 !important;
    font-size: 1.6rem !important;
}
.trx-header p {
    color: #D7E8E8;
    margin: 4px 0 0 0;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #0B5D5D;
}
section[data-testid="stSidebar"] * { color: #EDF2F2 !important; }
section[data-testid="stSidebar"] .stRadio label { font-family: 'IBM Plex Sans', sans-serif; }

/* Confirmed via devtools: the visible "Pharmacist / Store Staff" text is
   the value of the search <input> itself (its background is transparent),
   and the wildcard rule above was winning against its own dark color. The
   white box behind it comes from some ancestor div whose exact nesting
   level varies, so we paint every div inside the select control instead
   of guessing one specific level, and fix the input's text color directly. */
section[data-testid="stSidebar"] div[data-testid="stSelectbox"] input[role="combobox"] {
    color: #1B2B2B !important;
    -webkit-text-fill-color: #1B2B2B !important;
}
section[data-testid="stSidebar"] div[data-testid="stSelectbox"] div[data-baseweb="select"],
section[data-testid="stSidebar"] div[data-testid="stSelectbox"] div[data-baseweb="select"] div {
    background-color: #FFFFFF !important;
    border-color: #DCE4E4 !important;
}

/* Metric cards */
div[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #DCE4E4;
    border-radius: 8px;
    padding: 14px 16px;
}
div[data-testid="stMetricValue"] { font-family: 'IBM Plex Mono', monospace; }

/* Numeric/code-like columns render in mono where we tag them */
.trx-mono { font-family: 'IBM Plex Mono', monospace; }
</style>
""", unsafe_allow_html=True)


def flash(message, kind="success"):
    """
    Stash a message in session_state to survive an immediate st.rerun().
    st.success() etc. render for a split second and vanish on rerun because
    rerun restarts the script from scratch — this persists the message into
    the next run instead, where render_flash() displays and clears it.
    """
    st.session_state["_flash"] = (kind, message)


def render_flash():
    flash_msg = st.session_state.pop("_flash", None)
    if flash_msg:
        kind, message = flash_msg
        getattr(st, kind)(message)


def page_header(title, subtitle):
    st.markdown(f"""
    <div class="trx-header">
        <h1>{title}</h1>
        <p>{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)


def style_status_column(df, column, color_map, default="#E8EBEB"):
    """Returns a pandas Styler that colors a status column's cells like pharmacy label chips."""
    def _color(val):
        bg = color_map.get(val, default)
        return f"background-color: {bg}; color: #1B2B2B; font-weight: 600; border-radius: 4px;"
    styler = df.style
    if hasattr(styler, "map"):          # pandas >= 2.1
        return styler.map(_color, subset=[column])
    return styler.applymap(_color, subset=[column])  # pandas < 2.1


QC_COLORS = {"Passed": "#CDE9DC", "Pending": "#F5E1B8", "Failed": "#F3CFC9"}
SHIPMENT_COLORS = {"Ordered": "#E3E9F5", "Shipped": "#F5E1B8", "Delivered": "#CDE9DC"}
URGENCY_COLORS = {"Urgent": "#F3CFC9", "Watch": "#F5E1B8"}
REASON_COLORS = {
    "Dispensed to patient": "#E3E9F5",
    "Transferred to another institution": "#F5E1B8",
    "Shipment delivered": "#CDE9DC",
}

# Shared column label map so every table renders human-readable headers
# instead of raw SQL/DataFrame column names (e.g. "drug_name" -> "Drug Name").
COLUMN_LABELS = {
    "id": "ID",
    "drug_name": "Drug Name",
    "batch_no": "Batch No.",
    "quantity": "Quantity",
    "reorder_threshold": "Reorder Threshold",
    "expiry_date": "Expiry Date",
    "qc_status": "QC Status",
    "vendor": "Vendor",
    "institution": "Institution",
    "status": "Status",
    "order_date": "Order Date",
    "expected_delivery_date": "Expected Delivery",
    "delivered_date": "Delivered On",
    "total_shipments": "Total Shipments",
    "delivered": "Delivered",
    "on_time_rate_pct": "On-Time Rate (%)",
    "avg_daily_consumption": "Avg Daily Use",
    "days_of_stock_left": "Days of Stock Left",
    "lead_time_days": "Vendor Lead Time (Days)",
    "suggested_reorder_qty": "Suggested Reorder Qty",
    "category": "Category",
    "source_type": "Source Type",
    "source": "Source",
    "days_until_expiry": "Days Until Expiry",
    "urgency": "Urgency",
    "txn_date": "Date",
    "change_qty": "Qty Change",
    "reason": "Reason",
    "direction": "Direction",
}


def pretty(df):
    """Rename a DataFrame's columns to their display labels, leaving unmapped columns as-is."""
    return df.rename(columns=COLUMN_LABELS)


# ---------------------------------------------------------------
# ROLE SIMULATION
# This is a UI-level simulation, not real authentication — no login, no
# security. It exists to demonstrate that different real-world users (a
# pharmacist recording consumption vs. a procurement officer creating
# shipments) would only need — and only see — a scoped slice of the system.
# ---------------------------------------------------------------
ROLES = [
    "Full Access (Demo Mode)",
    "Pharmacist / Store Staff",
    "Procurement Officer",
    "QC / Compliance Staff",
    "Institution Admin",
]

ROLE_PAGES = {
    "Full Access (Demo Mode)": ["Dashboard", "Ask TrackRx", "Inventory", "Shipments", "Activity Log", "Reset Demo Data"],
    "Pharmacist / Store Staff": ["Inventory", "Activity Log", "Ask TrackRx"],
    "Procurement Officer": ["Dashboard", "Ask TrackRx", "Shipments", "Activity Log"],
    "QC / Compliance Staff": ["Inventory", "Activity Log", "Ask TrackRx"],
    "Institution Admin": ["Dashboard", "Ask TrackRx", "Activity Log"],
}

ROLE_INVENTORY_TABS = {
    "Full Access (Demo Mode)": ["Current Stock", "Record Consumption", "Update QC Status", "Add New Batch", "Bulk Upload (CSV)"],
    "Pharmacist / Store Staff": ["Current Stock", "Record Consumption", "Add New Batch"],
    "QC / Compliance Staff": ["Current Stock", "Update QC Status"],
}

st.sidebar.markdown("### ⛑ TrackRx")
st.sidebar.caption("Drug Inventory & Supply Chain Tracking — PSS04")
role = st.sidebar.selectbox("View as", ROLES, index=0)
st.sidebar.caption("Role simulation for demo purposes — not real access control.")
available_pages = ROLE_PAGES[role]
page = st.sidebar.radio("Navigate", available_pages)

# Institution Admin is scoped to a single institution — the "seat" they hold —
# rather than seeing every institution pooled together. This picker simulates
# which institution that admin belongs to; every Dashboard query below is
# filtered by it, so switching this dropdown is like logging in as a different
# admin.
admin_institution_id = None
admin_institution_name = None
if role == "Institution Admin":
    _admin_institutions = db.get_institutions()
    _admin_inst_names = [i[1] for i in _admin_institutions]
    admin_institution_name = st.sidebar.selectbox(
        "Administering Institution", _admin_inst_names, key="admin_institution_select"
    )
    admin_institution_id = dict((i[1], i[0]) for i in _admin_institutions)[admin_institution_name]
    st.sidebar.caption("Institution Admins only see their own institution's data.")

# ---------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------
render_flash()
if page == "Dashboard":
    page_header("Supply Chain Dashboard", "Real-time stock · consumption · vendor performance")
    if role != "Full Access (Demo Mode)":
        st.caption(f"Viewing as: **{role}**")

    # ---- Institution scope ----
    # Institution Admin is auto-scoped to the institution picked in the sidebar
    # (no "All Institutions" option — that's the whole point of the role).
    # Every other role that can see the Dashboard gets an optional filter, since
    # pooled-vs-single-institution is still a useful view for them.
    if role == "Institution Admin":
        institution_filter_id = admin_institution_id
        institution_filter_name = admin_institution_name
        st.info(f"🏥 Scoped to **{institution_filter_name}** — this role only sees its own institution's data.")
    else:
        dash_institutions = db.get_institutions()
        inst_options = ["All Institutions"] + [i[1] for i in dash_institutions]
        selected_inst = st.selectbox("Filter by institution", inst_options, key="dash_institution_filter")
        if selected_inst == "All Institutions":
            institution_filter_id = None
            institution_filter_name = None
        else:
            institution_filter_id = dict((i[1], i[0]) for i in dash_institutions)[selected_inst]
            institution_filter_name = selected_inst

    inv = db.get_inventory_df(institution_filter_id)

    low_stock = inv[inv["quantity"] <= inv["reorder_threshold"]]
    expiry_notifications = db.get_expiry_notifications_df(institution_id=institution_filter_id)
    urgent_expiry = expiry_notifications[expiry_notifications["urgency"] == "Urgent"] if len(expiry_notifications) else expiry_notifications
    units_at_risk = int(expiry_notifications["quantity"].sum()) if len(expiry_notifications) else 0

    qc_pending = db.get_qc_pending_count(institution_filter_id)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Drug Types Tracked", len(inv))
    col2.metric("⚠️ Items Below Reorder Threshold", len(low_stock))
    col3.metric("⏳ Units Expiring Within 90 Days", units_at_risk)
    col4.metric("🧪 Items Needing QC Review", qc_pending)

    if len(low_stock) > 0:
        st.error(f"**Stock Alert:** {len(low_stock)} item(s) are at or below their reorder threshold and need restocking.")
        st.dataframe(
            pretty(low_stock[["drug_name", "quantity", "reorder_threshold", "institution", "vendor"]]),
            use_container_width=True, hide_index=True
        )
    else:
        st.success("All stock levels are healthy.")

    st.subheader("🎯 Smart Reorder Suggestions")
    st.caption(
        "Unlike a fixed threshold, this factors in each drug's actual recent consumption rate "
        "and its vendor's lead time — so it flags items that will run out *before* the next "
        "shipment could realistically arrive, not just items already below a static number."
    )
    reorder = db.get_reorder_suggestions_df(institution_id=institution_filter_id)
    if len(reorder) > 0:
        st.dataframe(
            pretty(reorder[["drug_name", "quantity", "avg_daily_consumption", "days_of_stock_left",
                             "vendor", "lead_time_days", "suggested_reorder_qty"]]),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("No items currently need reordering based on consumption trends.")

    st.subheader("Stock Levels by Drug")
    fig = px.bar(
        inv.sort_values("quantity"), x="drug_name", y="quantity",
        color=(inv["quantity"] <= inv["reorder_threshold"]).map({True: "Low", False: "OK"}),
        color_discrete_map={"Low": "#e74c3c", "OK": "#2ecc71"},
        labels={"drug_name": "Drug", "quantity": "Quantity", "color": "Status"},
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("⏳ Expiry Notifications")
    st.caption(
        "Flags stock expiring within 90 days, split into Urgent (≤30 days) and Watch (31–90 days) — "
        "showing exact units at risk, not just a list of drug names."
    )
    if len(expiry_notifications) > 0:
        if len(urgent_expiry) > 0:
            urgent_units = int(urgent_expiry["quantity"].sum())
            st.error(f"**{len(urgent_expiry)} batch(es), {urgent_units} unit(s) expiring within 30 days.**")
        styled_expiry = style_status_column(
            pretty(expiry_notifications[["drug_name", "batch_no", "quantity", "expiry_date",
                                          "days_until_expiry", "institution", "urgency"]]),
            "Urgency", URGENCY_COLORS
        )
        st.dataframe(styled_expiry, use_container_width=True, hide_index=True)
    else:
        st.success("No stock expiring within the next 90 days.")

    if institution_filter_id is None:
        st.subheader("Consumption Pattern by Institution (last 14 days)")
    else:
        st.subheader(f"Consumption Pattern — {institution_filter_name} (last 14 days)")
    trend = db.get_consumption_trend_df(days=14, institution_id=institution_filter_id)
    if len(trend) > 0:
        fig2 = px.line(
            trend, x="date", y="consumed", color="institution", markers=True,
            labels={"consumed": "Units Dispensed", "date": "Date"},
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No consumption recorded yet — dispense some stock from the Inventory page to see the trend.")

    if institution_filter_id is None:
        st.subheader("Vendor Performance")
    else:
        st.subheader(f"Vendor Performance — shipments to {institution_filter_name}")
    vendor_perf = db.get_vendor_performance_df(institution_filter_id)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.dataframe(
            pretty(vendor_perf[["vendor", "total_shipments", "delivered", "on_time_rate_pct"]]),
            use_container_width=True, hide_index=True
        )
    with c2:
        chartable = vendor_perf.dropna(subset=["on_time_rate_pct"])
        if len(chartable) > 0:
            fig3 = px.bar(
                chartable, x="vendor", y="on_time_rate_pct",
                labels={"on_time_rate_pct": "On-Time Delivery Rate (%)", "vendor": "Vendor"},
                range_y=[0, 100],
            )
            st.plotly_chart(fig3, use_container_width=True)

# ---------------------------------------------------------------
# ASK TRACKRX (NATURAL LANGUAGE)
# ---------------------------------------------------------------
elif page == "Ask TrackRx":
    page_header("Ask TrackRx", "Natural-language queries · grounded in live inventory data")
    if role != "Full Access (Demo Mode)":
        st.caption(f"Viewing as: **{role}**")

    api_configured = bool(nl_query.get_api_key())
    if api_configured:
        st.success("AI mode active.")
    else:
        st.info(
            "Offline mode — set **`GEMINI_API_KEY`** as an environment variable or in "
            "`.streamlit/secrets.toml` for full natural-language answers. "
            "Offline mode still answers common questions from live data."
        )

    if role == "Institution Admin":
        nl_institution_id = admin_institution_id
        nl_institution_name = admin_institution_name
        st.caption(f"Data scoped to **{nl_institution_name}**.")
    else:
        nl_institutions = db.get_institutions()
        nl_inst_options = ["All Institutions"] + [i[1] for i in nl_institutions]
        nl_selected = st.selectbox("Scope data to institution", nl_inst_options, key="nl_institution_filter")
        if nl_selected == "All Institutions":
            nl_institution_id = None
            nl_institution_name = None
        else:
            nl_institution_id = dict((i[1], i[0]) for i in nl_institutions)[nl_selected]
            nl_institution_name = nl_selected

    st.markdown("**Try an example:**")
    ex_cols = st.columns(len(nl_query.EXAMPLE_QUESTIONS))
    for i, (col, example) in enumerate(zip(ex_cols, nl_query.EXAMPLE_QUESTIONS)):
        if col.button(example, key=f"nl_example_{i}"):
            st.session_state["nl_question"] = example

    default_q = st.session_state.get("nl_question", "")
    with st.form("nl_query_form", clear_on_submit=False):
        question = st.text_area(
            "Your question",
            value=default_q,
            placeholder='e.g. "Which drugs are critical this week?"',
            height=80,
        )
        submitted = st.form_submit_button("Ask TrackRx", type="primary")

    if submitted and question.strip():
        st.session_state["nl_question"] = question.strip()
        with st.spinner("Analyzing your inventory data…"):
            result = nl_query.answer_question(
                question.strip(),
                institution_id=nl_institution_id,
                institution_name=nl_institution_name,
            )

        if result.error:
            st.warning(result.error)
        if result.source == "ai":
            st.caption("Answer source: AI")
        else:
            st.caption("Answer source: Offline rule engine")

        st.markdown(result.answer)

        if result.snapshot:
            with st.expander("Data snapshot used (for transparency)"):
                st.json(result.snapshot)

# ---------------------------------------------------------------
# INVENTORY
# ---------------------------------------------------------------
elif page == "Inventory":
    page_header("Inventory Management", "Stock levels · batch tracking · quality control")
    if role != "Full Access (Demo Mode)":
        st.caption(f"Viewing as: **{role}** — some actions are hidden for this role.")

    tab_names = ROLE_INVENTORY_TABS.get(role, ROLE_INVENTORY_TABS["Full Access (Demo Mode)"])
    tabs = st.tabs(tab_names)
    tab_map = dict(zip(tab_names, tabs))

    if "Current Stock" in tab_map:
        with tab_map["Current Stock"]:
            inv = db.get_inventory_df()
            category_filter = st.multiselect("Filter by category", sorted(inv["category"].unique()), key="cat_filter")
            display_inv = inv[inv["category"].isin(category_filter)] if category_filter else inv
            styled = style_status_column(pretty(display_inv), "QC Status", QC_COLORS)
            st.dataframe(styled, use_container_width=True, hide_index=True)

    if "Record Consumption" in tab_map:
        with tab_map["Record Consumption"]:
            st.subheader("Record Stock Consumption")
            st.caption("Simulates drugs being dispensed to patients — watch the dashboard alert trigger if stock drops below threshold.")
            inv = db.get_inventory_df()
            options = {f"{row.drug_name} ({row.institution}) — {row.quantity} in stock": row.id for row in inv.itertuples()}
            chosen = st.selectbox("Select item", list(options.keys()))
            available = int(inv.loc[inv["id"] == options[chosen], "quantity"].iloc[0])
            if available <= 0:
                st.info("This item is out of stock — nothing left to dispense.")
            else:
                amount = st.number_input(
                    "Quantity dispensed", min_value=1, max_value=available, value=min(10, available), step=1
                )
                if st.button("Record Consumption"):
                    try:
                        db.consume_stock(options[chosen], amount)
                        flash(f"Recorded: {amount} units consumed. Check the Dashboard for updated alerts.")
                        st.rerun()
                    except db.InsufficientStockError as e:
                        st.error(f"Cannot record consumption: {e}")

    if "Update QC Status" in tab_map:
        with tab_map["Update QC Status"]:
            st.subheader("Update Quality-Control Status")
            st.caption("Simulates a QC check being logged against a received batch.")
            inv2 = db.get_inventory_df()
            qc_options = {f"{row.drug_name} — {row.batch_no}": row.id for row in inv2.itertuples()}
            qc_chosen = st.selectbox("Select batch", list(qc_options.keys()), key="qc_select")
            new_qc = st.selectbox("QC status", db.QC_STATUSES, key="qc_status_select")
            if st.button("Update QC Status"):
                db.update_qc_status(qc_options[qc_chosen], new_qc)
                flash(f"QC status updated to '{new_qc}'.")
                st.rerun()

    if "Add New Batch" in tab_map:
        with tab_map["Add New Batch"]:
            st.subheader("Add New Inventory Batch")
            drug_name = st.text_input("Drug name", key="new_drug_name")
            suggested_category = db.categorize_drug(drug_name) if drug_name else "Other"
            category_idx = db.DRUG_CATEGORIES.index(suggested_category) if suggested_category in db.DRUG_CATEGORIES else db.DRUG_CATEGORIES.index("Other")

            with st.form("add_inventory_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                batch_no = c1.text_input("Batch number")
                quantity = c2.number_input("Quantity", min_value=0, value=100)
                threshold = c1.number_input("Reorder threshold", min_value=0, value=50)
                expiry = c2.date_input("Expiry date", value=date.today() + timedelta(days=365))
                category_choice = c1.selectbox(
                    "Category (auto-suggested from drug name above)", db.DRUG_CATEGORIES, index=category_idx
                )

                vendors = db.get_vendors()
                institutions = db.get_institutions()
                vendor_choice = c2.selectbox("Vendor", [v[1] for v in vendors])
                institution_choice = c1.selectbox("Institution", [i[1] for i in institutions])

                submitted = st.form_submit_button("Add to Inventory")
                if submitted and drug_name and batch_no:
                    vendor_id = dict((v[1], v[0]) for v in vendors)[vendor_choice]
                    institution_id = dict((i[1], i[0]) for i in institutions)[institution_choice]
                    db.add_inventory_item(drug_name, batch_no, quantity, threshold,
                                           expiry.isoformat(), vendor_id, institution_id, category=category_choice)
                    flash(f"Added {quantity} units of {drug_name}.")
                    st.rerun()

    if "Bulk Upload (CSV)" in tab_map:
        with tab_map["Bulk Upload (CSV)"]:
            st.subheader("Bulk Upload Inventory from CSV")
            st.caption(
                "Faster than adding items one at a time. Required columns: drug_name, batch_no, "
                "quantity, expiry_date. Optional: reorder_threshold (defaults to 50), vendor_name and "
                "institution_name (new names are created automatically — no need to add them first), "
                "qc_status (defaults to Passed), category (auto-detected from drug name if left blank)."
            )

            template_df = pd.DataFrame([{
                "drug_name": "Paracetamol 500mg", "batch_no": "B1234", "quantity": 100,
                "reorder_threshold": 50, "expiry_date": "2027-01-01",
                "vendor_name": "Sunrise Pharma Distributors", "institution_name": "City General Hospital",
                "qc_status": "Passed", "category": "",
            }])
            st.download_button(
                "⬇ Download CSV Template",
                data=template_df.to_csv(index=False),
                file_name="inventory_upload_template.csv",
                mime="text/csv",
            )

            inv_upload_key = f"inv_csv_upload_{st.session_state.get('inv_csv_upload_version', 0)}"
            uploaded = st.file_uploader("Upload inventory CSV", type="csv", key=inv_upload_key)
            if uploaded is not None:
                try:
                    upload_df = pd.read_csv(uploaded)
                    missing = [c for c in ["drug_name", "batch_no", "quantity", "expiry_date"] if c not in upload_df.columns]
                    if missing:
                        st.error(f"CSV is missing required column(s): {', '.join(missing)}")
                    else:
                        st.write("Preview:")
                        st.dataframe(upload_df, use_container_width=True, hide_index=True)
                        if st.button("Import This File", key="import_inventory_btn"):
                            success, errors = db.bulk_import_inventory(upload_df)
                            if success:
                                flash(f"Imported {success} row(s) successfully.")
                            if errors:
                                st.warning(f"{len(errors)} row(s) failed and were skipped:")
                                for e in errors:
                                    st.text(e)
                            if success:
                                st.session_state["inv_csv_upload_version"] = st.session_state.get("inv_csv_upload_version", 0) + 1
                                st.rerun()
                except Exception as e:
                    st.error(f"Could not read this file: {e}")

# ---------------------------------------------------------------
# SHIPMENTS
# ---------------------------------------------------------------
elif page == "Shipments":
    page_header("Shipment & Transfer Tracking", "Vendor orders · inter-institution transfers · lead times")
    if role != "Full Access (Demo Mode)":
        st.caption(f"Viewing as: **{role}**")

    tab1, tab2, tab3 = st.tabs(["Active Shipments", "Create Shipment", "Bulk Upload (CSV)"])

    with tab1:
        ships = db.get_shipments_df()
        styled = style_status_column(pretty(ships), "Status", SHIPMENT_COLORS)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        st.subheader("Update Shipment Status")
        options = {f"#{row.id} — {row.drug_name} ({row.status}) [{row.source_type}]": row.id for row in ships.itertuples()}
        if options:
            chosen = st.selectbox("Select shipment", list(options.keys()))
            new_status = st.selectbox("New status", db.SHIPMENT_STATUSES)
            inv = db.get_inventory_df()
            inv_options = {f"{row.drug_name} — {row.institution}": row.id for row in inv.itertuples()}
            add_to = st.selectbox("If Delivered, add stock to which inventory item?", list(inv_options.keys()))
            if st.button("Update Status"):
                db.update_shipment_status(options[chosen], new_status, inv_options[add_to])
                flash(f"Shipment updated to '{new_status}'.")
                st.rerun()

    with tab2:
        shipment_type = st.radio(
            "Shipment Type",
            ["From Vendor (new stock)", "Transfer from another institution (existing stock)"],
            key="shipment_type_radio"
        )

        if shipment_type == "From Vendor (new stock)":
            with st.form("create_vendor_shipment_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                drug_name = c1.selectbox("Drug", db.DRUG_NAMES)
                quantity = c2.number_input("Quantity ordered", min_value=1, value=100)
                vendors = db.get_vendors()
                institutions = db.get_institutions()
                vendor_choice = c1.selectbox("Vendor", [v[1] for v in vendors])
                institution_choice = c2.selectbox("Destination institution", [i[1] for i in institutions])
                submitted = st.form_submit_button("Create Shipment")
                if submitted:
                    vendor_id = dict((v[1], v[0]) for v in vendors)[vendor_choice]
                    institution_id = dict((i[1], i[0]) for i in institutions)[institution_choice]
                    db.create_shipment(drug_name, quantity, vendor_id, institution_id)
                    flash("Vendor shipment created with status 'Ordered'.")
                    st.rerun()
        else:
            st.caption(
                "This subtracts the quantity from the source institution's stock immediately — "
                "it represents real stock physically leaving that location, not a new order arriving."
            )
            inv = db.get_inventory_df()
            with st.form("create_transfer_shipment_form", clear_on_submit=True):
                source_options = {
                    f"{row.drug_name} — {row.institution} ({row.quantity} in stock)": row.id
                    for row in inv.itertuples()
                }
                source_choice = st.selectbox("Transfer FROM (drug + institution)", list(source_options.keys()))
                quantity = st.number_input("Quantity to transfer", min_value=1, value=10)
                institutions = db.get_institutions()
                institution_choice = st.selectbox("Destination institution", [i[1] for i in institutions])
                submitted = st.form_submit_button("Create Transfer")
                if submitted:
                    source_id = source_options[source_choice]
                    dest_id = dict((i[1], i[0]) for i in institutions)[institution_choice]
                    try:
                        db.create_transfer_shipment(source_id, quantity, dest_id)
                        flash("Transfer created — stock has been subtracted from the source institution.")
                        st.rerun()
                    except db.InsufficientStockError as e:
                        st.error(f"Cannot create transfer: {e}")
                    except ValueError as e:
                        st.error(str(e))

    with tab3:
        st.subheader("Bulk Upload Shipments from CSV")
        st.caption(
            "Required columns: drug_name, quantity. Optional: vendor_name, institution_name "
            "(new names auto-created), status (defaults to Ordered), order_date (defaults to today), "
            "expected_delivery_date (auto-computed from vendor lead time if left blank), delivered_date."
        )

        ship_template_df = pd.DataFrame([{
            "drug_name": "Paracetamol 500mg", "quantity": 100,
            "vendor_name": "Sunrise Pharma Distributors", "institution_name": "City General Hospital",
            "status": "Ordered", "order_date": "", "expected_delivery_date": "", "delivered_date": "",
        }])
        st.download_button(
            "⬇ Download CSV Template",
            data=ship_template_df.to_csv(index=False),
            file_name="shipments_upload_template.csv",
            mime="text/csv",
        )

        ship_upload_key = f"ship_csv_upload_{st.session_state.get('ship_csv_upload_version', 0)}"
        ship_uploaded = st.file_uploader("Upload shipments CSV", type="csv", key=ship_upload_key)
        if ship_uploaded is not None:
            try:
                ship_upload_df = pd.read_csv(ship_uploaded)
                missing = [c for c in ["drug_name", "quantity"] if c not in ship_upload_df.columns]
                if missing:
                    st.error(f"CSV is missing required column(s): {', '.join(missing)}")
                else:
                    st.write("Preview:")
                    st.dataframe(ship_upload_df, use_container_width=True, hide_index=True)
                    if st.button("Import This File", key="import_shipments_btn"):
                        success, errors = db.bulk_import_shipments(ship_upload_df)
                        if success:
                            flash(f"Imported {success} row(s) successfully.")
                        if errors:
                            st.warning(f"{len(errors)} row(s) failed and were skipped:")
                            for e in errors:
                                st.text(e)
                        if success:
                            st.session_state["ship_csv_upload_version"] = st.session_state.get("ship_csv_upload_version", 0) + 1
                            st.rerun()
            except Exception as e:
                st.error(f"Could not read this file: {e}")

# ---------------------------------------------------------------
# ACTIVITY LOG
# ---------------------------------------------------------------
elif page == "Activity Log":
    page_header("Activity Log", "Stock movements · consumption · transfers · deliveries")
    if role != "Full Access (Demo Mode)":
        st.caption(f"Viewing as: **{role}**")

    if role == "Institution Admin":
        institution_filter_id = admin_institution_id
        institution_filter_name = admin_institution_name
        st.info(f"🏥 Scoped to **{institution_filter_name}** — this role only sees its own institution's data.")
    else:
        log_institutions = db.get_institutions()
        inst_options = ["All Institutions"] + [i[1] for i in log_institutions]
        selected_inst = st.selectbox("Filter by institution", inst_options, key="log_institution_filter")
        if selected_inst == "All Institutions":
            institution_filter_id = None
            institution_filter_name = None
        else:
            institution_filter_id = dict((i[1], i[0]) for i in log_institutions)[selected_inst]
            institution_filter_name = selected_inst

    available_drugs, available_reasons = db.get_transaction_filter_options()

    f1, f2, f3 = st.columns(3)
    with f1:
        drug_filter = st.multiselect("Filter by drug", available_drugs, key="log_drug_filter")
    with f2:
        reason_filter = st.multiselect("Filter by reason", available_reasons, key="log_reason_filter")
    with f3:
        default_from = date.today() - timedelta(days=30)
        date_range = st.date_input(
            "Date range",
            value=(default_from, date.today()),
            key="log_date_range",
        )

    date_from = date_to = None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        date_from, date_to = date_range[0].isoformat(), date_range[1].isoformat()
    elif isinstance(date_range, date):
        date_from = date_to = date_range.isoformat()

    log_df = db.get_transactions_df(
        institution_id=institution_filter_id,
        drug_names=drug_filter or None,
        date_from=date_from,
        date_to=date_to,
        reasons=reason_filter or None,
    )

    if len(log_df) > 0:
        units_out = int(log_df.loc[log_df["change_qty"] < 0, "change_qty"].abs().sum())
        units_in = int(log_df.loc[log_df["change_qty"] > 0, "change_qty"].sum())
        m1, m2, m3 = st.columns(3)
        m1.metric("Transactions", len(log_df))
        m2.metric("Units Out", units_out)
        m3.metric("Units In", units_in)

        display_cols = ["txn_date", "drug_name", "batch_no", "institution", "direction", "change_qty", "reason"]
        styled_log = style_status_column(pretty(log_df[display_cols]), "Reason", REASON_COLORS)
        st.dataframe(styled_log, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇ Export filtered log (CSV)",
            data=log_df[display_cols].to_csv(index=False),
            file_name="activity_log.csv",
            mime="text/csv",
            key="log_export_btn",
        )
    else:
        st.info("No transactions match the current filters.")

# ---------------------------------------------------------------
# RESET
# ---------------------------------------------------------------
elif page == "Reset Demo Data":
    page_header("Reset Demo Data", "Wipe and reseed all data")
    st.warning("This wipes all current data and reseeds fresh demo data. This cannot be undone.")
    if st.button("Reset now"):
        db.init_db(reset=True)
        flash("Data reset and reseeded.")
        st.rerun()
