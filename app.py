import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import zipfile
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ---------- QR DECODER ----------
try:
    from PIL import Image
    import pyzbar.pyzbar as pyzbar
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

def decode_qr_from_image(image):
    if not QR_AVAILABLE:
        return None
    try:
        rgb_image = image.convert('RGB')
        decoded_objects = pyzbar.decode(rgb_image)
        for obj in decoded_objects:
            return obj.data.decode('utf-8')
    except Exception:
        pass
    return None

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
    # Add missing columns
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
    c.execute("""UPDATE recipes SET
                 tsc_min = COALESCE(tsc_min, 40.0),
                 tsc_max = COALESCE(tsc_max, 50.0),
                 ph_min = COALESCE(ph_min, 7.5),
                 ph_max = COALESCE(ph_max, 9.5),
                 visc_min = COALESCE(visc_min, 1000.0),
                 visc_max = COALESCE(visc_max, 1400.0),
                 de_max = COALESCE(de_max, 1.0),
                 dl_tolerance = COALESCE(dl_tolerance, 0.5),
                 da_tolerance = COALESCE(da_tolerance, 0.6),
                 db_tolerance = COALESCE(db_tolerance, 0.6),
                 strength_min = COALESCE(strength_min, 95.0),
                 strength_max = COALESCE(strength_max, 105.0)""")
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

def get_recipe_by_id(recipe_id):
    conn = sqlite3.connect('pigment.db')
    df = pd.read_sql_query("SELECT * FROM recipes WHERE recipe_id = ?", conn, params=(recipe_id,))
    conn.close()
    return df

def batch_exists(batch_number):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM batches WHERE batch_number = ?", (batch_number,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def add_recipe(colour_code, colour_name, tsc_min, tsc_max, ph_min, ph_max,
               visc_min, visc_max, de_max, dl_tol, da_tol, db_tol, str_min, str_max):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO recipes
                 (recipe_id, colour_code, colour_name, tsc_min, tsc_max, ph_min, ph_max,
                  visc_min, visc_max, de_max, dl_tolerance, da_tolerance, db_tolerance,
                  strength_min, strength_max)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (colour_code, colour_code, colour_name, tsc_min, tsc_max, ph_min, ph_max,
               visc_min, visc_max, de_max, dl_tol, da_tol, db_tol, str_min, str_max))
    conn.commit()
    conn.close()

def update_recipe(recipe_id, colour_name, tsc_min, tsc_max, ph_min, ph_max,
                  visc_min, visc_max, de_max, dl_tol, da_tol, db_tol,
                  str_min, str_max):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("""UPDATE recipes SET
                 colour_name=?, tsc_min=?, tsc_max=?, ph_min=?, ph_max=?,
                 visc_min=?, visc_max=?, de_max=?,
                 dl_tolerance=?, da_tolerance=?, db_tolerance=?,
                 strength_min=?, strength_max=?
                 WHERE recipe_id=?""",
              (colour_name, tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max,
               de_max, dl_tol, da_tol, db_tol, str_min, str_max, recipe_id))
    conn.commit()
    conn.close()

def delete_recipe(recipe_id):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("DELETE FROM recipes WHERE recipe_id = ?", (recipe_id,))
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
    c.execute("""SELECT tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max,
                        de_max, dl_tolerance, da_tolerance, db_tolerance,
                        strength_min, strength_max
                 FROM recipes r JOIN batches b ON r.recipe_id = b.recipe_id
                 WHERE b.batch_id = ?""", (batch_id,))
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
        """UPDATE batches SET tsc=?, ph=?, visc=?, de=?, dl=?, da=?, db=?,
           colour_strength=?, status=?, stage=?, attempt_count=?, remark=?
           WHERE batch_id=?""",
        (tsc, ph, visc, de, dl, da, db, colour_strength, status, stage, new_attempt, remark, batch_id))
    conn.commit()
    conn.close()
    return msg

# ---------- BACKUP / RESTORE ----------
def export_db_to_zip():
    conn = sqlite3.connect('pigment.db')
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for table in ['recipes', 'batches', 'seq_counter']:
            df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
            csv_data = df.to_csv(index=False).encode('utf-8')
            zipf.writestr(f"{table}.csv", csv_data)
    conn.close()
    zip_buffer.seek(0)
    return zip_buffer

def import_db_from_zip(zip_file):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    with zipfile.ZipFile(zip_file, 'r') as zipf:
        for table in ['recipes', 'batches', 'seq_counter']:
            if f"{table}.csv" in zipf.namelist():
                df = pd.read_csv(zipf.open(f"{table}.csv"))
                c.execute(f"DELETE FROM {table}")
                df.to_sql(table, conn, if_exists='append', index=False)
    conn.commit()
    conn.close()

# ---------- COA GENERATION (fully customizable template) ----------
def generate_coa_pdf(batch_number, template, edited_results=None):
    """
    template: dict with keys: company_name, reg_no, address_lines (list), phone_fax, title
    edited_results: DataFrame with columns PARAMETER, SPECIFICATION, RESULT
    """
    try:
        all_batches = get_batches()
        batch_df = all_batches[all_batches['batch_number'] == batch_number]
        if batch_df.empty:
            return None
        batch = batch_df.iloc[0]

        recipe_df = get_recipe_by_id(batch['recipe_id'])
        if recipe_df.empty:
            return None
        recipe = recipe_df.iloc[0]

        # ---- Date parsing ----
        mfg_val = batch['manufacturing_date']
        if pd.isna(mfg_val) or mfg_val is None:
            mfg_date = datetime.now()
        else:
            try:
                if isinstance(mfg_val, (int, float)):
                    mfg_date = datetime.fromtimestamp(mfg_val)
                else:
                    mfg_date = pd.to_datetime(mfg_val)
            except:
                mfg_date = datetime.now()
        if hasattr(mfg_date, 'to_pydatetime'):
            mfg_date = mfg_date.to_pydatetime()

        expiry_date = mfg_date + pd.DateOffset(months=18)
        mfg_str = mfg_date.strftime("%d.%m.%Y")
        expiry_str = expiry_date.strftime("%d.%m.%Y")

        # ---- Prepare results ----
        # Default: use database values
        default_results = {
            "pH": batch['ph'],
            "TSC": batch['tsc'],
            "Viscosity": "Paste",
            "DL": batch['dl'],
            "Da": batch['da'],
            "Db": batch['db'],
            "DE": batch['de'],
            "Colour Strength": batch['colour_strength']
        }

        # If edited results provided, merge them
        if edited_results is not None:
            edited_dict = {row['PARAMETER']: row['RESULT'] for _, row in edited_results.iterrows()}
            # For numeric fields, try to convert to float; if fails, keep original
            numeric_params = ["pH", "TSC", "DL", "Da", "Db", "DE", "Colour Strength"]
            for param in numeric_params:
                if param in edited_dict and edited_dict[param] != "":
                    try:
                        default_results[param] = float(edited_dict[param])
                    except ValueError:
                        # keep original
                        pass
            # For viscosity, just take the string
            if "Viscosity" in edited_dict:
                default_results["Viscosity"] = edited_dict["Viscosity"]

        # Build results list for PDF
        results = [
            ("pH", f"{recipe['ph_min']:.2f} - {recipe['ph_max']:.2f}", f"{default_results['pH']:.2f}"),
            ("TSC", f"{recipe['tsc_min']:.0f}-{recipe['tsc_max']:.0f}%", f"{default_results['TSC']:.2f}%"),
            ("Viscosity", "Paste", default_results["Viscosity"]),
            ("DL", f"± {recipe['dl_tolerance']:.1f}", f"{default_results['DL']:.2f}"),
            ("Da", f"± {recipe['da_tolerance']:.1f}", f"{default_results['Da']:.2f}"),
            ("Db", f"± {recipe['db_tolerance']:.1f}", f"{default_results['Db']:.2f}"),
            ("DE", f"≤ {recipe['de_max']:.1f}", f"{default_results['DE']:.2f}"),
            ("Colour Strength", f"{recipe['strength_min']:.0f}-{recipe['strength_max']:.0f}%", f"{default_results['Colour Strength']:.2f}%")
        ]

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=20, leftMargin=20,
                                topMargin=20, bottomMargin=20)
        styles = getSampleStyleSheet()
        story = []

        # ---- HEADER (customizable) ----
        header_style = ParagraphStyle('Header', parent=styles['Normal'],
                                      fontSize=10, leading=12, alignment=1)
        # Company lines
        company_lines = [
            template.get('company_name', "TIARCO CHEMICAL (MALAYSIA) SDN. BHD."),
            template.get('reg_no', "199101012802 (223114-K)"),
            *template.get('address_lines', [
                "LOT 47962, PERSIARAN TASEK,",
                "KAWASAN PERINDUSTRIAN TASEK,",
                "31400 IPOH, PERAK, MALAYSIA."
            ]),
            template.get('phone_fax', "TEL: 605-5412018            FAX : 605-5412716")
        ]
        for line in company_lines:
            story.append(Paragraph(line, header_style))
        story.append(Spacer(1, 12))

        # ---- TITLE ----
        title_text = template.get('title', "PROVISIONAL CERTIFICATE OF ANALYSIS")
        title_style = ParagraphStyle('Title', parent=styles['Title'],
                                     fontSize=16, alignment=1, spaceAfter=12)
        story.append(Paragraph(title_text, title_style))

        # ---- TOP TABLE ----
        top_data = [
            ["Product:", recipe['colour_name']],
            ["Batch No.:", batch['batch_number']],
            ["Manufacturing date:", mfg_str],
            ["Expiry date:", expiry_str]
        ]
        top_table = Table(top_data, colWidths=[70, 300])
        top_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ]))
        story.append(top_table)
        story.append(Spacer(1, 12))

        # ---- MAIN TABLE ----
        data = [["PARAMETER", "SPECIFICATION", "RESULT"]]
        for param, spec, result in results:
            data.append([param, spec, result])

        main_table = Table(data, colWidths=[100, 150, 100])
        main_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(main_table)
        story.append(Spacer(1, 20))

        # ---- BOTTOM TABLE ----
        bottom_data = [
            ["Date:", mfg_str],
            ["Prepared by:", template.get('prepared_by', 'MOKHJY')],
            ["Reviewed & approved by:", template.get('reviewed_by', 'MOKHJY')]
        ]
        bottom_table = Table(bottom_data, colWidths=[120, 250])
        bottom_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ]))
        story.append(bottom_table)

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

login()

def is_admin():
    return st.session_state.role == "Admin"
def is_production():
    return st.session_state.role == "Production"
def is_qa():
    return st.session_state.role == "QA"

# ---------- MAIN APP ----------
st.title("🎨 Pigment Dispersion System")

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

        with st.form("new_recipe_form"):
            col_code = st.text_input("Colour Code (e.g., RED, PIG-001)")
            col_name = st.text_input("Colour Name", "Red Oxide")

            st.subheader("📊 Basic QC Specs (Ranges)")
            col1, col2 = st.columns(2)
            with col1:
                tsc_min = st.number_input("TSC Min (%)", value=43.0, step=0.1)
                ph_min = st.number_input("pH Min", value=8.0, step=0.1)
                visc_min = st.number_input("Viscosity Min (cP)", value=1100.0, step=10.0)
            with col2:
                tsc_max = st.number_input("TSC Max (%)", value=47.0, step=0.1)
                ph_max = st.number_input("pH Max", value=9.0, step=0.1)
                visc_max = st.number_input("Viscosity Max (cP)", value=1300.0, step=10.0)

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
                    add_recipe(col_code, col_name, tsc_min, tsc_max, ph_min, ph_max,
                               visc_min, visc_max, de_max, dl_tol, da_tol, db_tol,
                               str_min, str_max)
                    st.toast(f"✅ Recipe for {col_code} saved!", icon="✅")
                    st.rerun()

        # ---- Existing Recipes (CRUD, Preview, Export) ----
        st.subheader("📋 Existing Recipes")
        recipes_df = get_recipes()
        if not recipes_df.empty:
            st.dataframe(recipes_df, use_container_width=True)

            csv = recipes_df.to_csv(index=False)
            st.download_button(
                label="⬇ Export Recipes as CSV",
                data=csv,
                file_name="recipes.csv",
                mime="text/csv"
            )

            st.subheader("✏️ Edit or Delete Recipe")
            selected_recipe = st.selectbox("Select Recipe to Edit/Delete",
                                           recipes_df['colour_code'].tolist())
            if selected_recipe:
                recipe_row = recipes_df[recipes_df['colour_code'] == selected_recipe].iloc[0]
                with st.expander(f"Edit {selected_recipe}"):
                    with st.form("edit_recipe_form"):
                        edit_colour_name = st.text_input("Colour Name",
                                                         value=recipe_row['colour_name'])
                        edit_tsc_min = st.number_input("TSC Min",
                                                       value=float(recipe_row['tsc_min']),
                                                       step=0.1)
                        edit_tsc_max = st.number_input("TSC Max",
                                                       value=float(recipe_row['tsc_max']),
                                                       step=0.1)
                        edit_ph_min = st.number_input("pH Min",
                                                      value=float(recipe_row['ph_min']),
                                                      step=0.1)
                        edit_ph_max = st.number_input("pH Max",
                                                      value=float(recipe_row['ph_max']),
                                                      step=0.1)
                        edit_visc_min = st.number_input("Viscosity Min",
                                                        value=float(recipe_row['visc_min']),
                                                        step=10.0)
                        edit_visc_max = st.number_input("Viscosity Max",
                                                        value=float(recipe_row['visc_max']),
                                                        step=10.0)
                        edit_de_max = st.number_input("DE Max",
                                                      value=float(recipe_row['de_max']),
                                                      step=0.01)
                        edit_dl_tol = st.number_input("DL Tolerance",
                                                      value=float(recipe_row['dl_tolerance']),
                                                      step=0.1)
                        edit_da_tol = st.number_input("Da Tolerance",
                                                      value=float(recipe_row['da_tolerance']),
                                                      step=0.1)
                        edit_db_tol = st.number_input("Db Tolerance",
                                                      value=float(recipe_row['db_tolerance']),
                                                      step=0.1)
                        edit_str_min = st.number_input("Strength Min",
                                                       value=float(recipe_row['strength_min']),
                                                       step=1.0)
                        edit_str_max = st.number_input("Strength Max",
                                                       value=float(recipe_row['strength_max']),
                                                       step=1.0)

                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("Update Recipe"):
                                update_recipe(selected_recipe, edit_colour_name,
                                              edit_tsc_min, edit_tsc_max,
                                              edit_ph_min, edit_ph_max,
                                              edit_visc_min, edit_visc_max,
                                              edit_de_max, edit_dl_tol, edit_da_tol,
                                              edit_db_tol, edit_str_min, edit_str_max)
                                st.toast(f"✅ Recipe {selected_recipe} updated!", icon="✅")
                                st.rerun()
                        with col2:
                            if st.form_submit_button("Delete Recipe", type="primary"):
                                delete_recipe(selected_recipe)
                                st.toast(f"🗑️ Recipe {selected_recipe} deleted!", icon="🗑️")
                                st.rerun()
        else:
            st.info("No recipes defined yet.")

        # ---- Backup / Restore ----
        st.divider()
        st.subheader("💾 Backup / Restore Database")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 Export Database (ZIP)", use_container_width=True):
                zip_data = export_db_to_zip()
                st.download_button(
                    label="⬇ Download pigment_db_backup.zip",
                    data=zip_data,
                    file_name="pigment_db_backup.zip",
                    mime="application/zip"
                )
                st.success("✅ Database exported successfully!")
        with col2:
            uploaded_zip = st.file_uploader("📤 Upload backup ZIP to restore", type=["zip"])
            if uploaded_zip is not None:
                if st.button("⚠️ Restore Database (overwrites current data)", type="primary"):
                    try:
                        import_db_from_zip(uploaded_zip)
                        st.toast("✅ Database restored! Refreshing...", icon="🔄")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Restore failed: {str(e)}")

# ---------- TAB 2 / 3: ISSUE BATCH ----------
if is_admin() or is_production():
    tab_idx = 1 if is_admin() else 0
    with tabs[tab_idx]:
        st.header("📄 2. Issue New Batch")
        recipes = get_recipes()
        if recipes.empty:
            st.warning("No recipes. Please ask Admin to add a recipe first.")
        else:
            # ---- QR Scanner ----
            st.subheader("📷 Scan QR with Camera")
            if not QR_AVAILABLE:
                st.warning(
                    "⚠️ QR scanning library not installed. Please install pyzbar and Pillow.\n"
                    "You can still use the manual text input below."
                )
            else:
                camera_image = st.camera_input("Point camera at QR code")
                if camera_image is not None:
                    try:
                        img = Image.open(camera_image)
                        decoded = decode_qr_from_image(img)
                        if decoded:
                            st.success(f"✅ Decoded: {decoded}")
                            parts = decoded.split('_', 1)
                            if len(parts) == 2:
                                qr_recipe, qr_batch = parts[0], parts[1]
                                if not recipes[recipes['colour_code'] == qr_recipe].empty:
                                    st.session_state['qr_recipe'] = qr_recipe
                                    st.session_state['qr_batch'] = qr_batch
                                    st.rerun()
                                else:
                                    st.error(f"❌ Recipe '{qr_recipe}' not found.")
                            else:
                                st.error("❌ Invalid QR format. Use 'recipeName_batchNumber'")
                        else:
                            st.error("❌ No QR code detected. Please try again.")
                    except Exception as e:
                        st.error(f"❌ Error processing image: {e}")

            # ---- Manual QR text ----
            st.subheader("📝 Or paste QR text (optional)")
            qr_input = st.text_input(
                "Paste QR code content (format: recipeName_batchNumber)",
                placeholder="e.g. RED_2026-001"
            )
            if qr_input:
                try:
                    parts = qr_input.split('_', 1)
                    if len(parts) == 2:
                        qr_recipe, qr_batch = parts[0], parts[1]
                        if not recipes[recipes['colour_code'] == qr_recipe].empty:
                            st.session_state['qr_recipe'] = qr_recipe
                            st.session_state['qr_batch'] = qr_batch
                            st.success(f"✅ Recognised: Recipe '{qr_recipe}', Batch '{qr_batch}'")
                            st.rerun()
                        else:
                            st.error(f"❌ Recipe '{qr_recipe}' not found.")
                    else:
                        st.error("❌ Invalid QR format. Use 'recipeName_batchNumber'")
                except Exception as e:
                    st.error(f"❌ Error parsing QR: {e}")

            # ---- Recipe Selection ----
            unique_colours = recipes['colour_code'].unique().tolist()
            default_recipe = st.session_state.get('qr_recipe', None)
            default_index = 0
            if default_recipe and default_recipe in unique_colours:
                default_index = unique_colours.index(default_recipe)

            colour_filter = st.selectbox("Filter by Colour Code", ["All"] + sorted(unique_colours), index=0)
            if colour_filter != "All":
                filtered_recipes = recipes[recipes['colour_code'] == colour_filter]
            else:
                filtered_recipes = recipes

            if filtered_recipes.empty:
                st.warning(f"No recipes found for: {colour_filter}")
            else:
                sorted_recipes = filtered_recipes.sort_values('colour_code')
                recipe_options = {f"{row['colour_code']} - {row['colour_name']}": row['recipe_id']
                                  for _, row in sorted_recipes.iterrows()}
                default_selected = None
                if default_recipe:
                    for key in recipe_options.keys():
                        if key.startswith(default_recipe):
                            default_selected = key
                            break
                selected = st.selectbox("Select Recipe", list(recipe_options.keys()),
                                        index=list(recipe_options.keys()).index(default_selected) if default_selected else 0)
                recipe_id = recipe_options[selected]
                colour_code = selected.split(" - ")[0]

                default_batch = st.session_state.get('qr_batch', '')
                batch_number = st.text_input("Batch Number (e.g., RED-0001, 2026-001)", value=default_batch)
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
                        if 'qr_recipe' in st.session_state:
                            del st.session_state['qr_recipe']
                        if 'qr_batch' in st.session_state:
                            del st.session_state['qr_batch']
                        st.rerun()

# ---------- TAB 3 / 4: QA TESTING ----------
if is_admin() or is_qa():
    tab_idx = 2 if is_admin() else 0
    with tabs[tab_idx]:
        st.header("🔬 3. QA Testing")
        df_batches = get_batches()
        pending = df_batches[df_batches['status'] == 'QA_Pending']
        if not pending.empty:
            batch_options = {f"{row['batch_number']} ({row['colour_code']})": row['batch_id']
                             for _, row in pending.iterrows()}
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
                visc = st.number_input("Viscosity (cP)", value=1200.0, step=10.0)
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

# ---------- WIP PROGRESS ----------
wip_index = next(i for i, name in enumerate(tabs_list) if name == "WIP Progress")
with tabs[wip_index]:
    st.header("📋 4. Live WIP Progress")
    df_all = get_batches()
    active = df_all[df_all['status'] != 'Completed']
    if active.empty:
        st.info("No active batches.")
    else:
        display_cols = ['batch_number', 'colour_code', 'stage', 'status', 'attempt_count',
                        'manufacturing_date', 'tsc', 'ph', 'visc', 'de', 'dl', 'da', 'db',
                        'colour_strength', 'remark']
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

# ---------- REPORTS TAB ----------
report_index = next(i for i, name in enumerate(tabs_list) if name == "📊 Reports")
with tabs[report_index]:
    st.header("📊 Reports & Analytics")
    report_tabs = st.tabs(["📈 SPC Charts", "📄 COA Generation", "📥 Data Export"])

    # ---- SPC Charts ----
    with report_tabs[0]:
        st.subheader("📈 Statistical Process Control (SPC) Charts")
        completed_df = get_completed_batches()
        if completed_df.empty:
            st.info("No completed batches available for SPC analysis.")
        else:
            colours = completed_df['colour_code'].unique().tolist()
            selected_colour = st.selectbox("Select Colour Code for SPC", sorted(colours))
            filtered_df = completed_df[completed_df['colour_code'] == selected_colour]
            if filtered_df.empty:
                st.warning(f"No completed batches for {selected_colour}")
            else:
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

                params = ['tsc', 'ph', 'visc', 'de', 'dl', 'da', 'db', 'colour_strength']
                param_labels = ['TSC (%)', 'pH', 'Viscosity (cP)', 'DE', 'DL', 'Da', 'Db', 'Colour Strength (%)']
                filtered_df = filtered_df.sort_values('created_at')
                x_vals = filtered_df['batch_number'].tolist()

                fig = make_subplots(rows=4, cols=2, subplot_titles=param_labels)
                row_idx, col_idx = 1, 1
                for i, param in enumerate(params):
                    y_vals = filtered_df[param].tolist()
                    fig.add_trace(go.Scatter(x=x_vals, y=y_vals, mode='lines+markers',
                                             name=param_labels[i], line=dict(color='blue'),
                                             marker=dict(size=6)),
                                  row=row_idx, col=col_idx)
                    if specs:
                        lower, upper = specs[param]
                        fig.add_hline(y=upper, line_dash="dash", line_color="red", row=row_idx, col=col_idx)
                        fig.add_hline(y=lower, line_dash="dash", line_color="red", row=row_idx, col=col_idx)
                    if col_idx == 2:
                        row_idx += 1
                        col_idx = 1
                    else:
                        col_idx += 1

                fig.update_layout(height=1000, showlegend=False, title_text=f"SPC Chart: {selected_colour}")
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)

    # ---- COA Generation (fully customizable template) ----
    with report_tabs[1]:
        st.subheader("📄 Certificate of Analysis - Editable Preview & Custom Template")

        completed_list = get_completed_batches()
        if completed_list.empty:
            st.info("No completed batches available for COA generation.")
        else:
            # ---- Template customisation ----
            with st.expander("✏️ Customize COA Template (optional)", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    company_name = st.text_input("Company Name", value="TIARCO CHEMICAL (MALAYSIA) SDN. BHD.", key="coa_company")
                    reg_no = st.text_input("Registration No.", value="199101012802 (223114-K)", key="coa_reg")
                    address_line1 = st.text_input("Address Line 1", value="LOT 47962, PERSIARAN TASEK,", key="coa_addr1")
                    address_line2 = st.text_input("Address Line 2", value="KAWASAN PERINDUSTRIAN TASEK,", key="coa_addr2")
                    address_line3 = st.text_input("Address Line 3", value="31400 IPOH, PERAK, MALAYSIA.", key="coa_addr3")
                with col2:
                    phone_fax = st.text_input("Phone / Fax", value="TEL: 605-5412018            FAX : 605-5412716", key="coa_phone")
                    title = st.text_input("COA Title", value="PROVISIONAL CERTIFICATE OF ANALYSIS", key="coa_title")
                    prepared_by = st.text_input("Prepared by", value="MOKHJY", key="coa_prepared")
                    reviewed_by = st.text_input("Reviewed & approved by", value="MOKHJY", key="coa_reviewed")

            # Build template dict
            template = {
                'company_name': company_name,
                'reg_no': reg_no,
                'address_lines': [address_line1, address_line2, address_line3],
                'phone_fax': phone_fax,
                'title': title,
                'prepared_by': prepared_by,
                'reviewed_by': reviewed_by
            }

            # ---- Select batch ----
            batch_options = {f"{row['batch_number']} ({row['colour_code']})": row['batch_number']
                             for _, row in completed_list.iterrows()}
            selected_batch = st.selectbox("Select Batch for COA", list(batch_options.keys()))
            batch_num = batch_options[selected_batch]

            # ---- Load batch and recipe data ----
            all_batches = get_batches()
            batch_df = all_batches[all_batches['batch_number'] == batch_num]
            if not batch_df.empty:
                batch = batch_df.iloc[0]
                recipe_df = get_recipe_by_id(batch['recipe_id'])
                if not recipe_df.empty:
                    recipe = recipe_df.iloc[0]

                    # Parse dates
                    mfg_val = batch['manufacturing_date']
                    if pd.isna(mfg_val) or mfg_val is None:
                        mfg_date = datetime.now()
                    else:
                        try:
                            if isinstance(mfg_val, (int, float)):
                                mfg_date = datetime.fromtimestamp(mfg_val)
                            else:
                                mfg_date = pd.to_datetime(mfg_val)
                        except:
                            mfg_date = datetime.now()
                    if hasattr(mfg_date, 'to_pydatetime'):
                        mfg_date = mfg_date.to_pydatetime()
                    expiry_date = mfg_date + pd.DateOffset(months=18)
                    mfg_str = mfg_date.strftime("%d.%m.%Y")
                    expiry_str = expiry_date.strftime("%d.%m.%Y")

                    # ---- Build results data for editing ----
                    results_data = pd.DataFrame({
                        "PARAMETER": ["pH", "TSC", "Viscosity", "DL", "Da", "Db", "DE", "Colour Strength"],
                        "SPECIFICATION": [
                            f"{recipe['ph_min']:.2f} - {recipe['ph_max']:.2f}",
                            f"{recipe['tsc_min']:.0f}-{recipe['tsc_max']:.0f}%",
                            "Paste",
                            f"± {recipe['dl_tolerance']:.1f}",
                            f"± {recipe['da_tolerance']:.1f}",
                            f"± {recipe['db_tolerance']:.1f}",
                            f"≤ {recipe['de_max']:.1f}",
                            f"{recipe['strength_min']:.0f}-{recipe['strength_max']:.0f}%"
                        ],
                        "RESULT": [
                            f"{batch['ph']:.2f}",
                            f"{batch['tsc']:.2f}%",
                            "Paste",
                            f"{batch['dl']:.2f}",
                            f"{batch['da']:.2f}",
                            f"{batch['db']:.2f}",
                            f"{batch['de']:.2f}",
                            f"{batch['colour_strength']:.2f}%"
                        ]
                    })

                    # ---- Display preview with data_editor ----
                    st.subheader("📋 COA Preview (edit results inline)")

                    # Top info
                    top_df = pd.DataFrame({
                        "Field": ["Product", "Batch No.", "Manufacturing date", "Expiry date"],
                        "Value": [recipe['colour_name'], batch['batch_number'], mfg_str, expiry_str]
                    })
                    st.dataframe(top_df, use_container_width=True, hide_index=True)

                    # Editable results table
                    st.markdown("**Edit the RESULT column if needed (numeric values for pH, TSC, DL, Da, Db, DE, Colour Strength):**")
                    edited_results = st.data_editor(
                        results_data,
                        use_container_width=True,
                        hide_index=True,
                        key=f"coa_editor_{batch_num}_{datetime.now().timestamp()}",
                        column_config={
                            "PARAMETER": st.column_config.TextColumn("Parameter", disabled=True),
                            "SPECIFICATION": st.column_config.TextColumn("Specification", disabled=True),
                            "RESULT": st.column_config.TextColumn("Result (editable)")
                        }
                    )

                    # Bottom info
                    bottom_df = pd.DataFrame({
                        "Field": ["Date:", "Prepared by:", "Reviewed & approved by:"],
                        "Value": [mfg_str, prepared_by, reviewed_by]
                    })
                    st.dataframe(bottom_df, use_container_width=True, hide_index=True)

                    # ---- Generate PDF button ----
                    if st.button("📑 Generate COA PDF", type="primary"):
                        pdf_buffer = generate_coa_pdf(batch_num, template, edited_results)
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

    # ---- Data Export ----
    with report_tabs[2]:
        st.subheader("📥 Export Completed Data to CSV")
        completed_data = get_completed_batches()
        if completed_data.empty:
            st.info("No completed batches to export.")
        else:
            st.dataframe(completed_data, use_container_width=True)
            csv = completed_data.to_csv(index=False)
            st.download_button(
                label="⬇ Download CSV",
                data=csv,
                file_name=f"completed_batches_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

# ---------- SIDEBAR REFRESH ----------
st.sidebar.button("🔄 Refresh Data", on_click=lambda: st.rerun())

st.caption("💡 Reports are available to all roles. SPC charts show trends vs control limits. COA PDF fits a single A4 page.")