import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# ---------- USER CREDENTIALS (Hardcoded for demo - Use Secrets in production) ----------
# To use Streamlit Secrets, replace this with: CREDENTIALS = st.secrets["users"]
CREDENTIALS = {
    "admin": {"password": "admin123", "role": "Admin"},
    "production": {"password": "prod123", "role": "Production"},
    "qa": {"password": "qa123", "role": "QA"}
}


# ---------- DATABASE SETUP ----------
def init_db():
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
                    recipe_id TEXT PRIMARY KEY,
                    colour_code TEXT UNIQUE,
                    colour_name TEXT,
                    tsc_min REAL, tsc_max REAL, ph_min REAL, ph_max REAL,
                    visc_min REAL, visc_max REAL, de_max REAL,
                    dl_tolerance REAL DEFAULT 0.5, da_tolerance REAL DEFAULT 0.6,
                    db_tolerance REAL DEFAULT 0.6, strength_min REAL DEFAULT 95.0,
                    strength_max REAL DEFAULT 105.0
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    batch_number TEXT UNIQUE, recipe_id TEXT, colour_code TEXT,
                    status TEXT, stage TEXT, tsc REAL, ph REAL, visc REAL,
                    de REAL, dl REAL, da REAL, db REAL, colour_strength REAL,
                    manufacturing_date TEXT, attempt_count INTEGER DEFAULT 0,
                    remark TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS seq_counter (
                    colour_code TEXT PRIMARY KEY, last_seq INTEGER DEFAULT 0
                )''')

    # Migration for existing columns
    for col in ['tsc_min', 'tsc_max', 'ph_min', 'ph_max', 'visc_min', 'visc_max', 'de_max']:
        try:
            c.execute(f"ALTER TABLE recipes ADD COLUMN {col} REAL")
        except:
            pass
    for col in ['dl', 'da', 'db', 'colour_strength']:
        try:
            c.execute(f"ALTER TABLE batches ADD COLUMN {col} REAL")
        except:
            pass
    for col in ['manufacturing_date', 'remark']:
        try:
            c.execute(f"ALTER TABLE batches ADD COLUMN {col} TEXT")
        except:
            pass
    try:
        c.execute("ALTER TABLE batches ADD COLUMN attempt_count INTEGER DEFAULT 0")
    except:
        pass

    # Set defaults to prevent NULL errors
    c.execute(
        "UPDATE recipes SET tsc_min = COALESCE(tsc_min, 40.0), tsc_max = COALESCE(tsc_max, 50.0), ph_min = COALESCE(ph_min, 7.5), ph_max = COALESCE(ph_max, 9.5), visc_min = COALESCE(visc_min, 1000.0), visc_max = COALESCE(visc_max, 1400.0), de_max = COALESCE(de_max, 1.0), dl_tolerance = COALESCE(dl_tolerance, 0.5), da_tolerance = COALESCE(da_tolerance, 0.6), db_tolerance = COALESCE(db_tolerance, 0.6), strength_min = COALESCE(strength_min, 95.0), strength_max = COALESCE(strength_max, 105.0)")
    conn.commit()
    conn.close()


# ---------- DATABASE FUNCTIONS ----------
def get_recipes():
    conn = sqlite3.connect('pigment.db')
    df = pd.read_sql_query("SELECT * FROM recipes ORDER BY colour_code", conn)
    conn.close()
    return df


def get_batches():
    conn = sqlite3.connect('pigment.db')
    df = pd.read_sql_query("SELECT * FROM batches ORDER BY created_at DESC", conn)
    conn.close()
    return df


def batch_exists(batch_number):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM batches WHERE batch_number = ?", (batch_number,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def add_recipe(colour_code, colour_name, tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max, de_max, dl_tol, da_tol,
               db_tol, str_min, str_max):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO recipes 
                 (recipe_id, colour_code, colour_name, tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max, de_max, dl_tolerance, da_tolerance, db_tolerance, strength_min, strength_max) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (colour_code, colour_code, colour_name, tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max, de_max,
               dl_tol, da_tol, db_tol, str_min, str_max))
    conn.commit()
    conn.close()


def add_batch(batch_number, recipe_id, colour_code, manufacturing_date):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    batch_id = f"b_{batch_number}"
    c.execute(
        "INSERT INTO batches (batch_id, batch_number, recipe_id, colour_code, status, stage, manufacturing_date) VALUES (?,?,?,?,?,?,?)",
        (batch_id, batch_number, recipe_id, colour_code, 'Issued', 'Mixing', manufacturing_date))
    conn.commit()
    conn.close()
    return batch_number


def update_status(batch_id, status, stage):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("UPDATE batches SET status=?, stage=? WHERE batch_id=?", (status, stage, batch_id))
    conn.commit()
    conn.close()


def update_qa(batch_id, tsc, ph, visc, de, dl, da, db, colour_strength, remark):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("""SELECT tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max, de_max, dl_tolerance, da_tolerance, db_tolerance, strength_min, strength_max
                 FROM recipes r JOIN batches b ON r.recipe_id = b.recipe_id WHERE b.batch_id = ?""", (batch_id,))
    row = c.fetchone()
    if not row: return "❌ Recipe not found!"
    tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max, de_max, dl_tol, da_tol, db_tol, str_min, str_max = row

    tsc_ok = tsc_min <= tsc <= tsc_max
    ph_ok = ph_min <= ph <= ph_max
    visc_ok = visc_min <= visc <= visc_max
    de_ok = de <= de_max
    dl_ok = abs(dl) <= dl_tol
    da_ok = abs(da) <= da_tol
    db_ok = abs(db) <= db_tol
    strength_ok = str_min <= colour_strength <= str_max
    passed = all([tsc_ok, ph_ok, visc_ok, de_ok, dl_ok, da_ok, db_ok, strength_ok])

    c.execute("SELECT attempt_count FROM batches WHERE batch_id = ?", (batch_id,))
    current_attempt = c.fetchone()[0] or 0
    new_attempt = current_attempt + 1

    if passed:
        status, stage, msg = 'QA_Passed', 'Finished', '✅ QA PASSED!'
    else:
        status, stage, msg = 'QA_Failed', 'Milling', '❌ QA FAILED! Back to Milling.'

    c.execute(
        """UPDATE batches SET tsc=?, ph=?, visc=?, de=?, dl=?, da=?, db=?, colour_strength=?, status=?, stage=?, attempt_count=?, remark=? WHERE batch_id=?""",
        (tsc, ph, visc, de, dl, da, db, colour_strength, status, stage, new_attempt, remark, batch_id))
    conn.commit()
    conn.close()
    return msg


# ---------- INIT DB ----------
init_db()


# ---------- LOGIN UI ----------
def login():
    st.set_page_config(page_title="Pigment Monitor", layout="wide")
    st.title("🔐 Pigment Dispersion System - Login")

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.username = None

    if not st.session_state.logged_in:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                if username in CREDENTIALS and CREDENTIALS[username]['password'] == password:
                    st.session_state.logged_in = True
                    st.session_state.role = CREDENTIALS[username]['role']
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Invalid username or password")
        st.stop()
    else:
        st.sidebar.success(f"Logged in as: **{st.session_state.username}** (Role: {st.session_state.role})")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.role = None
            st.session_state.username = None
            st.rerun()


# ---------- RUN LOGIN CHECK ----------
login()


# ---------- ROLE-BASED ACCESS CHECK ----------
def is_admin():
    return st.session_state.role == "Admin"


def is_production():
    return st.session_state.role == "Production"


def is_qa():
    return st.session_state.role == "QA"


# ---------- MAIN APP ----------
st.title("🎨 Pigment Dispersion System")

# Define Tabs conditionally based on Role
tabs_list = []

# Admin sees all 4 tabs
if is_admin():
    tabs_list = ["Define Recipe", "Issue Batch", "QA Testing", "WIP Progress"]
# Production sees Issue Batch and WIP only
elif is_production():
    tabs_list = ["Issue Batch", "WIP Progress"]
# QA sees QA Testing and WIP only
elif is_qa():
    tabs_list = ["QA Testing", "WIP Progress"]

tabs = st.tabs(tabs_list)

tab_index = 0

# ---------- TAB 1: DEFINE RECIPE (ADMIN ONLY) ----------
if is_admin():
    with tabs[tab_index]:
        st.header("📄 1. Define Recipe (Control Limits)")
        with st.form("recipe_form"):
            col_code = st.text_input("Colour Code (e.g., RED, PIG-001)")
            col_name = st.text_input("Colour Name", "Red Oxide")

            st.subheader("📊 Basic QC Specs (Ranges)")
            col1, col2 = st.columns(2)
            with col1:
                tsc_min = st.number_input("TSC Min (%)", value=43.0, step=0.1)
                ph_min = st.number_input("pH Min", value=8.0, step=0.1)
                visc_min = st.number_input("Viscosity Min (cP)", value=1100, step=10)
            with col2:
                tsc_max = st.number_input("TSC Max (%)", value=47.0, step=0.1)
                ph_max = st.number_input("pH Max", value=9.0, step=0.1)
                visc_max = st.number_input("Viscosity Max (cP)", value=1300, step=10)

            st.subheader("🎨 Colouristic Properties")
            col1, col2 = st.columns(2)
            with col1:
                de_max = st.number_input("DE Max (≤ value)", value=1.0, step=0.01)
                dl_tol = st.number_input("DL Tolerance (±)", value=0.5, step=0.1)
                da_tol = st.number_input("Da Tolerance (±)", value=0.6, step=0.1)
            with col2:
                db_tol = st.number_input("Db Tolerance (±)", value=0.6, step=0.1)
                str_min = st.number_input("Strength Min %", value=95.0, step=1.0)
                str_max = st.number_input("Strength Max %", value=105.0, step=1.0)

            if st.form_submit_button("Save Recipe"):
                if col_code:
                    add_recipe(col_code, col_name, tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max, de_max, dl_tol,
                               da_tol, db_tol, str_min, str_max)
                    st.toast(f"✅ Recipe for {col_code} saved!", icon="✅")
                    st.rerun()
    tab_index += 1

# ---------- TAB 2: ISSUE BATCH (ADMIN & PRODUCTION) ----------
if is_admin() or is_production():
    current_tab = tabs[tab_index]
    with current_tab:
        st.header("📄 2. Issue New Batch")
        recipes = get_recipes()
        if recipes.empty:
            st.warning("No recipes. Please ask Admin to add a recipe first.")
        else:
            unique_colours = recipes['colour_code'].unique().tolist()
            colour_filter = st.selectbox("Filter by Colour Code", ["All"] + sorted(unique_colours))

            if colour_filter != "All":
                filtered_recipes = recipes[recipes['colour_code'] == colour_filter]
            else:
                filtered_recipes = recipes

            if filtered_recipes.empty:
                st.warning(f"No recipes found for: {colour_filter}")
            else:
                sorted_recipes = filtered_recipes.sort_values('colour_code')
                recipe_options = {f"{row['colour_code']} - {row['colour_name']}": row['recipe_id'] for _, row in
                                  sorted_recipes.iterrows()}
                selected = st.selectbox("Select Recipe", list(recipe_options.keys()))
                recipe_id = recipe_options[selected]
                colour_code = selected.split(" - ")[0]

                batch_number = st.text_input("Batch Number (e.g., RED-0001, 2026-001)")
                manufacturing_date = st.date_input("Manufacturing Date", datetime.now())
                manufacturing_date_str = manufacturing_date.strftime("%Y-%m-%d")

                if st.button("▶ Issue Batch", type="primary"):
                    if not batch_number:
                        st.error("❌ Please enter a Batch Number.")
                    elif batch_exists(batch_number):
                        st.error(f"❌ Batch Number '{batch_number}' already exists.")
                    else:
                        add_batch(batch_number, recipe_id, colour_code, manufacturing_date_str)
                        st.toast(f"✅ Batch {batch_number} issued!", icon="✅")
                        st.rerun()
    tab_index += 1

# ---------- TAB 3: QA TESTING (ADMIN & QA) ----------
if is_admin() or is_qa():
    current_tab = tabs[tab_index]
    with current_tab:
        st.header("🔬 3. QA Testing")
        df_batches = get_batches()
        pending = df_batches[df_batches['status'] == 'QA_Pending']
        if not pending.empty:
            batch_options = {f"{row['batch_number']} ({row['colour_code']})": row['batch_id'] for _, row in
                             pending.iterrows()}
            selected = st.selectbox("Select Batch", list(batch_options.keys()))
            batch_id = batch_options[selected]

            st.markdown("**Enter Measured Values**")
            col1, col2 = st.columns(2)
            with col1:
                tsc = st.number_input("TSC (%)", value=45.0, step=0.1)
                ph = st.number_input("pH", value=8.5, step=0.1)
                dl = st.number_input("DL", value=0.0, step=0.01)
                da = st.number_input("Da", value=0.0, step=0.01)
            with col2:
                visc = st.number_input("Viscosity (cP)", value=1200, step=10)
                de = st.number_input("DE", value=0.5, step=0.01)
                db = st.number_input("Db", value=0.0, step=0.01)
                colour_strength = st.number_input("Colour Strength (%)", value=100.0, step=0.1)

            remark = st.text_area("Remark (e.g., adjustments made, issues found)",
                                  placeholder="Add any comments for this QA test...")

            if st.button("Submit QA", type="primary"):
                if not remark:
                    st.warning("⚠️ Please add a remark for traceability.")
                else:
                    msg = update_qa(batch_id, tsc, ph, visc, de, dl, da, db, colour_strength, remark)
                    st.toast(msg, icon="🔬")
                    st.rerun()
        else:
            st.info("No batches waiting for QA.")
    tab_index += 1

# ---------- TAB 4: WIP PROGRESS (ALL ROLES) ----------
# This is always the last tab
with tabs[-1]:
    st.header("📋 4. Live WIP Progress")
    df_all = get_batches()
    active = df_all[df_all['status'] != 'Completed']

    if active.empty:
        st.info("No active batches.")
    else:
        display_cols = ['batch_number', 'colour_code', 'stage', 'status', 'attempt_count', 'manufacturing_date',
                        'tsc', 'ph', 'visc', 'de', 'dl', 'da', 'db', 'colour_strength', 'remark']
        st.dataframe(active[display_cols], use_container_width=True)

        st.subheader("⚡ Actions")
        for _, row in active.iterrows():
            col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 2, 2])
            with col1:
                st.write(f"**{row['batch_number']}**")
            with col2:
                st.write(row['stage'])
            with col3:
                st.write(row['status'])
            with col4:
                st.write(f"Attempt: {row['attempt_count'] or 0}")
            with col5:
                batch_id = row['batch_id']
                # Only show Action Buttons for Admin and Production (QA cannot change stages via buttons)
                if is_admin() or is_production():
                    if row['status'] == 'Issued':
                        if st.button(f"▶ Mix", key=f"mix_{batch_id}"):
                            update_status(batch_id, 'Mixing', 'Mixing')
                            st.rerun()
                    elif row['status'] == 'Mixing':
                        if st.button(f"⚙ Mill", key=f"mill_{batch_id}"):
                            update_status(batch_id, 'Milling', 'Milling')
                            st.rerun()
                    elif row['status'] == 'Milling':
                        if st.button(f"🔬 Submit to QA", key=f"qa_{batch_id}"):
                            update_status(batch_id, 'QA_Pending', 'QA')
                            st.rerun()
                    elif row['status'] == 'QA_Failed':
                        if st.button(f"🔄 Retry", key=f"retry_{batch_id}"):
                            update_status(batch_id, 'Milling', 'Milling')
                            st.rerun()
                    elif row['status'] == 'QA_Passed':
                        if st.button(f"✅ Complete", key=f"comp_{batch_id}"):
                            update_status(batch_id, 'Completed', 'Finished')
                            st.rerun()
                    else:
                        st.write("⏳")
                else:
                    # QA role: Read-only view in WIP
                    st.write("(Read Only)")

st.caption(
    "💡 TSC/pH/Visc are checked against Min/Max ranges. DE is part of Colouristic Properties. Attempts auto-counted.")