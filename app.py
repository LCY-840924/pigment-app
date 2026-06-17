import streamlit as st
import sqlite3
import pandas as pd


# ---------- DATABASE SETUP ----------
def init_db():
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()

    # Recipes table
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
                    recipe_id TEXT PRIMARY KEY,
                    colour_code TEXT UNIQUE,
                    colour_name TEXT,
                    target_tsc REAL,
                    target_ph REAL,
                    target_visc REAL,
                    target_de REAL
                )''')

    # Batches table - ADDED: dl, da, db, colour_strength
    c.execute('''CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    batch_number TEXT UNIQUE,
                    recipe_id TEXT,
                    colour_code TEXT,
                    status TEXT,
                    stage TEXT,
                    tsc REAL,
                    ph REAL,
                    visc REAL,
                    de REAL,
                    dl REAL,
                    da REAL,
                    db REAL,
                    colour_strength REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

    # Sequence counter for batch numbers
    c.execute('''CREATE TABLE IF NOT EXISTS seq_counter (
                    colour_code TEXT PRIMARY KEY,
                    last_seq INTEGER DEFAULT 0
                )''')

    # --- Add new columns safely if they don't exist ---
    try:
        c.execute("ALTER TABLE batches ADD COLUMN dl REAL")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        c.execute("ALTER TABLE batches ADD COLUMN da REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE batches ADD COLUMN db REAL")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE batches ADD COLUMN colour_strength REAL")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


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


def get_next_seq(colour_code):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("SELECT last_seq FROM seq_counter WHERE colour_code = ?", (colour_code,))
    row = c.fetchone()
    if row:
        next_seq = row[0] + 1
        c.execute("UPDATE seq_counter SET last_seq = ? WHERE colour_code = ?", (next_seq, colour_code))
    else:
        next_seq = 1
        c.execute("INSERT INTO seq_counter (colour_code, last_seq) VALUES (?, ?)", (colour_code, next_seq))
    conn.commit()
    conn.close()
    return next_seq


def add_recipe(colour_code, colour_name, target_tsc, target_ph, target_visc, target_de):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO recipes (recipe_id, colour_code, colour_name, target_tsc, target_ph, target_visc, target_de) VALUES (?,?,?,?,?,?,?)",
        (colour_code, colour_code, colour_name, target_tsc, target_ph, target_visc, target_de))
    conn.commit()
    conn.close()


def add_batch(recipe_id, colour_code):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    seq = get_next_seq(colour_code)
    batch_number = f"{colour_code}-{seq:08d}"  # 8-digit padded number
    batch_id = f"b_{colour_code}_{seq:08d}"
    c.execute(
        "INSERT INTO batches (batch_id, batch_number, recipe_id, colour_code, status, stage) VALUES (?,?,?,?,?,?)",
        (batch_id, batch_number, recipe_id, colour_code, 'Issued', 'Mixing'))
    conn.commit()
    conn.close()
    return batch_number


def update_status(batch_id, status, stage):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("UPDATE batches SET status=?, stage=? WHERE batch_id=?", (status, stage, batch_id))
    conn.commit()
    conn.close()


# ---------- UPDATED QA FUNCTION with new parameters ----------
def update_qa(batch_id, tsc, ph, visc, de, dl, da, db, colour_strength):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()

    # Get recipe targets for this batch
    c.execute("""
        SELECT r.target_tsc, r.target_ph, r.target_visc, r.target_de 
        FROM recipes r JOIN batches b ON r.recipe_id = b.recipe_id 
        WHERE b.batch_id = ?
    """, (batch_id,))
    row = c.fetchone()
    if not row:
        return "❌ Recipe not found!"

    target_tsc, target_ph, target_visc, target_de = row

    # ----- PASS / FAIL LOGIC (All must pass) -----
    # 1. TSC: +/- 5%
    tsc_ok = abs(tsc - target_tsc) / target_tsc <= 0.05
    # 2. pH: +/- 0.5
    ph_ok = abs(ph - target_ph) <= 0.5
    # 3. Viscosity: +/- 5%
    visc_ok = abs(visc - target_visc) / target_visc <= 0.05
    # 4. DE: <= 1.0 (or target_de, but spec says <=1.0)
    de_ok = de <= 1.0
    # 5. DL: +/- 0.5
    dl_ok = abs(dl) <= 0.5
    # 6. Da: +/- 0.6
    da_ok = abs(da) <= 0.6
    # 7. Db: +/- 0.6
    db_ok = abs(db) <= 0.6
    # 8. Colour Strength: 95% - 105%
    strength_ok = 95 <= colour_strength <= 105

    passed = all([tsc_ok, ph_ok, visc_ok, de_ok, dl_ok, da_ok, db_ok, strength_ok])

    if passed:
        status, stage, msg = 'QA_Passed', 'Finished', '✅ QA PASSED! Ready to Complete.'
    else:
        status, stage, msg = 'QA_Failed', 'Milling', '❌ QA FAILED! Back to Milling.'

    # Update batch with ALL measured values
    c.execute("""
        UPDATE batches 
        SET tsc=?, ph=?, visc=?, de=?, dl=?, da=?, db=?, colour_strength=?, status=?, stage=? 
        WHERE batch_id=?
    """, (tsc, ph, visc, de, dl, da, db, colour_strength, status, stage, batch_id))

    conn.commit()
    conn.close()
    return msg


# ---------- INIT DATABASE ----------
init_db()

# ---------- STREAMLIT UI ----------
st.set_page_config(page_title="Pigment Monitor", layout="wide")
st.title("🎨 Pigment Dispersion System")

# ---------- SIDEBAR ----------
with st.sidebar:
    st.header("📄 1. Define Recipe (Colour)")
    with st.form("recipe_form"):
        col_code = st.text_input("Colour Code (e.g., RED)", max_chars=5).upper()
        col_name = st.text_input("Colour Name", "Red Oxide")
        col1, col2 = st.columns(2)
        with col1:
            target_tsc = st.number_input("Target TSC (%)", value=45.0, step=0.1)
            target_ph = st.number_input("Target pH", value=8.5, step=0.1)
        with col2:
            target_visc = st.number_input("Target Viscosity (cP)", value=1200, step=10)
            target_de = st.number_input("Target DE (≤1.0)", value=1.0, step=0.01, max_value=1.0)
        submitted = st.form_submit_button("Save Recipe")
        if submitted and col_code:
            add_recipe(col_code, col_name, target_tsc, target_ph, target_visc, target_de)
            st.toast(f"✅ Recipe for {col_code} saved!", icon="✅")
            st.rerun()

    st.divider()
    st.header("📄 2. Issue New Batch")
    recipes = get_recipes()
    if recipes.empty:
        st.warning("No recipes. Please add a recipe first.")
    else:
        recipe_options = {f"{row['colour_code']} - {row['colour_name']}": row['recipe_id'] for _, row in
                          recipes.iterrows()}
        selected = st.selectbox("Select Recipe", list(recipe_options.keys()))
        recipe_id = recipe_options[selected]
        colour_code = selected.split(" - ")[0]
        if st.button("▶ Issue Batch", type="primary"):
            batch_num = add_batch(recipe_id, colour_code)
            st.toast(f"✅ Batch {batch_num} issued!", icon="✅")
            st.rerun()

    st.divider()
    st.header("🔬 3. QA Testing")
    df_batches = get_batches()
    pending = df_batches[df_batches['status'] == 'QA_Pending']
    if not pending.empty:
        batch_options = {f"{row['batch_number']} ({row['colour_code']})": row['batch_id'] for _, row in
                         pending.iterrows()}
        selected = st.selectbox("Select Batch", list(batch_options.keys()))
        batch_id = batch_options[selected]

        st.markdown("**Measured Values**")
        col1, col2 = st.columns(2)
        with col1:
            tsc = st.number_input("TSC (%)", value=45.0, step=0.1)
            ph = st.number_input("pH", value=8.5, step=0.1)
            dl = st.number_input("DL (target 0, ±0.5)", value=0.0, step=0.01)
            da = st.number_input("Da (target 0, ±0.6)", value=0.0, step=0.01)
        with col2:
            visc = st.number_input("Viscosity (cP)", value=1200, step=10)
            de = st.number_input("DE (≤1.0)", value=0.5, step=0.01, max_value=1.0)
            db = st.number_input("Db (target 0, ±0.6)", value=0.0, step=0.01)
            colour_strength = st.number_input("Colour Strength (%)", value=100.0, step=0.1)

        if st.button("Submit QA", type="primary"):
            msg = update_qa(batch_id, tsc, ph, visc, de, dl, da, db, colour_strength)
            st.toast(msg, icon="🔬")
            st.rerun()
    else:
        st.info("No batches waiting for QA.")

# ---------- MAIN TABLE (Updated Columns) ----------
st.header("📋 4. Live WIP Progress")

df_all = get_batches()
active = df_all[df_all['status'] != 'Completed']

if active.empty:
    st.info("No active batches. Issue one from the sidebar.")
else:
    # Display all QA parameters including the new ones
    st.dataframe(
        active[['batch_number', 'colour_code', 'stage', 'status', 'tsc', 'ph', 'visc', 'de', 'dl', 'da', 'db',
                'colour_strength']],
        use_container_width=True
    )

    st.subheader("⚡ Actions")
    for _, row in active.iterrows():
        col1, col2, col3, col4 = st.columns([1, 1, 2, 2])
        with col1:
            st.write(f"**{row['batch_number']}**")
        with col2:
            st.write(row['stage'])
        with col3:
            st.write(row['status'])
        with col4:
            batch_id = row['batch_id']
            if row['status'] == 'Issued':
                if st.button(f"▶ Mix", key=f"mix_{batch_id}"):
                    update_status(batch_id, 'Mixing', 'Mixing')
                    st.rerun()
            elif row['status'] == 'Mixing':
                if st.button(f"⚙ Mill", key=f"mill_{batch_id}"):
                    update_status(batch_id, 'Milling', 'Milling')
                    st.rerun()
            elif row['status'] == 'Milling':
                if st.button(f"🔬 QA", key=f"qa_{batch_id}"):
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

st.caption("💡 QC Specs: TSC ±5%, pH ±0.5, Visc ±5%, DE ≤1.0, DL ±0.5, Da ±0.6, Db ±0.6, Strength 95-105%.")