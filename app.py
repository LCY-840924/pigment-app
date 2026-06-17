import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime


# ---------- DATABASE SETUP ----------
def init_db():
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()

    # Recipes table
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
                    recipe_id TEXT PRIMARY KEY,
                    colour_code TEXT UNIQUE,
                    colour_name TEXT,
                    tsc_min REAL,
                    tsc_max REAL,
                    ph_min REAL,
                    ph_max REAL,
                    visc_min REAL,
                    visc_max REAL,
                    de_max REAL,
                    dl_tolerance REAL DEFAULT 0.5,
                    da_tolerance REAL DEFAULT 0.6,
                    db_tolerance REAL DEFAULT 0.6,
                    strength_min REAL DEFAULT 95.0,
                    strength_max REAL DEFAULT 105.0
                )''')

    # Batches table
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
                    manufacturing_date TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    remark TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

    # Sequence counter (not used anymore, but kept)
    c.execute('''CREATE TABLE IF NOT EXISTS seq_counter (
                    colour_code TEXT PRIMARY KEY,
                    last_seq INTEGER DEFAULT 0
                )''')

    # --- MIGRATE: Add new columns if missing and set defaults for existing rows ---
    # Add recipe columns
    for col in ['tsc_min', 'tsc_max', 'ph_min', 'ph_max', 'visc_min', 'visc_max', 'de_max']:
        try:
            c.execute(f"ALTER TABLE recipes ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass

    # Add batch columns
    for col in ['dl', 'da', 'db', 'colour_strength']:
        try:
            c.execute(f"ALTER TABLE batches ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass

    for col in ['manufacturing_date', 'remark']:
        try:
            c.execute(f"ALTER TABLE batches ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    try:
        c.execute("ALTER TABLE batches ADD COLUMN attempt_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # --- FIX NULL VALUES for existing recipes ---
    # Set default ranges for any recipe that has NULL in the new columns
    c.execute("UPDATE recipes SET tsc_min = COALESCE(tsc_min, 40.0)")
    c.execute("UPDATE recipes SET tsc_max = COALESCE(tsc_max, 50.0)")
    c.execute("UPDATE recipes SET ph_min = COALESCE(ph_min, 7.5)")
    c.execute("UPDATE recipes SET ph_max = COALESCE(ph_max, 9.5)")
    c.execute("UPDATE recipes SET visc_min = COALESCE(visc_min, 1000.0)")
    c.execute("UPDATE recipes SET visc_max = COALESCE(visc_max, 1400.0)")
    c.execute("UPDATE recipes SET de_max = COALESCE(de_max, 1.0)")
    c.execute("UPDATE recipes SET dl_tolerance = COALESCE(dl_tolerance, 0.5)")
    c.execute("UPDATE recipes SET da_tolerance = COALESCE(da_tolerance, 0.6)")
    c.execute("UPDATE recipes SET db_tolerance = COALESCE(db_tolerance, 0.6)")
    c.execute("UPDATE recipes SET strength_min = COALESCE(strength_min, 95.0)")
    c.execute("UPDATE recipes SET strength_max = COALESCE(strength_max, 105.0)")

    conn.commit()
    conn.close()


# ---------- REST OF THE CODE (unchanged except for add_recipe and update_qa) ----------
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


def recipe_exists(colour_code):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM recipes WHERE colour_code = ?", (colour_code,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def batch_exists(batch_number):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM batches WHERE batch_number = ?", (batch_number,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def add_recipe(colour_code, colour_name, tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max,
               de_max, dl_tol, da_tol, db_tol, str_min, str_max):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO recipes 
                 (recipe_id, colour_code, colour_name, 
                  tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max,
                  de_max, dl_tolerance, da_tolerance, db_tolerance, strength_min, strength_max) 
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (colour_code, colour_code, colour_name,
               tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max,
               de_max, dl_tol, da_tol, db_tol, str_min, str_max))
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

    # Fetch recipe specs (now guaranteed to have non-NULL values)
    c.execute("""
        SELECT tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max,
               de_max, dl_tolerance, da_tolerance, db_tolerance, strength_min, strength_max
        FROM recipes r JOIN batches b ON r.recipe_id = b.recipe_id 
        WHERE b.batch_id = ?
    """, (batch_id,))
    row = c.fetchone()
    if not row:
        return "❌ Recipe not found!"

    (tsc_min, tsc_max, ph_min, ph_max, visc_min, visc_max,
     de_max, dl_tol, da_tol, db_tol, str_min, str_max) = row

    # ----- PASS / FAIL LOGIC -----
    tsc_ok = tsc_min <= tsc <= tsc_max
    ph_ok = ph_min <= ph <= ph_max
    visc_ok = visc_min <= visc <= visc_max
    de_ok = de <= de_max
    dl_ok = abs(dl) <= dl_tol
    da_ok = abs(da) <= da_tol
    db_ok = abs(db) <= db_tol
    strength_ok = str_min <= colour_strength <= str_max

    passed = all([tsc_ok, ph_ok, visc_ok, de_ok, dl_ok, da_ok, db_ok, strength_ok])

    # Increment attempt count
    c.execute("SELECT attempt_count FROM batches WHERE batch_id = ?", (batch_id,))
    current_attempt = c.fetchone()[0] or 0
    new_attempt = current_attempt + 1

    if passed:
        status, stage, msg = 'QA_Passed', 'Finished', '✅ QA PASSED! Ready to Complete.'
    else:
        status, stage, msg = 'QA_Failed', 'Milling', '❌ QA FAILED! Back to Milling.'

    c.execute("""
        UPDATE batches 
        SET tsc=?, ph=?, visc=?, de=?, dl=?, da=?, db=?, colour_strength=?, 
            status=?, stage=?, attempt_count=?, remark=? 
        WHERE batch_id=?
    """, (tsc, ph, visc, de, dl, da, db, colour_strength, status, stage, new_attempt, remark, batch_id))

    conn.commit()
    conn.close()
    return msg


# ---------- INIT DATABASE ----------
init_db()

# ---------- STREAMLIT UI (same as before) ----------
st.set_page_config(page_title="Pigment Monitor", layout="wide")
st.title("🎨 Pigment Dispersion System")

# ... (the rest of your sidebar, tabs, main table code is unchanged)
# Copy the exact UI code from the previous response from the line `with st.sidebar:` onwards.
# I'll include it here in full for completeness.