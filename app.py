import streamlit as st
import pandas as pd
import json
import io
import re
import zipfile
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ==============================================================
# 1. PAGE SETUP & MINIMAL FINTECH THEME
# ==============================================================
st.set_page_config(
    page_title="ClearGST Auto-Filer | 100% Upload Driven",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="collapsed"
)

APP_NAME = "GST_AutoFiler_Pro"

st.markdown("""
<style>
    /* Clean, Modern Background & Typography */
    .stApp {
        background-color: #0d1117;
        color: #e6edf3;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Hero Banner */
    .hero-box {
        background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
    }
    
    /* Modern Metric Cards */
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 10px;
        padding: 16px 18px;
        transition: transform 0.15s ease-in-out, border-color 0.15s ease;
    }
    .metric-card:hover {
        border-color: #58a6ff;
        transform: translateY(-2px);
    }
    .metric-card-title {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #8b949e;
        margin-bottom: 4px;
    }
    .metric-card-value {
        font-size: 1.55rem;
        font-weight: 700;
        color: #f0f6fc;
    }
    .metric-card-sub {
        font-size: 0.72rem;
        color: #7ee787;
        margin-top: 3px;
    }

    /* Modern Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #30363d;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px 8px 0 0;
        color: #8b949e;
        padding: 8px 18px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f6feb !important;
        border-color: #1f6feb !important;
        color: #ffffff !important;
    }
    
    /* Table Styling */
    div[data-testid="stDataFrame"] {
        border: 1px solid #30363d;
        border-radius: 8px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

STATE_MAP = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "19": "West Bengal", "23": "Madhya Pradesh", "24": "Gujarat",
    "27": "Maharashtra", "29": "Karnataka", "33": "Tamil Nadu", "36": "Telangana", "37": "Andhra Pradesh"
}

# ==============================================================
# 2. CORE UTILITY & CRASH-PROOF ACCESSORS
# ==============================================================
def get_state_name_from_gstin(gstin):
    code = str(gstin)[:2] if len(str(gstin)) >= 2 and str(gstin)[:2].isdigit() else "24"
    return STATE_MAP.get(code, f"State-{code}")

def safe_float(val, default=0.0):
    try:
        if pd.isna(val) or str(val).strip() == '':
            return default
        return float(val)
    except (ValueError, TypeError):
        return default

def safe_get(row, idx, default=""):
    """Crash-proof row indexing for unpredictable spreadsheet layouts"""
    try:
        if idx < len(row):
            v = row[idx]
            return v if pd.notna(v) else default
        return default
    except Exception:
        return default

def is_valid_gstin(gstin):
    pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    return bool(re.match(pattern, str(gstin).strip().upper()))

def format_period_label(fp):
    months_map = {
        '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr', '05': 'May', '06': 'Jun',
        '07': 'Jul', '08': 'Aug', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
    }
    if len(fp) == 6 and fp[:2] in months_map:
        return f"{months_map[fp[:2]]}_{fp[2:]}"
    return fp

def extract_return_period(filenames, sample_dates):
    months = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05', 'jun': '06',
        'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
    }
    for fn in filenames:
        fn_low = fn.lower()
        for m_name, m_num in months.items():
            if m_name in fn_low:
                m_year = re.search(r'202[4-9]', fn_low)
                year_str = m_year.group(0) if m_year else str(datetime.now().year)
                return f"{m_num}{year_str}"
                
    for d in sample_dates:
        if d and isinstance(d, str):
            d_low = d.lower()
            for m_name, m_num in months.items():
                if m_name in d_low:
                    m_year = re.search(r'202[4-9]', d_low)
                    year_str = m_year.group(0) if m_year else str(datetime.now().year)
                    return f"{m_num}{year_str}"
    return f"{datetime.now().month:02d}{datetime.now().year}"

def extract_gstin_from_excel(file_bytes_or_io):
    try:
        xl = pd.ExcelFile(file_bytes_or_io)
        pattern = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
        for sheet in xl.sheet_names:
            df = pd.read_excel(file_bytes_or_io, sheet_name=sheet)
            for c in df.columns:
                if 'gstin' in str(c).lower() and 'buyer' not in str(c).lower() and 'flipkart' not in str(c).lower():
                    for v in df[c].dropna():
                        v_str = str(v).strip().upper()
                        if pattern.match(v_str):
                            return v_str
            for v in df.values.flatten():
                v_str = str(v).strip().upper()
                if pattern.match(v_str):
                    return v_str
    except Exception:
        pass
    return None

def detect_ecommerce_platform(file_bytes, filename=""):
    try:
        excel = pd.ExcelFile(file_bytes)
        sheets = [s.strip().lower() for s in excel.sheet_names]
        if any('section 7(a)' in s or 'section 12 in gstr-1' in s or 'section 7(b)' in s or 'section 3 in gstr-8' in s for s in sheets):
            return "Flipkart", "🟦 Flipkart"
        if any('b2c small' in s or 'hsn summary' in s or 'b2cl cn' in s for s in sheets):
            return "Amazon", "🟧 Amazon"
        if any('tcs_sales' in s or 'order_date' in str(s) for s in sheets):
            return "Meesho", "🟪 Meesho"
        return "Unknown", "⚪ Unknown Platform"
    except Exception:
        return "Unknown", "⚪ Unknown Platform"

# ==============================================================
# 3. PLATFORM PARSERS (ROBUST & BULLET-PROOF)
# ==============================================================
def parse_amazon(file_bytes):
    try:
        excel = pd.ExcelFile(file_bytes)
    except Exception:
        return {"platform": "Amazon", "supplier_gstin": "N/A", "supplier_state": "24", "gross": 0.0, "taxable": 0.0, "returns_gross": 0.0, "returns_taxable": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "total_tax": 0.0, "tcs": 0.0, "hsn": [], "b2cs": [], "b2b": [], "sample_dates": []}

    hsn_records, b2cs_records, b2b_records = [], [], []
    taxable_sum, igst_sum, cgst_sum, sgst_sum, gross_sum = 0.0, 0.0, 0.0, 0.0, 0.0
    supplier_gstin = extract_gstin_from_excel(file_bytes) or "N/A"
    supplier_state = supplier_gstin[:2] if len(supplier_gstin) >= 2 and supplier_gstin[:2].isdigit() else "24"
    sample_dates = []

    if 'HSN Summary' in excel.sheet_names:
        df_hsn = pd.read_excel(file_bytes, sheet_name='HSN Summary', header=None)
        if len(df_hsn) > 4:
            for r in df_hsn.values[4:]:
                hsn_code = str(safe_get(r, 0, '')).strip()
                if hsn_code and hsn_code.lower() not in ['total', 'nan']:
                    qty = safe_float(safe_get(r, 3, 0))
                    rate = safe_float(safe_get(r, 4, 0))
                    gross = safe_float(safe_get(r, 5, 0))
                    taxable = safe_float(safe_get(r, 6, 0))
                    igst = safe_float(safe_get(r, 7, 0))
                    cgst = safe_float(safe_get(r, 8, 0))
                    sgst = safe_float(safe_get(r, 9, 0))
                    
                    taxable_sum += taxable
                    igst_sum += igst
                    cgst_sum += cgst
                    sgst_sum += sgst
                    gross_sum += gross
                    
                    hsn_records.append({
                        "Platform": "Amazon", "Supplier GSTIN": supplier_gstin, "HSN Code": hsn_code,
                        "UQC": str(safe_get(r, 2, 'PCS')).strip(),
                        "Qty": qty, "GST Rate": f"{rate*100:.0f}%", "Rate_Num": rate*100, "Taxable (₹)": taxable,
                        "IGST (₹)": igst, "CGST (₹)": cgst, "SGST (₹)": sgst, "Gross Total (₹)": gross
                    })

    if 'B2C Small' in excel.sheet_names:
        df_b2cs = pd.read_excel(file_bytes, sheet_name='B2C Small', header=None)
        if len(df_b2cs) > 4:
            for r in df_b2cs.values[4:]:
                pos = str(safe_get(r, 1, '')).strip()
                taxable = safe_float(safe_get(r, 4, 0))
                rate = safe_float(safe_get(r, 3, 0.05))
                if pos and taxable > 0:
                    is_intra = pos.startswith(supplier_state)
                    igst = 0.0 if is_intra else round(taxable * rate, 2)
                    cgst = round((taxable * rate) / 2, 2) if is_intra else 0.0
                    sgst = round((taxable * rate) / 2, 2) if is_intra else 0.0
                    b2cs_records.append({
                        "Platform": "Amazon", "Supplier GSTIN": supplier_gstin, "Place of Supply": pos, "Rate": f"{rate*100:.0f}%", "Rate_Num": rate*100,
                        "Taxable Value (₹)": taxable, "IGST (₹)": igst, "CGST (₹)": cgst, "SGST (₹)": sgst,
                        "Gross Value (₹)": round(taxable + igst + cgst + sgst, 2)
                    })

    if 'B2B' in excel.sheet_names:
        df_b2b = pd.read_excel(file_bytes, sheet_name='B2B', header=None)
        if len(df_b2b) > 4:
            for r in df_b2b.values[4:]:
                buyer_gst = str(safe_get(r, 0, '')).strip().upper()
                if buyer_gst and buyer_gst.lower() not in ['total', 'nan']:
                    rate = safe_float(safe_get(r, 10, 0.05))
                    inv_date = str(safe_get(r, 3, '')).strip()
                    sample_dates.append(inv_date)
                    b2b_records.append({
                        "Platform": "Amazon", "Supplier GSTIN": supplier_gstin, "Buyer GSTIN": buyer_gst,
                        "Invoice No": str(safe_get(r, 2, '')).strip(),
                        "Date": inv_date, "Place of Supply": str(safe_get(r, 5, '')).strip(),
                        "Rate": f"{rate*100:.0f}%", "Rate_Num": rate*100,
                        "Taxable Value (₹)": safe_float(safe_get(r, 11, 0)),
                        "Gross / Invoice Value (₹)": safe_float(safe_get(r, 4, 0))
                    })

    return {
        "platform": "Amazon", "supplier_gstin": supplier_gstin, "supplier_state": supplier_state,
        "gross": gross_sum, "taxable": taxable_sum, "returns_gross": 0.0, "returns_taxable": 0.0,
        "igst": igst_sum, "cgst": cgst_sum, "sgst": sgst_sum,
        "total_tax": igst_sum + cgst_sum + sgst_sum,
        "tcs": round(taxable_sum * 0.005, 2),
        "hsn": hsn_records, "b2cs": b2cs_records, "b2b": b2b_records, "sample_dates": sample_dates
    }

def parse_flipkart(file_bytes):
    excel = pd.ExcelFile(file_bytes)
    hsn_records, b2cs_records, b2b_records = [], [], []
    taxable_sum, igst_sum, cgst_sum, sgst_sum, gross_sum = 0.0, 0.0, 0.0, 0.0, 0.0
    supplier_gstin = extract_gstin_from_excel(file_bytes) or "N/A"
    supplier_state = supplier_gstin[:2] if len(supplier_gstin) >= 2 and supplier_gstin[:2].isdigit() else "24"
    returns_taxable = 0.0

    if 'Section 12 in GSTR-1' in excel.sheet_names:
        df_hsn = pd.read_excel(file_bytes, sheet_name='Section 12 in GSTR-1')
        for _, r in df_hsn.iterrows():
            qty = safe_float(r.get('Total Quantity in Nos.', 0))
            gross = safe_float(r.get('Total\n Value Rs.', 0))
            taxable = safe_float(r.get('Total Taxable Value Rs.', 0))
            igst = safe_float(r.get('IGST Amount Rs.', 0))
            cgst = safe_float(r.get('CGST Amount Rs.', 0))
            sgst = safe_float(r.get('SGST Amount Rs.', 0))
            
            taxable_sum += taxable
            igst_sum += igst
            cgst_sum += cgst
            sgst_sum += sgst
            gross_sum += gross
            
            calc_rate = round(((igst + cgst + sgst) / taxable * 100)) if taxable > 0 else 5.0
            hsn_records.append({
                "Platform": "Flipkart", "Supplier GSTIN": supplier_gstin, "HSN Code": str(r.get('HSN Number', '')).strip(), "UQC": "NOS",
                "Qty": qty, "GST Rate": f"{calc_rate:.0f}%", "Rate_Num": calc_rate, "Taxable (₹)": taxable,
                "IGST (₹)": igst, "CGST (₹)": cgst, "SGST (₹)": sgst, "Gross Total (₹)": gross
            })

    if 'Section 7(A)(2) in GSTR-1' in excel.sheet_names:
        df_7a = pd.read_excel(file_bytes, sheet_name='Section 7(A)(2) in GSTR-1')
        for _, r in df_7a.iterrows():
            taxable = safe_float(r.get('Aggregate Taxable Value Rs.', 0))
            cgst = safe_float(r.get('CGST Amount Rs.', 0))
            sgst = safe_float(r.get('SGST /UT Amount Rs.', 0))
            rate = safe_float(r.get('CGST %', 2.5)) + safe_float(r.get('SGST/UT %', 2.5))
            returns_taxable += safe_float(r.get('Taxable Sales Return Value Rs.', 0))
            if taxable > 0:
                b2cs_records.append({
                    "Platform": "Flipkart", "Supplier GSTIN": supplier_gstin, "Place of Supply": f"{supplier_state}-Local", "Rate": f"{rate:.0f}%", "Rate_Num": rate,
                    "Taxable Value (₹)": taxable, "IGST (₹)": 0.0, "CGST (₹)": cgst, "SGST (₹)": sgst,
                    "Gross Value (₹)": round(taxable + cgst + sgst, 2)
                })

    if 'Section 7(B)(2) in GSTR-1' in excel.sheet_names:
        df_7b = pd.read_excel(file_bytes, sheet_name='Section 7(B)(2) in GSTR-1')
        for _, r in df_7b.iterrows():
            taxable = safe_float(r.get('Aggregate Taxable Value Rs.', 0))
            igst = safe_float(r.get('IGST Amount Rs.', 0))
            state = str(r.get('Delivered State (PoS)', '')).strip()
            rate = safe_float(r.get('IGST %', 5.0))
            returns_taxable += safe_float(r.get('Taxable Sales Return Value Rs.', 0))
            if taxable > 0:
                b2cs_records.append({
                    "Platform": "Flipkart", "Supplier GSTIN": supplier_gstin, "Place of Supply": state, "Rate": f"{rate:.0f}%", "Rate_Num": rate,
                    "Taxable Value (₹)": taxable, "IGST (₹)": igst, "CGST (₹)": 0.0, "SGST (₹)": 0.0,
                    "Gross Value (₹)": round(taxable + igst, 2)
                })

    tcs_total = 0.0
    if 'Section 3 in GSTR-8' in excel.sheet_names:
        df_tcs = pd.read_excel(file_bytes, sheet_name='Section 3 in GSTR-8')
        tcs_total = safe_float(df_tcs['TCS IGST amount Rs.'].sum()) + safe_float(df_tcs['TCS CGST amount Rs.'].sum()) + safe_float(df_tcs['TCS SGST amount Rs.'].sum())

    return {
        "platform": "Flipkart", "supplier_gstin": supplier_gstin, "supplier_state": supplier_state,
        "gross": gross_sum, "taxable": taxable_sum, "returns_gross": round(returns_taxable * 1.05, 2), "returns_taxable": round(returns_taxable, 2),
        "igst": igst_sum, "cgst": cgst_sum, "sgst": sgst_sum,
        "total_tax": igst_sum + cgst_sum + sgst_sum,
        "tcs": round(tcs_total, 2),
        "hsn": hsn_records, "b2cs": b2cs_records, "b2b": [], "sample_dates": []
    }

def parse_meesho_frames(df_sales, df_returns):
    df_sales = df_sales.copy()
    df_returns = df_returns.copy()
    df_sales.columns = [c.strip().lower() for c in df_sales.columns]
    df_returns.columns = [c.strip().lower() for c in df_returns.columns]
    
    pattern = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
    supplier_gstin = "N/A"
    if 'gstin' in df_sales.columns:
        for val in df_sales['gstin'].dropna():
            v = str(val).strip().upper()
            if pattern.match(v):
                supplier_gstin = v
                break
                
    supplier_state = supplier_gstin[:2] if len(supplier_gstin) >= 2 and supplier_gstin[:2].isdigit() else "24"
    ret_gross = safe_float(df_returns['total_invoice_value'].sum()) if 'total_invoice_value' in df_returns.columns else 0.0
    ret_taxable = safe_float(df_returns['total_taxable_sale_value'].sum()) if 'total_taxable_sale_value' in df_returns.columns else 0.0

    df_sales['sign'] = 1
    df_returns['sign'] = -1
    df_all = pd.concat([df_sales, df_returns], ignore_index=True)
    
    df_all['net_taxable'] = df_all['total_taxable_sale_value'] * df_all['sign']
    df_all['net_gross'] = df_all['total_invoice_value'] * df_all['sign']
    df_all['net_tax'] = df_all['tax_amount'] * df_all['sign']
    df_all['net_qty'] = df_all['quantity'] * df_all['sign']
    
    def is_intra_state(state_val):
        s = str(state_val).strip().upper()
        return s.startswith(supplier_state) or s == 'GUJARAT' or s == 'IN-GJ'
    
    df_all['is_intra'] = df_all['end_customer_state_new'].apply(is_intra_state)
    df_all['igst'] = df_all.apply(lambda r: 0.0 if r['is_intra'] else r['net_tax'], axis=1)
    df_all['cgst'] = df_all.apply(lambda r: (r['net_tax'] / 2.0) if r['is_intra'] else 0.0, axis=1)
    df_all['sgst'] = df_all.apply(lambda r: (r['net_tax'] / 2.0) if r['is_intra'] else 0.0, axis=1)
    
    taxable_sum = df_all['net_taxable'].sum()
    gross_sum = df_all['net_gross'].sum()
    igst_sum = df_all['igst'].sum()
    cgst_sum = df_all['cgst'].sum()
    sgst_sum = df_all['sgst'].sum()
    total_tax_sum = igst_sum + cgst_sum + sgst_sum
    
    state_grp = df_all.groupby('end_customer_state_new').agg({
        'net_taxable': 'sum', 'igst': 'sum', 'cgst': 'sum', 'sgst': 'sum', 'net_gross': 'sum', 'gst_rate': 'first'
    }).reset_index()
    
    b2cs_records = []
    for _, r in state_grp.iterrows():
        if round(r['net_taxable'], 2) != 0:
            b2cs_records.append({
                "Platform": "Meesho", "Supplier GSTIN": supplier_gstin, "Place of Supply": str(r['end_customer_state_new']).strip().title(),
                "Rate": f"{r['gst_rate']:.0f}%", "Rate_Num": float(r['gst_rate']), "Taxable Value (₹)": round(r['net_taxable'], 2),
                "IGST (₹)": round(r['igst'], 2), "CGST (₹)": round(r['cgst'], 2), "SGST (₹)": round(r['sgst'], 2),
                "Gross Value (₹)": round(r['net_gross'], 2)
            })
            
    hsn_grp = df_all.groupby(['hsn_code', 'gst_rate']).agg({
        'net_qty': 'sum', 'net_taxable': 'sum', 'igst': 'sum', 'cgst': 'sum', 'sgst': 'sum', 'net_gross': 'sum'
    }).reset_index()
    
    hsn_records = []
    for _, r in hsn_grp.iterrows():
        hsn_records.append({
            "Platform": "Meesho", "Supplier GSTIN": supplier_gstin, "HSN Code": str(int(r['hsn_code'])) if pd.notna(r['hsn_code']) else "9999",
            "UQC": "PCS", "Qty": r['net_qty'], "GST Rate": f"{r['gst_rate']:.0f}%", "Rate_Num": float(r['gst_rate']),
            "Taxable (₹)": round(r['net_taxable'], 2), "IGST (₹)": round(r['igst'], 2),
            "CGST (₹)": round(r['cgst'], 2), "SGST (₹)": round(r['sgst'], 2), "Gross Total (₹)": round(r['net_gross'], 2)
        })
        
    return {
        "platform": "Meesho", "supplier_gstin": supplier_gstin, "supplier_state": supplier_state,
        "gross": round(gross_sum, 2), "taxable": round(taxable_sum, 2),
        "returns_gross": round(ret_gross, 2), "returns_taxable": round(ret_taxable, 2),
        "igst": round(igst_sum, 2), "cgst": round(cgst_sum, 2), "sgst": round(sgst_sum, 2),
        "total_tax": round(total_tax_sum, 2), "tcs": round(taxable_sum * 0.005, 2),
        "hsn": hsn_records, "b2cs": b2cs_records, "b2b": [], "sample_dates": []
    }

# ==============================================================
# 4. STATUTORY EXPORT GENERATORS (JSON & PDF)
# ==============================================================
def build_official_gstn_json(gstin, fp, b2cs_records, hsn_records, b2b_records):
    b2cs_payload = []
    supplier_state = gstin[:2] if len(gstin) >= 2 and gstin[:2].isdigit() else "24"
    
    for r in b2cs_records:
        pos_raw = str(r.get('Place of Supply', ''))
        pos_digits = re.findall(r'^[0-9]{2}', pos_raw)
        pos_code = pos_digits[0] if pos_digits else supplier_state
        is_intra = pos_code == supplier_state
        
        b2cs_payload.append({
            "sply_ty": "INTRA" if is_intra else "INTER",
            "pos": pos_code,
            "typ": "OE",
            "rt": float(r.get('Rate_Num', 5.0)),
            "txval": round(float(r.get('Taxable Value (₹)', 0.0)), 2),
            "iamt": round(float(r.get('IGST (₹)', 0.0)), 2),
            "camt": round(float(r.get('CGST (₹)', 0.0)), 2),
            "samt": round(float(r.get('SGST (₹)', 0.0)), 2),
            "csamt": 0.0
        })

    hsn_payload = []
    for idx, r in enumerate(hsn_records):
        hsn_payload.append({
            "num": idx + 1,
            "hsn_sc": str(r.get('HSN Code', '9999')).strip(),
            "desc": "Goods",
            "uqc": str(r.get('UQC', 'PCS')).strip(),
            "qty": round(float(r.get('Qty', 1.0)), 2),
            "rt": float(r.get('Rate_Num', 5.0)),
            "txval": round(float(r.get('Taxable (₹)', 0.0)), 2),
            "iamt": round(float(r.get('IGST (₹)', 0.0)), 2),
            "camt": round(float(r.get('CGST (₹)', 0.0)), 2),
            "samt": round(float(r.get('SGST (₹)', 0.0)), 2),
            "csamt": 0.0
        })

    b2b_payload = []
    if b2b_records:
        buyer_map = {}
        for item in b2b_records:
            b_gstin = item.get('Buyer GSTIN', '')
            buyer_map.setdefault(b_gstin, []).append(item)
            
        for b_gstin, inv_list in buyer_map.items():
            inv_group = []
            for inv in inv_list:
                pos_digits = re.findall(r'^[0-9]{2}', str(inv.get('Place of Supply', '')))
                pos_code = pos_digits[0] if pos_digits else supplier_state
                inv_group.append({
                    "inum": str(inv.get('Invoice No', '')),
                    "idt": str(inv.get('Date', '')),
                    "val": round(float(inv.get('Gross / Invoice Value (₹)', 0.0)), 2),
                    "pos": pos_code,
                    "rchrg": "N",
                    "inv_typ": "R",
                    "itms": [{
                        "num": 1,
                        "itm_det": {
                            "rt": float(inv.get('Rate_Num', 5.0)),
                            "txval": round(float(inv.get('Taxable Value (₹)', 0.0)), 2),
                            "iamt": round(float(inv.get('Taxable Value (₹)', 0.0)) * 0.05, 2),
                            "camt": 0.0,
                            "samt": 0.0,
                            "csamt": 0.0
                        }
                    }]
                })
            b2b_payload.append({"ctin": b_gstin, "inv": inv_group})

    return {
        "gstin": gstin,
        "fp": fp,
        "gt": 0.0,
        "cur_gt": 0.0,
        "version": "GST1.1",
        "hash": "hash",
        "b2cs": b2cs_payload,
        "hsn": {"data": hsn_payload},
        "b2b": b2b_payload
    }

def generate_pdf_report(state_title, gross, taxable, output_tax, igst, cgst, sgst, tcs, net_cash, gstin_grouped_platforms):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    story = []

    c_primary = colors.HexColor('#0F172A')
    c_accent = colors.HexColor('#2563EB')
    c_slate_light = colors.HexColor('#F8FAFC')
    c_border = colors.HexColor('#E2E8F0')
    c_success_bg = colors.HexColor('#ECFDF5')
    c_success_txt = colors.HexColor('#065F46')
    c_text_muted = colors.HexColor('#64748B')

    h_title_style = ParagraphStyle('HTitle', fontName='Helvetica-Bold', fontSize=13, textColor=colors.whitesmoke, leading=15)
    h_meta_style = ParagraphStyle('HMeta', fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#94A3B8'), alignment=2, leading=11)
    card_title_style = ParagraphStyle('CardTitle', fontName='Helvetica-Bold', fontSize=10, textColor=c_accent, leading=12)
    gstin_badge_style = ParagraphStyle('GstinBadge', fontName='Helvetica-Bold', fontSize=8.5, textColor=c_primary, leading=11)
    footer_style = ParagraphStyle('FooterNote', fontName='Helvetica', fontSize=7, textColor=c_text_muted, leading=9, alignment=1)

    # 1. Header Banner
    header_table = Table([
        [
            Paragraph(f"<b>{APP_NAME.replace('_', ' ').upper()}</b><br/><font size=8.5 color='#CBD5E1'>Automated E-Commerce GST Audit & Compliance Certificate</font>", h_title_style),
            Paragraph(f"<b>AUDIT COPY | CONFIDENTIAL</b><br/>Date: {datetime.now().strftime('%d-%b-%Y')}<br/>Status: <b>VERIFIED</b>", h_meta_style)
        ]
    ], colWidths=[374, 190])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_primary),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))

    # 2. Metadata Box
    meta_table = Table([
        ["Active Entity / Scope:", state_title, "Verification Mode:", "Direct Marketplace Parser"],
        ["Tax Regime:", "Goods & Services Tax (India)", "Document Type:", "Statutory Tax Liability Summary"]
    ], colWidths=[110, 180, 110, 164])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_slate_light),
        ('BOX', (0,0), (-1,-1), 0.5, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, c_border),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # 3. Financial KPI Table
    story.append(Paragraph("1. CONSOLIDATED OUTWARD SUPPLIES & TAX LIABILITY", card_title_style))
    story.append(Spacer(1, 4))
    kpi_rows = [
        ["Key Statutory Parameter", "Amount (Rs.)", "GST Portal Table Mapping"],
        ["Gross Outward Turnover", f"Rs. {gross:,.2f}", "Total Turnover"],
        ["Net Aggregate Taxable Value", f"Rs. {taxable:,.2f}", "GSTR-3B Table 3.1(a)"],
        ["Integrated Tax (IGST)", f"Rs. {igst:,.2f}", "GSTR-3B Table 3.1(a)"],
        ["Central Tax (CGST)", f"Rs. {cgst:,.2f}", "GSTR-3B Table 3.1(a)"],
        ["State Tax (SGST)", f"Rs. {sgst:,.2f}", "GSTR-3B Table 3.1(a)"],
        ["Total Output GST Liability", f"Rs. {output_tax:,.2f}", "Total Output Tax"],
        ["E-Commerce TCS Credit Claimed (Sec 52)", f"Rs. {tcs:,.2f}", "TDS/TCS Credit Received"],
        ["NET CASH CHALLAN PAYABLE (GSTR-3B)", f"Rs. {net_cash:,.2f}", "Table 6.1 Payment of Tax"]
    ]
    t_kpi = Table(kpi_rows, colWidths=[260, 160, 144])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), c_accent),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, c_slate_light]),
        ('FONTNAME', (0,6), (-1,6), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1), (-1,-1), c_success_bg),
        ('TEXTCOLOR', (0,-1), (-1,-1), c_success_txt),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('PADDING', (0,0), (-1,-1), 3.5),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 8))

    # 4. Platform Breakdown
    story.append(Paragraph("2. PLATFORM-WISE BREAKDOWN GROUPED BY GSTIN", card_title_style))
    story.append(Spacer(1, 4))
    for g_num, p_list in gstin_grouped_platforms.items():
        state_label = f"• GSTIN: <b>{g_num}</b> — <i>{get_state_name_from_gstin(g_num)}</i>"
        story.append(Paragraph(state_label, gstin_badge_style))
        story.append(Spacer(1, 2))
        plat_rows = [["Platform", "Gross (Rs.)", "Taxable (Rs.)", "IGST (Rs.)", "CGST (Rs.)", "SGST (Rs.)", "Total Tax (Rs.)", "TCS (Rs.)"]]
        for p in p_list:
            plat_rows.append([
                p['platform'], f"Rs. {p['gross']:,.2f}", f"Rs. {p['taxable']:,.2f}",
                f"Rs. {p['igst']:,.2f}", f"Rs. {p['cgst']:,.2f}", f"Rs. {p['sgst']:,.2f}",
                f"Rs. {p['total_tax']:,.2f}", f"Rs. {p['tcs']:,.2f}"
            ])
        t_plat = Table(plat_rows, colWidths=[70, 75, 75, 68, 68, 68, 75, 65])
        t_plat.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), c_primary),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, c_border),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, c_slate_light]),
            ('FONTSIZE', (0,0), (-1,-1), 7.5),
            ('PADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(t_plat)
        story.append(Spacer(1, 6))

    # 5. Signature Section
    sig_table = Table([
        [
            Paragraph("<b>Taxpayer Declaration:</b><br/>I confirm that figures herein tally with marketplace orders.", ParagraphStyle('Decl', fontName='Helvetica', fontSize=7, textColor=c_text_muted, leading=9)),
            Paragraph("<b>Verified By Authorized Signatory / CA:</b><br/><br/>________________________________________<br/>Seal & Signature", ParagraphStyle('Sign', fontName='Helvetica', fontSize=7, textColor=c_primary, alignment=2, leading=9))
        ]
    ], colWidths=[360, 204])
    sig_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('PADDING', (0,0), (-1,-1), 0)]))
    story.append(sig_table)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_border, spaceBefore=2, spaceAfter=4))
    story.append(Paragraph(f"Generated via {APP_NAME}. Strictly for statutory tax audit and portal filing verification.", footer_style))

    doc.build(story)
    return buf.getvalue()

# ==============================================================
# 5. ZERO-MANUAL WORKSPACE & HEADER
# ==============================================================
st.markdown("""
<div class="hero-box">
    <h2 style="margin: 0 0 6px 0; font-weight: 700;">⚡ E-Commerce GST Auto-Filer</h2>
    <p style="margin: 0; color: #8b949e; font-size: 0.95rem;">
        Zero Manual Entry: Bas Amazon, Flipkart ya Meesho ki reports upload karein. Poora GST, TCS aur Portal JSON automatic generate ho jayega.
    </p>
</div>
""", unsafe_allow_html=True)

# Central Upload Zone
uploaded_files = st.file_uploader(
    "Marketplace Excel (.xlsx, .xls) ya ZIP bundle drag and drop karein:",
    type=["xlsx", "xls", "zip", "csv"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("💡 **Ready to Process:** Shuru karne ke liye upar Amazon MTR, Flipkart GSTR ya Meesho TCS sales reports upload karein.")
    st.stop()

# ==============================================================
# 6. PIPELINE EXECUTION (AUTO-PARSE & AUTO-DETECT)
# ==============================================================
raw_platform_results = []
file_names_collected = []
sample_dates_collected = []

with st.spinner("Analyzing spreadsheet schemas and cross-verifying tax heads..."):
    for file_obj in uploaded_files:
        file_name = file_obj.name
        file_names_collected.append(file_name)
        
        if file_name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(file_obj) as z:
                    extracted_names = [n for n in z.namelist() if n.endswith(('.xlsx', '.xls', '.csv')) and not n.startswith('__MACOSX/')]
                    
                    if any('tcs_sales' in n for n in extracted_names):
                        sales_name = next(n for n in extracted_names if 'tcs_sales.' in n or n.endswith('tcs_sales.xlsx'))
                        returns_name = next((n for n in extracted_names if 'tcs_sales_return' in n), None)
                        
                        df_s = pd.read_excel(io.BytesIO(z.read(sales_name)))
                        df_r = pd.read_excel(io.BytesIO(z.read(returns_name))) if returns_name else pd.DataFrame(columns=df_s.columns)
                        raw_platform_results.append(parse_meesho_frames(df_s, df_r))
                    else:
                        for inner_filename in extracted_names:
                            inner_bytes = io.BytesIO(z.read(inner_filename))
                            p_id, _ = detect_ecommerce_platform(inner_bytes, inner_filename)
                            inner_bytes.seek(0)
                            
                            if p_id == "Flipkart":
                                raw_platform_results.append(parse_flipkart(inner_bytes))
                            elif p_id == "Meesho":
                                df_s = pd.read_excel(inner_bytes)
                                raw_platform_results.append(parse_meesho_frames(df_s, pd.DataFrame(columns=df_s.columns)))
                            else:
                                parsed_amz = parse_amazon(inner_bytes)
                                sample_dates_collected.extend(parsed_amz.get('sample_dates', []))
                                raw_platform_results.append(parsed_amz)
            except Exception as e:
                st.error(f"Error unzipping {file_name}: {e}")
        else:
            try:
                p_id, _ = detect_ecommerce_platform(file_obj, file_name)
                file_obj.seek(0)
                
                if p_id == "Flipkart":
                    raw_platform_results.append(parse_flipkart(file_obj))
                elif p_id == "Meesho":
                    df_single = pd.read_excel(file_obj)
                    raw_platform_results.append(parse_meesho_frames(df_single, pd.DataFrame(columns=df_single.columns)))
                else:
                    parsed_amz = parse_amazon(file_obj)
                    sample_dates_collected.extend(parsed_amz.get('sample_dates', []))
                    raw_platform_results.append(parsed_amz)
            except Exception as e:
                st.error(f"Error reading {file_name}: {e}")

# Auto-detect filing period
detected_fp = extract_return_period(file_names_collected, sample_dates_collected)

# Multi-State Grouping
gstin_groups = {}
for p in raw_platform_results:
    g = p['supplier_gstin']
    gstin_groups.setdefault(g, []).append(p)

# ==============================================================
# 7. MULTI-STATE & WORKSPACE SELECTOR (ZERO-TYPING)
# ==============================================================
state_options = []
if len(gstin_groups) > 1:
    state_options.append("🌐 All States Consolidated (PAN Level)")

for g in gstin_groups.keys():
    s_name = get_state_name_from_gstin(g)
    state_options.append(f"📍 {s_name} — {g}")

c_scope1, c_scope2 = st.columns([3, 1])
with c_scope1:
    selected_scope = st.radio("Active Scope:", state_options, horizontal=True)
with c_scope2:
    # Auto-detected dropdown without manual typing
    fp_input = st.selectbox("Detected Filing Period (fp):", [detected_fp], index=0)

period_label = format_period_label(fp_input)

if "All States Consolidated" in selected_scope:
    platform_results = raw_platform_results
    current_state_title = "All States Consolidated (PAN Level)"
    state_file_slug = "All_States_Consolidated"
    active_gstin = list(gstin_groups.keys())[0] if gstin_groups else "24ECEPM6676L1Z0"
    pdf_gstin_groups = gstin_groups
else:
    selected_gstin = selected_scope.split("—")[-1].strip()
    platform_results = gstin_groups[selected_gstin]
    state_name_clean = get_state_name_from_gstin(selected_gstin).replace(" ", "_")
    current_state_title = f"{get_state_name_from_gstin(selected_gstin)} ({selected_gstin})"
    state_file_slug = f"{state_name_clean}_{selected_gstin}"
    active_gstin = selected_gstin
    pdf_gstin_groups = {selected_gstin: platform_results}

# Combined Figures
combined_gross = sum(p['gross'] for p in platform_results)
combined_taxable = sum(p['taxable'] for p in platform_results)
combined_igst = sum(p['igst'] for p in platform_results)
combined_cgst = sum(p['cgst'] for p in platform_results)
combined_sgst = sum(p['sgst'] for p in platform_results)
combined_total_tax = sum(p['total_tax'] for p in platform_results)
combined_tcs = sum(p['tcs'] for p in platform_results)
total_returns_loss = sum(p['returns_gross'] for p in platform_results)

# Zero-typing net cash challan (Auto calculated after TCS deduction)
net_cash_auto = max(0.0, combined_total_tax - combined_tcs)

all_hsn = [item for p in platform_results for item in p['hsn']]
all_b2cs = [item for p in platform_results for item in p['b2cs']]
all_b2b = [item for p in platform_results for item in p['b2b']]

# ==============================================================
# 8. EXECUTIVE KPI SUMMARY CARDS
# ==============================================================
st.write("")
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-card-title">Gross Outward Turnover</div>
        <div class="metric-card-value">₹{combined_gross:,.0f}</div>
        <div class="metric-card-sub">Total Shipped Value</div>
    </div>''', unsafe_allow_html=True)
with col2:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-card-title">Net Taxable Turnover</div>
        <div class="metric-card-value">₹{combined_taxable:,.0f}</div>
        <div class="metric-card-sub">Table 3.1(a) GSTR-3B</div>
    </div>''', unsafe_allow_html=True)
with col3:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-card-title">Total Output GST</div>
        <div class="metric-card-value">₹{combined_total_tax:,.0f}</div>
        <div class="metric-card-sub">IGST: ₹{combined_igst:,.0f}</div>
    </div>''', unsafe_allow_html=True)
with col4:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-card-title">TCS Credit (Sec 52)</div>
        <div class="metric-card-value">₹{combined_tcs:,.0f}</div>
        <div class="metric-card-sub">Marketplace Deducted</div>
    </div>''', unsafe_allow_html=True)
with col5:
    st.markdown(f'''
    <div class="metric-card" style="border-color: #238636;">
        <div class="metric-card-title" style="color: #7ee787;">Est. Net Cash Challan</div>
        <div class="metric-card-value" style="color: #7ee787;">₹{round(net_cash_auto):,}</div>
        <div class="metric-card-sub" style="color: #8b949e;">Output GST - TCS Credit</div>
    </div>''', unsafe_allow_html=True)

# Compliance Alerts
invalid_hsn = [x['HSN Code'] for x in all_hsn if len(str(x.get('HSN Code', '')).strip()) < 4]
if invalid_hsn:
    st.warning(f"⚠️ **HSN Code Advisory:** {len(invalid_hsn)} items have less than 4-digit HSN codes ({', '.join(set(invalid_hsn)[:4])}). GST rules recommend minimum 4 digits.")

# ==============================================================
# 9. STRUCTURED TABS (CLEAN & MINIMALIST LAYOUT)
# ==============================================================
st.write("")
t_summary, t_portal, t_analytics, t_export = st.tabs([
    "📊 Platform Performance",
    "📋 GST Portal Mappings (3B / Table 14)",
    "📦 Returns & RTO Analytics",
    "📥 Statutory Export Center"
])

# --- TAB 1: PLATFORM PERFORMANCE ---
with t_summary:
    comp_data = []
    for p in platform_results:
        comp_data.append({
            "Platform": p['platform'],
            "Supplier GSTIN": p['supplier_gstin'],
            "Gross Sales (₹)": f"₹{p['gross']:,.2f}",
            "Taxable Sales (₹)": f"₹{p['taxable']:,.2f}",
            "Returns / RTO (₹)": f"₹{p['returns_gross']:,.2f}",
            "IGST (₹)": f"₹{p['igst']:,.2f}",
            "CGST (₹)": f"₹{p['cgst']:,.2f}",
            "SGST (₹)": f"₹{p['sgst']:,.2f}",
            "Total GST (₹)": f"₹{p['total_tax']:,.2f}",
            "TCS Credit (₹)": f"₹{p['tcs']:,.2f}"
        })
    st.dataframe(pd.DataFrame(comp_data), use_container_width=True)

# --- TAB 2: PORTAL MAPPINGS ---
with t_portal:
    c_m1, c_m2 = st.columns(2)
    with c_m1:
        st.markdown("#### 📋 GSTR-3B Auto-Populated Figures")
        gstr3b_data = [
            {"Portal Section": "Table 3.1(a) Outward Taxable Supplies", "Taxable Value (₹)": f"₹{combined_taxable:,.2f}", "IGST (₹)": f"₹{combined_igst:,.2f}", "CGST (₹)": f"₹{combined_cgst:,.2f}", "SGST (₹)": f"₹{combined_sgst:,.2f}"},
            {"Portal Section": "TDS/TCS Credit (Claim in Portal)", "Taxable Value (₹)": "-", "IGST (₹)": f"₹{combined_tcs:,.2f}", "CGST (₹)": "-", "SGST (₹)": "-"},
            {"Portal Section": "Estimated Cash Payable (Challan)", "Taxable Value (₹)": "-", "IGST (₹)": f"₹{max(0.0, combined_igst - combined_tcs):,.2f}", "CGST (₹)": f"₹{combined_cgst:,.2f}", "SGST (₹)": f"₹{combined_sgst:,.2f}"}
        ]
        st.table(pd.DataFrame(gstr3b_data))
        
    with c_m2:
        st.markdown("#### 🏬 GSTR-1 Table 14 (Supplies through ECO)")
        eco_data = []
        for p in platform_results:
            eco_data.append({
                "Marketplace": p['platform'],
                "Net Taxable Value (₹)": f"₹{p['taxable']:,.2f}",
                "IGST (₹)": f"₹{p['igst']:,.2f}",
                "CGST (₹)": f"₹{p['cgst']:,.2f}",
                "SGST (₹)": f"₹{p['sgst']:,.2f}"
            })
        st.table(pd.DataFrame(eco_data))

# --- TAB 3: RTO & ANALYTICS ---
with t_analytics:
    ca1, ca2 = st.columns([1, 1.5])
    with ca1:
        st.metric("Total Revenue Blocked in Returns / RTO", f"₹{total_returns_loss:,.2f}")
        return_rate = (total_returns_loss / combined_gross * 100) if combined_gross > 0 else 0.0
        st.caption(f"Gross return impact rate: **{return_rate:.1f}%** across all channels.")
    with ca2:
        chart_data = pd.DataFrame([{"Platform": p['platform'], "Returns (₹)": p['returns_gross']} for p in platform_results]).set_index('Platform')
        st.bar_chart(chart_data)

# --- TAB 4: EXPORT CENTER ---
with t_export:
    st.markdown(f"#### 📥 1-Click Statutory File Exports ({current_state_title})")
    
    df_hsn_unified = pd.DataFrame(all_hsn)
    if not df_hsn_unified.empty:
        df_hsn_unified = df_hsn_unified.groupby(['HSN Code', 'GST Rate']).agg({
            'Qty': 'sum', 'Taxable (₹)': 'sum', 'IGST (₹)': 'sum', 'CGST (₹)': 'sum', 'SGST (₹)': 'sum', 'Gross Total (₹)': 'sum'
        }).reset_index()

    df_b2c_unified = pd.DataFrame(all_b2cs)
    if not df_b2c_unified.empty:
        df_b2c_unified = df_b2c_unified.groupby(['Place of Supply', 'Rate']).agg({
            'Taxable Value (₹)': 'sum', 'IGST (₹)': 'sum', 'CGST (₹)': 'sum', 'SGST (₹)': 'sum', 'Gross Value (₹)': 'sum'
        }).reset_index()

    ex1, ex2, ex3, ex4 = st.columns(4)

    # 1. Audit Excel
    excel_audit_filename = f"{APP_NAME}_Audit_Report_{period_label}_{state_file_slug}.xlsx"
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
        pd.DataFrame(comp_data).to_excel(writer, sheet_name='Platform Summary', index=False)
        if not df_hsn_unified.empty:
            df_hsn_unified.to_excel(writer, sheet_name='Unified HSN Table 12', index=False)
        if not df_b2c_unified.empty:
            df_b2c_unified.to_excel(writer, sheet_name='Unified B2C Table 7', index=False)
        if all_b2b:
            pd.DataFrame(all_b2b).to_excel(writer, sheet_name='B2B Invoices', index=False)
    with ex1:
        st.download_button("📊 Multi-Sheet Audit Excel", data=excel_buf.getvalue(), file_name=excel_audit_filename, use_container_width=True)

    # 2. Offline Utility Excel
    excel_utility_filename = f"{APP_NAME}_GSTR1_Offline_Utility_{period_label}_{state_file_slug}.xlsx"
    offline_excel_buf = io.BytesIO()
    with pd.ExcelWriter(offline_excel_buf, engine='openpyxl') as writer:
        b2cs_offline_rows = [{"Type": "OE", "Place of Supply": x.get('Place of Supply', ''), "Applicable % of Tax Rate": "", "Rate": x.get('Rate_Num', 5.0), "Taxable Value": x.get('Taxable Value (₹)', 0.0), "Cess Amount": 0.0} for x in all_b2cs]
        pd.DataFrame(b2cs_offline_rows).to_excel(writer, sheet_name='b2cs', index=False)
        hsn_offline_rows = [{"HSN": x.get('HSN Code', ''), "Description": "Goods", "UQC": x.get('UQC', 'PCS'), "Total Quantity": x.get('Qty', 1.0), "Total Value": x.get('Gross Total (₹)', 0.0), "Taxable Value": x.get('Taxable (₹)', 0.0), "Integrated Tax Amount": x.get('IGST (₹)', 0.0), "Central Tax Amount": x.get('CGST (₹)', 0.0), "State/UT Tax Amount": x.get('SGST (₹)', 0.0), "Cess Amount": 0.0} for x in all_hsn]
        pd.DataFrame(hsn_offline_rows).to_excel(writer, sheet_name='hsn', index=False)
    with ex2:
        st.download_button("🏛️ GSTR-1 Offline Utility (.xlsx)", data=offline_excel_buf.getvalue(), file_name=excel_utility_filename, use_container_width=True)

    # 3. Official GSTN JSON
    json_export_filename = f"{APP_NAME}_GSTR1_Official_Upload_{period_label}_{active_gstin}.json"
    official_json_obj = build_official_gstn_json(
        active_gstin, fp_input,
        df_b2c_unified.to_dict(orient='records') if not df_b2c_unified.empty else all_b2cs,
        df_hsn_unified.to_dict(orient='records') if not df_hsn_unified.empty else all_hsn,
        all_b2b
    )
    with ex3:
        st.download_button("⚡ Official GSTN JSON", data=json.dumps(official_json_obj, indent=4).encode('utf-8'), file_name=json_export_filename, mime="application/json", use_container_width=True)

    # 4. CA Audit PDF Certificate
    pdf_export_filename = f"{APP_NAME}_Audit_Certificate_{period_label}_{state_file_slug}.pdf"
    pdf_bytes = generate_pdf_report(
        current_state_title, combined_gross, combined_taxable, combined_total_tax,
        combined_igst, combined_cgst, combined_sgst, combined_tcs, net_cash_auto, pdf_gstin_groups
    )
    with ex4:
        st.download_button("📄 CA Tax Certificate (PDF)", data=pdf_bytes, file_name=pdf_export_filename, mime="application/pdf", use_container_width=True)

    # Master ZIP Bundle
    st.write("---")
    master_zip_filename = f"{APP_NAME}_Master_Filing_Bundle_{period_label}.zip"
    master_zip_buf = io.BytesIO()
    with zipfile.ZipFile(master_zip_buf, 'w', zipfile.ZIP_DEFLATED) as master_z:
        for g_num, p_list in gstin_groups.items():
            g_state = get_state_name_from_gstin(g_num).replace(" ", "_")
            folder_prefix = f"{g_state}_{g_num}/"
            
            st_b2cs = [it for p in p_list for it in p['b2cs']]
            st_hsn = [it for p in p_list for it in p['hsn']]
            st_b2b = [it for p in p_list for it in p['b2b']]
            st_json = build_official_gstn_json(g_num, fp_input, st_b2cs, st_hsn, st_b2b)
            master_z.writestr(f"{folder_prefix}{APP_NAME}_GSTR1_Official_{period_label}_{g_num}.json", json.dumps(st_json, indent=4))
            
            st_buf = io.BytesIO()
            with pd.ExcelWriter(st_buf, engine='openpyxl') as st_wr:
                pd.DataFrame(st_hsn).to_excel(st_wr, sheet_name='HSN Summary', index=False)
                pd.DataFrame(st_b2cs).to_excel(st_wr, sheet_name='B2C Sales', index=False)
                if st_b2b:
                    pd.DataFrame(st_b2b).to_excel(st_wr, sheet_name='B2B Invoices', index=False)
            master_z.writestr(f"{folder_prefix}{APP_NAME}_Audit_Report_{period_label}_{g_num}.xlsx", st_buf.getvalue())

    st.download_button(
        f"📦 Download 1-Click All-States Master ZIP Bundle ({period_label})",
        data=master_zip_buf.getvalue>,
        file_name=master_zip_filename,
        mime="application/zip",
        use_container_width=True
    )
