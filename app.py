import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ---------- USER CREDENTIALS ----------
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


def get_completed_batches():
    conn = sqlite3.connect('pigment.db')
    df = pd.read_sql_query("SELECT * FROM batches WHERE status = 'Completed' ORDER BY created_at DESC", conn)
    conn.close()
    return df


# REMOVED get_batch_by_number – we will filter within the COA function

def get_recipe_by_id(recipe_id):
    conn = sqlite3.connect('pigment.db')
    df = pd.read_sql_query("SELECT * FROM recipes WHERE recipe_id = ?", (recipe_id,), conn)
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


# ---------- REPORT FUNCTIONS ----------
def generate_coa_pdf(batch_number):
    try:
        # Fetch batch data using get_batches and filter
        all_batches = get_batches()
        batch_df = all_batches[all_batches['batch_number'] == batch_number]
        if batch_df.empty:
            return None
        batch = batch_df.iloc[0]

        recipe_df = get_recipe_by_id(batch['recipe_id'])
        if recipe_df.empty:
            return None
        recipe = recipe_df.iloc[0]

        # Prepare data for PDF table
        params = [
            ("TSC (%)", f"{recipe['tsc_min']:.1f} - {recipe['tsc_max']:.1f}", batch['tsc'],
             recipe['tsc_min'] <= batch['tsc'] <= recipe['tsc_max']),
            ("pH", f"{recipe['ph_min']:.1f} - {recipe['ph_max']:.1f}", batch['ph'],
             recipe['ph_min'] <= batch['ph'] <= recipe['ph_max']),
            ("Viscosity (cP)", f"{recipe['visc_min']:.0f} - {recipe['visc_max']:.0f}", batch['visc'],
             recipe['visc_min'] <= batch['visc'] <= recipe['visc_max']),
            ("DE", f"≤ {recipe['de_max']:.2f}", batch['de'], batch['de'] <= recipe['de_max']),
            ("DL", f"± {recipe['dl_tolerance']:.2f}", batch['dl'], abs(batch['dl']) <= recipe['dl_tolerance']),
            ("Da", f"± {recipe['da_tolerance']:.2f}", batch['da'], abs(batch['da']) <= recipe['da_tolerance']),
            ("Db", f"± {recipe['db_tolerance']:.2f}", batch['db'], abs(batch['db']) <= recipe['db_tolerance']),
            ("Colour Strength (%)", f"{recipe['strength_min']:.0f} - {recipe['strength_max']:.0f}",
             batch['colour_strength'], recipe['strength_min'] <= batch['colour_strength'] <= recipe['strength_max'])
        ]

        # Create PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, alignment=1, spaceAfter=20)
        story.append(Paragraph("CERTIFICATE OF ANALYSIS", title_style))

        # Header Info
        info_style = styles['Normal']
        story.append(Paragraph(f"<b>Batch Number:</b> {batch['batch_number']}", info_style))
        story.append(Paragraph(f"<b>Colour Code:</b> {batch['colour_code']} - {recipe['colour_name']}", info_style))
        story.append(Paragraph(f"<b>Manufacturing Date:</b> {batch['manufacturing_date']}", info_style))
        story.append(Paragraph(f"<b>Attempt Count:</b> {batch['attempt_count']}", info_style))
        story.append(Paragraph(f"<b>Status:</b> {batch['status']}", info_style))
        story.append(Spacer(1, 10))

        # Results Table
        table_data = [["Parameter", "Specification", "Result", "Status"]]
        for param, spec, result, passed in params:
            status_text = "✅ PASS" if passed else "❌ FAIL"
            table_data.append([param, spec, f"{result:.2f}", status_text])

        t = Table(table_data, colWidths=[80, 100, 80, 80])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(t)

        # Footer / Remarks
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"<b>Remarks:</b> {batch['remark'] or 'N/A'}", info_style))
        story.append(Spacer(1, 10))
        story.append(
            Paragraph("This certificate is electronically generated and does not require a physical signature.",
                      styles['Italic']))
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Italic']))

        doc.build(story)
        buffer.seek(0)
        return buffer
    except Exception as e:
        st.error(f"Error generating COA: {str(e)}")
        return None


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

# Dynamic Tabs based on Role
tabs_list = []
if is_admin():
    tabs_list = ["Define Recipe", "Issue Batch", "QA Testing", "WIP Progress", "📊 Reports"]
elif is_production():
    tabs_list = ["Issue Batch", "WIP Progress", "📊 Reports"]
elif is_qa():
    tabs_list = ["QA Testing", "WIP Progress", "📊 Reports"]

tabs = st.tabs(tabs_list)

# ---------- TAB 1: DEFINE RECIPE (ADMIN ONLY) ----------
if is_admin():
    with tabs[0]:
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

# ---------- TAB 2 / 3: ISSUE BATCH (ADMIN & PRODUCTION) ----------
tab_index = 0
if is_admin():
    tab_index = 1
else:
    tab_index = 0

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

# ---------- TAB 3 / 4: QA TESTING (ADMIN & QA) ----------
if is_admin():
    tab_index = 2
elif is_qa():
    tab_index = 0
else:
    tab_index = -1

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

# ---------- WIP PROGRESS (ALL ROLES) ----------
# Find the WIP tab index
wip_index = next(i for i, name in enumerate(tabs_list) if name == "WIP Progress")
with tabs[wip_index]:
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
                    st.write("(Read Only)")

# ---------- 📊 REPORTS TAB (ALL ROLES) ----------
report_index = next(i for i, name in enumerate(tabs_list) if name == "📊 Reports")
with tabs[report_index]:
    st.header("📊 Reports & Analytics")

    # Sub tabs for Reports
    report_tabs = st.tabs(["📈 SPC Charts", "📄 COA Generation", "📥 Data Export"])

    # ---------- SUB TAB 1: SPC CHARTS ----------
    with report_tabs[0]:
        st.subheader("📈 Statistical Process Control (SPC) Charts")

        completed_df = get_completed_batches()
        if completed_df.empty:
            st.info("No completed batches available for SPC analysis.")
        else:
            # Filter by Colour Code
            colours = completed_df['colour_code'].unique().tolist()
            selected_colour = st.selectbox("Select Colour Code for SPC", sorted(colours))

            filtered_df = completed_df[completed_df['colour_code'] == selected_colour]

            if filtered_df.empty:
                st.warning(f"No completed batches for {selected_colour}")
            else:
                # Get recipe specs for this colour
                recipe_df = get_recipes()
                recipe = recipe_df[recipe_df['colour_code'] == selected_colour]
                if not recipe.empty:
                    r = recipe.iloc[0]
                    specs = {
                        'tsc': (r['tsc_min'], r['tsc_max']),
                        'ph': (r['ph_min'], r['ph_max']),
                        'visc': (r['visc_min'], r['visc_max']),
                        'de': (0, r['de_max']),
                        'dl': (-r['dl_tolerance'], r['dl_tolerance']),
                        'da': (-r['da_tolerance'], r['da_tolerance']),
                        'db': (-r['db_tolerance'], r['db_tolerance']),
                        'colour_strength': (r['strength_min'], r['strength_max'])
                    }
                else:
                    specs = None

                # Create subplots (2 columns, 4 rows)
                params = ['tsc', 'ph', 'visc', 'de', 'dl', 'da', 'db', 'colour_strength']
                param_labels = ['TSC (%)', 'pH', 'Viscosity (cP)', 'DE', 'DL', 'Da', 'Db', 'Colour Strength (%)']

                # Sort by batch number or date for X-axis
                filtered_df = filtered_df.sort_values('created_at')
                x_vals = filtered_df['batch_number'].tolist()

                fig = make_subplots(rows=4, cols=2, subplot_titles=param_labels)

                row_idx = 1
                col_idx = 1
                for i, param in enumerate(params):
                    y_vals = filtered_df[param].tolist()

                    fig.add_trace(go.Scatter(
                        x=x_vals,
                        y=y_vals,
                        mode='lines+markers',
                        name=param_labels[i],
                        line=dict(color='blue'),
                        marker=dict(size=6)
                    ), row=row_idx, col=col_idx)

                    # Add UCL and LCL lines if specs exist
                    if specs:
                        lower, upper = specs[param]
                        fig.add_hline(y=upper, line_dash="dash", line_color="red", row=row_idx, col=col_idx)
                        fig.add_hline(y=lower, line_dash="dash", line_color="red", row=row_idx, col=col_idx)

                    # Move to next subplot
                    if col_idx == 2:
                        row_idx += 1
                        col_idx = 1
                    else:
                        col_idx += 1

                fig.update_layout(height=1000, showlegend=False, title_text=f"SPC Chart: {selected_colour}")
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)

    # ---------- SUB TAB 2: COA GENERATION ----------
    with report_tabs[1]:
        st.subheader("📄 Certificate of Analysis (COA) - PDF")

        completed_list = get_completed_batches()
        if completed_list.empty:
            st.info("No completed batches available for COA generation.")
        else:
            # Dropdown to select batch
            batch_options = {f"{row['batch_number']} ({row['colour_code']})": row['batch_number'] for _, row in
                             completed_list.iterrows()}
            selected_batch = st.selectbox("Select Batch for COA", list(batch_options.keys()))
            batch_num = batch_options[selected_batch]

            if st.button("📑 Generate COA PDF", type="primary"):
                pdf_buffer = generate_coa_pdf(batch_num)
                if pdf_buffer:
                    st.download_button(
                        label="⬇ Download COA (PDF)",
                        data=pdf_buffer,
                        file_name=f"COA_{batch_num}.pdf",
                        mime="application/pdf"
                    )
                    st.success("✅ COA generated successfully! Click the download button above.")
                else:
                    st.error("❌ Failed to generate COA. Please check that the batch has all required data.")

    # ---------- SUB TAB 3: DATA EXPORT ----------
    with report_tabs[2]:
        st.subheader("📥 Export Completed Data to CSV")

        completed_data = get_completed_batches()
        if completed_data.empty:
            st.info("No completed batches to export.")
        else:
            # Preview
            st.dataframe(completed_data, use_container_width=True)

            # Export button
            csv = completed_data.to_csv(index=False)
            st.download_button(
                label="⬇ Download CSV",
                data=csv,
                file_name=f"completed_batches_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

st.caption(
    "💡 Reports are available to all roles. SPC charts show trends vs control limits. COA PDF fits a single A4 page.")