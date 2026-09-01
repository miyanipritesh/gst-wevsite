import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
import hashlib
import json
from datetime import datetime

# ==========================================
# 1. PAGE CONFIGURATION & CUSTOM STYLING
# ==========================================
st.set_page_config(
    page_title="ClearGST | E-Commerce Tax Automation",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom SaaS Dark/Clean CSS theme
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .metric-card {
        background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
        border: 1px solid #374151;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .metric-title {
        color: #9ca3af;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-value {
        color: #f9fafb;
        font-size: 1.8rem;
        font-weight: 700;
        margin-top: 5px;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DATABASE & AUTHENTICATION ENGINE
# ==========================================
DB_FILE = "gst_portal.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Users Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            business_name TEXT,
            gstin TEXT
        )
    ''')
    # GST Monthly Records
    c.execute('''
        CREATE TABLE IF NOT EXISTS gst_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            month TEXT,
            platform TEXT,
            gross_sales REAL,
            returns REAL,
            net_sales REAL,
            igst REAL,
            cgst REAL,
            sgst REAL,
            tcs REAL,
            total_tax REAL,
            created_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_user(username, password, business_name, gstin):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password, business_name, gstin) VALUES (?, ?, ?, ?)",
                  (username, hash_pass(password), business_name, gstin))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username, business_name, gstin FROM users WHERE username = ? AND password = ?",
              (username, hash_pass(password)))
    user = c.fetchone()
    conn.close()
    return user

def save_gst_record(user_id, month, platform, gross, ret, net, igst, cgst, sgst, tcs, total_tax):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO gst_records (user_id, month, platform, gross_sales, returns, net_sales, igst, cgst, sgst, tcs, total_tax, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, month, platform, gross, ret, net, igst, cgst, sgst, tcs, total_tax, datetime.now()))
    conn.commit()
    conn.close()

def get_user_records(user_id):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM gst_records WHERE user_id = ? ORDER BY created_at DESC", conn, params=(user_id,))
    conn.close()
    return df

# ==========================================
# 3. SESSION MANAGEMENT
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user" not in st.session_state:
    st.session_state.user = None

# ==========================================
# 4. AUTH INTERFACE (LOGIN & SIGNUP)
# ==========================================
if not st.session_state.authenticated:
    st.markdown("<h2 style='text-align: center; margin-bottom: 25px;'>💼 ClearGST Automation Portal</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.6, 1])
    with col2:
        auth_tab1, auth_tab2 = st.tabs(["🔑 Sign In", "📝 Create Account"])
        
        with auth_tab1:
            with st.form("login_form"):
                username = st.text_input("Username or Email")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Access Dashboard", use_container_width=True)
                if submit:
                    user_data = verify_user(username, password)
                    if user_data:
                        st.session_state.authenticated = True
                        st.session_state.user = {
                            "id": user_data[0],
                            "username": user_data[1],
                            "business_name": user_data[2],
                            "gstin": user_data[3]
                        }
                        st.success("Authentication successful!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials. Check username or password.")
                        
        with auth_tab2:
            with st.form("signup_form"):
                new_user = st.text_input("Username")
                new_pass = st.text_input("Password", type="password")
                business_name = st.text_input("Business / Brand Name")
                gstin = st.text_input("GSTIN Number (15 digits)")
                register = st.form_submit_button("Register Seller Account", use_container_width=True)
                if register:
                    if new_user and new_pass and gstin:
                        if create_user(new_user, new_pass, business_name, gstin):
                            st.success("Account created successfully! Switch to Sign In tab.")
                        else:
                            st.error("Username already registered.")
                    else:
                        st.warning("Please fill all required details.")
    st.stop()

# ==========================================
# 5. DASHBOARD INTERFACE
# ==========================================
user = st.session_state.user

# Sidebar Control Center
with st.sidebar:
    st.markdown(f"### 🏢 {user['business_name']}")
    st.caption(f"GSTIN: `{user['gstin']}`")
    st.markdown("---")
    
    menu = st.radio(
        "Navigation",
        ["📊 Tax Analytics", "⚡ Process Platform Data", "📁 Reports & GSTR-1 Preview"],
        index=0
    )
    st.markdown("---")
    if st.button("Log Out", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()

# ------------------------------------------
# SCREEN 1: PROCESS DATA & AUTO-CALCULATE
# ------------------------------------------
if menu == "⚡ Process Platform Data":
    st.subheader("⚡ Multi-Platform GST Reconciliation")
    st.caption("Upload sales reports or enter consolidated figures to auto-compute GSTR-1 liabilities and TCS credit.")
    
    col_input, col_config = st.columns([2, 1])
    
    with col_config:
        st.markdown("#### Filing Details")
        selected_month = st.selectbox(
            "Filing Month",
            ["April 2026", "May 2026", "June 2026", "July 2026", "August 2026", "September 2026"]
        )
        selected_platform = st.selectbox(
            "Marketplace Channel",
            ["Amazon IN", "Flipkart", "Meesho", "Shopify / D2C", "Custom CSV"]
        )
        tax_rate = st.selectbox("Product GST Bracket", [5, 12, 18, 28], index=2)
        interstate_ratio = st.slider("Inter-State Sales Share (IGST %)", 0, 100, 70, help="Percentage of deliveries outside home state.")
    
    with col_input:
        st.markdown("#### Input Monthly Figures")
        entry_mode = st.radio("Input Method", ["Quick Manual Input", "Upload Order Sheet (CSV/Excel)"], horizontal=True)
        
        gross_sales = 0.0
        returns_amt = 0.0
        
        if entry_mode == "Quick Manual Input":
            c1, c2 = st.columns(2)
            with c1:
                gross_sales = st.number_input("Gross Shipped Value (₹)", min_value=0.0, value=250000.0, step=1000.0)
            with c2:
                returns_amt = st.number_input("Sales Returns / Cancellations (₹)", min_value=0.0, value=35000.0, step=500.0)
        else:
            uploaded_file = st.file_uploader("Upload settlement or MTR report", type=["csv", "xlsx"])
            if uploaded_file:
                try:
                    df_up = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
                    st.success(f"Loaded {len(df_up)} orders successfully!")
                    st.dataframe(df_up.head(3), use_container_width=True)
                    # Simulated extraction for prototype
                    gross_sales = float(df_up.select_dtypes(include=['float', 'int']).iloc[:, 0].sum()) if not df_up.empty else 100000.0
                    returns_amt = gross_sales * 0.12
                    st.info(f"Auto-detected Gross Sales: ₹{gross_sales:,.2f} | Returns: ₹{returns_amt:,.2f}")
                except Exception as e:
                    st.error(f"Error parsing file: {e}")
                    
    # Computation Engine
    net_taxable = max(0.0, gross_sales - returns_amt)
    base_tax_amount = net_taxable * (tax_rate / 100.0)
    
    igst = base_tax_amount * (interstate_ratio / 100.0)
    intra_tax = base_tax_amount * ((100 - interstate_ratio) / 100.0)
    cgst = intra_tax / 2.0
    sgst = intra_tax / 2.0
    
    # E-commerce TCS (0.5% CGST + 0.5% SGST or 1% IGST under Sec 52)
    tcs_deducted = net_taxable * 0.01

    st.markdown("---")
    st.markdown("### 📋 Liability Breakdown Preview")
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Net Taxable Turnover</div><div class="metric-value">₹{net_taxable:,.2f}</div></div>', unsafe_allow_html=True)
    with m2:
        st.markdown(f'<div class="metric-card"><div class="metric-title">Total GST Liability</div><div class="metric-value">₹{base_tax_amount:,.2f}</div></div>', unsafe_allow_html=True)
    with m3:
        st.markdown(f'<div class="metric-card"><div class="metric-title">TCS Credit Available</div><div class="metric-value">₹{tcs_deducted:,.2f}</div></div>', unsafe_allow_html=True)
    with m4:
        net_payable = max(0.0, base_tax_amount - tcs_deducted)
        st.markdown(f'<div class="metric-card"><div class="metric-title">Net Cash Outflow</div><div class="metric-value">₹{net_payable:,.2f}</div></div>', unsafe_allow_html=True)

    st.write("")
    if st.button("💾 Save Record to Database", type="primary", use_container_width=True):
        save_gst_record(
            user["id"], selected_month, selected_platform,
            gross_sales, returns_amt, net_taxable,
            igst, cgst, sgst, tcs_deducted, base_tax_amount
        )
        st.success(f"Report for {selected_platform} ({selected_month}) committed to database!")

# ------------------------------------------
# SCREEN 2: ANALYTICS & DASHBOARD
# ------------------------------------------
elif menu == "📊 Tax Analytics":
    st.subheader(f"📊 Tax Intelligence Dashboard")
    
    records_df = get_user_records(user["id"])
    
    if records_df.empty:
        st.info("Koi records save nahi mile. 'Process Platform Data' section me jakar pehle sales data add karein.")
    else:
        # High Level Metrics
        total_sales = records_df["net_sales"].sum()
        total_tax = records_df["total_tax"].sum()
        total_tcs = records_df["tcs"].sum()
        total_igst = records_df["igst"].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Cumulative Net Sales", f"₹{total_sales:,.0f}")
        c2.metric("Total Output GST", f"₹{total_tax:,.0f}")
        c3.metric("TCS Deducted (Sec 52)", f"₹{total_tcs:,.0f}")
        c4.metric("Total IGST Share", f"₹{total_igst:,.0f}")
        
        st.markdown("---")
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_platform = px.pie(
                records_df,
                names="platform",
                values="net_sales",
                title="Channel-wise Turnover Share",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Prism
            )
            fig_platform.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#e5e7eb")
            st.plotly_chart(fig_platform, use_container_width=True)
            
        with col_g2:
            tax_split = pd.DataFrame({
                "Tax Head": ["IGST", "CGST", "SGST", "TCS Credit"],
                "Amount": [records_df["igst"].sum(), records_df["cgst"].sum(), records_df["sgst"].sum(), records_df["tcs"].sum()]
            })
            fig_bar = px.bar(
                tax_split,
                x="Tax Head",
                y="Amount",
                title="Tax Component Distribution",
                text_auto=".2s",
                color="Tax Head",
                color_discrete_sequence=["#3b82f6", "#10b981", "#f59e0b", "#ec4899"]
            )
            fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="#e5e7eb", showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

# ------------------------------------------
# SCREEN 3: REPORTS & EXPORT
# ------------------------------------------
elif menu == "📁 Reports & GSTR-1 Preview":
    st.subheader("📁 Saved Monthly Reconciliations")
    
    records_df = get_user_records(user["id"])
    
    if records_df.empty:
        st.info("No saved records to generate reports.")
    else:
        st.dataframe(
            records_df[[
                "month", "platform", "gross_sales", "returns",
                "net_sales", "igst", "cgst", "sgst", "tcs", "total_tax", "created_at"
            ]],
            use_container_width=True
        )
        
        csv_buffer = records_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Consolidated GSTR Filing Sheet (CSV)",
            data=csv_buffer,
            file_name=f"GST_Summary_{user['business_name']}.csv",
            mime="text/csv",
            type="primary"
        )
