import streamlit as st
import sqlite3
import random
import pandas as pd


# ---------- DATABASE SETUP (Auto-creates a file called pigment.db) ----------
def init_db():
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS batches
                 (id TEXT PRIMARY KEY, 
                  batch_number TEXT UNIQUE, 
                  colour TEXT, 
                  status TEXT, 
                  stage TEXT, 
                  tsc REAL, 
                  ph REAL, 
                  visc REAL, 
                  de REAL, 
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()


def get_batches():
    conn = sqlite3.connect('pigment.db')
    df = pd.read_sql_query("SELECT * FROM batches ORDER BY created_at DESC", conn)
    conn.close()
    return df


def add_batch(colour):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    batch_id = f"b_{random.randint(1000, 9999)}"
    batch_num = f"PIG-{random.randint(100, 999)}"
    c.execute("INSERT INTO batches (id, batch_number, colour, status, stage) VALUES (?,?,?,?,?)",
              (batch_id, batch_num, colour, 'Issued', 'Mixing'))
    conn.commit()
    conn.close()


def update_status(batch_id, status, stage):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    c.execute("UPDATE batches SET status=?, stage=? WHERE id=?", (status, stage, batch_id))
    conn.commit()
    conn.close()


def update_qa(batch_id, tsc, ph, visc, de):
    conn = sqlite3.connect('pigment.db')
    c = conn.cursor()
    # PASS / FAIL Logic (Targets: TSC=45, pH=8.5, Visc=1200, DE<=1.0)
    passed = (abs(tsc - 45) <= 2.5 and abs(ph - 8.5) <= 0.5 and abs(visc - 1200) <= 100 and de <= 1.0)
    if passed:
        status, stage, msg = 'QA_Passed', 'Finished', '✅ QA PASSED! Ready to Complete.'
    else:
        status, stage, msg = 'QA_Failed', 'Milling', '❌ QA FAILED! Back to Milling.'
    c.execute("UPDATE batches SET tsc=?, ph=?, visc=?, de=?, status=?, stage=? WHERE id=?",
              (tsc, ph, visc, de, status, stage, batch_id))
    conn.commit()
    conn.close()
    return msg


# ---------- THE WEB INTERFACE ----------
st.set_page_config(page_title="Pigment Monitor", layout="wide")
st.title("🎨 Pigment Dispersion System")

# Create the database file if it doesn't exist
init_db()

# ---------- SIDEBAR (Issue Batch & QA) ----------
with st.sidebar:
    st.header("📄 1. Issue New Batch")
    colour = st.selectbox("Colour", ["Red", "Blue", "Black", "Yellow", "Green", "Violet", "Orange"])
    if st.button("▶ Issue Batch", type="primary"):
        add_batch(colour)
        st.success(f"✅ Batch for {colour} issued!")
        st.rerun()

    st.divider()
    st.header("🔬 2. QA Testing")
    df = get_batches()
    pending = df[df['status'] == 'QA_Pending']
    if not pending.empty:
        selected = st.selectbox("Select Batch", pending['batch_number'].tolist())
        col1, col2 = st.columns(2)
        with col1:
            tsc = st.number_input("TSC (%)", value=45.0, step=0.1)
            ph = st.number_input("pH", value=8.5, step=0.1)
        with col2:
            visc = st.number_input("Viscosity (cP)", value=1200, step=10)
            de = st.number_input("DE", value=0.5, step=0.01)
        if st.button("Submit QA", type="primary"):
            batch_id = df[df['batch_number'] == selected]['id'].values[0]
            msg = update_qa(batch_id, tsc, ph, visc, de)
            st.toast(msg)
            st.rerun()
    else:
        st.info("No batches waiting for QA.")

# ---------- MAIN TABLE (WIP Progress) ----------
st.header("📋 3. Live WIP Progress")

df = get_batches()
active = df[df['status'] != 'Completed']

if active.empty:
    st.info("No active batches. Go to the sidebar to issue one!")
else:
    st.dataframe(active[['batch_number', 'colour', 'stage', 'status', 'tsc', 'ph', 'visc', 'de']],
                 use_container_width=True)

    st.subheader("⚡ Actions")
    for idx, row in active.iterrows():
        col1, col2, col3, col4 = st.columns([1, 1, 2, 2])
        with col1:
            st.write(f"**{row['batch_number']}**")
        with col2:
            st.write(row['stage'])
        with col3:
            st.write(row['status'])
        with col4:
            if row['status'] == 'Issued':
                if st.button(f"▶ Mix", key=f"mix_{row['id']}"):
                    update_status(row['id'], 'Mixing', 'Mixing')
                    st.rerun()
            elif row['status'] == 'Mixing':
                if st.button(f"⚙ Mill", key=f"mill_{row['id']}"):
                    update_status(row['id'], 'Milling', 'Milling')
                    st.rerun()
            elif row['status'] == 'Milling':
                if st.button(f"🔬 QA", key=f"qa_{row['id']}"):
                    update_status(row['id'], 'QA_Pending', 'QA')
                    st.rerun()
            elif row['status'] == 'QA_Failed':
                if st.button(f"🔄 Retry", key=f"retry_{row['id']}"):
                    update_status(row['id'], 'Milling', 'Milling')
                    st.rerun()
            elif row['status'] == 'QA_Passed':
                if st.button(f"✅ Complete", key=f"comp_{row['id']}"):
                    update_status(row['id'], 'Completed', 'Finished')
                    st.rerun()
            else:
                st.write("⏳")

st.caption("💡 Press 'R' or click the browser refresh button to see updates from other users.")