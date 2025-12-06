# streamlit_subscriptions_products.py
# NATUVISIO - Abonelik Formu + Ürün Kartları + İndirim Planları + Sistem Kontrolleri
# Run: streamlit run streamlit_subscriptions_products.py

import os
import json
import uuid
import sqlite3
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import streamlit as st
import streamlit.components.v1 as components

# optional
try:
    import requests
except Exception:
    requests = None

st.set_page_config(page_title="NATUVISIO - Abonelikler", layout="wide")

# -----------------------
# AYARLAR / ORTAM DEGISKENLERI
# -----------------------
LOGO_URL = os.getenv("LOGO_URL", "https://res.cloudinary.com/deb1j92hy/image/upload/f_auto,q_auto/v1764805291/natuvisio_logo_gtqtfs.png")
BG_IMAGE = os.getenv("BG_IMAGE", "https://res.cloudinary.com/deb1j92hy/image/upload/v1764848571/man-standing-brown-mountain-range_elqddb.webp")

IYZICO_API_KEY = os.getenv("IYZICO_API_KEY", "")
IYZICO_SECRET_KEY = os.getenv("IYZICO_SECRET_KEY", "")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL", "")  # örn: https://abcd-1234.ngrok.io

DB_FILE = os.getenv("SUBSCRIPTIONS_DB", "natuvisio_subscriptions.sqlite")

# ÜRÜNLER (fiyatlar talimatına göre)
PRODUCTS = {
    "BLACK STUFF WELLBEING": {
        "sku": "BS-WELL-01",
        "price": 3500.0,
        "short": "Günlük mikrobiom destek formülü (30 kapsül)."
    },
    "BLACK STUFF OXIFIT": {
        "sku": "BS-OXIFIT-01",
        "price": 3400.0,
        "short": "Performans & oksijen taşıma destek formülü (30 kapsül)."
    }
}

# -----------------------
# STIL
# -----------------------
def load_css():
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    .stApp {{
        background-image: linear-gradient(rgba(255,255,255,0.06), rgba(255,255,255,0.06)), url("{BG_IMAGE}");
        background-size: cover;
        background-position: center;
        font-family: Inter, sans-serif;
    }}
    .product-card {{
        background: rgba(255,255,255,0.88);
        border-radius: 14px;
        padding: 18px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.06);
        text-align: left;
    }}
    .price-tag {{
        font-size:20px; font-weight:700; color:#164e33;
    }}
    .muted {{ color:#6b7280; font-size:13px; }}
    iframe {{ border:none; border-radius:8px; }}
    #MainMenu, header, footer {{ visibility: hidden; }}
    .ops-check {{ background: rgba(0,0,0,0.03); padding:12px; border-radius:8px; }}
    </style>
    """, unsafe_allow_html=True)

load_css()

# -----------------------
# DB - sqlite
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        created_at TEXT,
        email TEXT,
        name TEXT,
        phone TEXT,
        address TEXT,
        sku TEXT,
        base_price REAL,
        discount_plan TEXT,
        discount_details TEXT,
        frequency TEXT,
        schedule_json TEXT,
        iyzico_token TEXT,
        iyzico_ref TEXT,
        status TEXT
    )
    """)
    conn.commit()
    return conn

conn = init_db()

def save_sub_to_db(record: dict):
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO subscriptions (id, created_at, email, name, phone, address, sku, base_price, discount_plan, discount_details, frequency, schedule_json, iyzico_token, iyzico_ref, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.get("id"),
        record.get("created_at"),
        record.get("email"),
        record.get("name"),
        record.get("phone"),
        record.get("address"),
        record.get("sku"),
        record.get("base_price"),
        record.get("discount_plan"),
        json.dumps(record.get("discount_details", {}), ensure_ascii=False),
        record.get("frequency"),
        json.dumps(record.get("schedule", {}), ensure_ascii=False),
        record.get("iyzico_token", ""),
        record.get("iyzico_ref", ""),
        record.get("status", "created")
    ))
    conn.commit()

# -----------------------
# İndirim (discount) hesaplama
# - plan_key: 'none' | '10x2' | '15x3'
# - returns schedule: list of {month_index, price}
# -----------------------
def decimal_round(v):
    return float(Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def build_price_schedule(base_price: float, plan_key: str, months: int = 12):
    """
    plan_key:
      'none'  -> no discount
      '10x2'  -> 10% discount for first 2 months
      '15x3'  -> 15% discount for first 3 months
    returns list of tuples (month_index, price)
    """
    schedule = []
    for m in range(1, months+1):
        if plan_key == "10x2" and m <= 2:
            price = base_price * 0.90
        elif plan_key == "15x3" and m <= 3:
            price = base_price * 0.85
        else:
            price = base_price
        schedule.append({"month": m, "price": decimal_round(price)})
    return schedule

# -----------------------
# UI: Ürün kartları
# -----------------------
st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)

col_h1, col_h2 = st.columns([3,2])
with col_h1:
    st.image(LOGO_URL, width=120)
    st.title("NATUVISIO — Abonelikler")
    st.write("Aşağıdan ürünü seçin, abonelik planını belirleyin ve formu doldurarak devam edin.")
with col_h2:
    st.markdown("<div class='ops-check'><strong>Hızlı Bilgi</strong><br>2 Ürün, başlangıç fiyatları gösteriliyor. İlk dönemlerde seçtiğiniz indirim uygulamaları tablo halinde gösterilecek.</div>", unsafe_allow_html=True)

st.markdown("---")

prod_cols = st.columns(2)
prod_keys = list(PRODUCTS.keys())
for i, pk in enumerate(prod_keys):
    col = prod_cols[i]
    with col:
        p = PRODUCTS[pk]
        card_html = f"""
        <div class="product-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-weight:800; font-size:18px;">{pk}</div>
                    <div class="muted" style="margin-top:6px;">{p['short']}</div>
                </div>
                <div style="text-align:right;">
                    <div class="price-tag">{p['price']:,.0f}₺</div>
                    <div class="muted" style="font-size:12px;">SKU: {p['sku']}</div>
                </div>
            </div>
            <div style="margin-top:14px; display:flex; gap:8px;">
                <button id="sel_{i}" onclick="document.querySelector('input[name=\\'product_select\\'][value=\\'{pk}\\']').click();" style="background:#5b7354;color:white;border:none;padding:10px 12px;border-radius:8px;cursor:pointer;">Seç</button>
                <button id="info_{i}" onclick="alert('Ürün: {pk}\\nFiyat: {p['price']:,.0f}₺\\nSKU: {p['sku']}');" style="background:transparent;border:1px solid rgba(0,0,0,0.06);padding:10px 12px;border-radius:8px;cursor:pointer;">Detay</button>
            </div>
        </div>
        """
        components.html(card_html, height=160)

st.markdown("---")

# -----------------------
# Abonelik formu (sol) ve fiyat takvimi (sağ)
# -----------------------
col_left, col_right = st.columns([2,1])

with col_left:
    st.subheader("Abonelik Formu")
    # product selection input (hidden radio used by JS above)
    prod_choice = st.radio("Ürün Seçimi", prod_keys, index=0, key="product_select")
    email = st.text_input("E-posta", placeholder="ornek@eposta.com")
    name = st.text_input("Ad - Soyad", placeholder="Adınız Soyadınız")
    phone = st.text_input("Telefon (örn. +90555...)", placeholder="+905...")
    address = st.text_area("Adres (Teslimat adresi)", placeholder="Cadde, Mahalle, Şehir, Posta Kodu", height=80)
    st.markdown("**Abonelik İndirim Planı (başlangıç)**")
    discount_plan = st.selectbox("İndirim planı", [
        ("none", "İndirim Yok"),
        ("10x2", "10% İndirim — İlk 2 Ay"),
        ("15x3", "15% İndirim — İlk 3 Ay")
    ], format_func=lambda x: x[1], index=0)
    # discount_plan is tuple -> need key
    discount_key = discount_plan[0]
    freq = st.selectbox("Periyot", ["30 gün (Aylık)"], index=0)
    note = st.text_area("Not (opsiyonel)", height=60)

    if st.button("Aboneliği Oluştur ve Önizle"):
        # validation
        if not (email and name and phone and address):
            st.error("Lütfen e-posta, isim, telefon ve adres girin.")
        else:
            base_price = PRODUCTS[prod_choice]["price"]
            schedule = build_price_schedule(base_price, discount_key, months=12)
            total_first_6 = sum(item["price"] for item in schedule[:6])
            rec_id = "NV-SUB-" + datetime.utcnow().strftime("%Y%m%d%H%M%S") + "-" + str(uuid.uuid4())[:6]
            record = {
                "id": rec_id,
                "created_at": datetime.utcnow().isoformat(),
                "email": email,
                "name": name,
                "phone": phone,
                "address": address,
                "sku": prod_choice,
                "base_price": base_price,
                "discount_plan": discount_key,
                "discount_details": {"desc": dict(discount_plan)[discount_key] if isinstance(discount_plan, tuple) else discount_key},
                "frequency": freq,
                "schedule": schedule,
                "iyzico_token": "",
                "iyzico_ref": "",
                "status": "previewed"
            }
            # Save preview state in session to show right panel and allow final confirm
            st.session_state["last_preview"] = record
            st.success(f"Önizleme oluşturuldu — Abonelik ID: {rec_id}\nİlk 6 aylık maliyet: {total_first_6:,.2f}₺")
            st.experimental_rerun()

with col_right:
    st.subheader("Fiyat Takvimi — Önizleme")
    preview = st.session_state.get("last_preview", None)
    if preview is None:
        st.info("Form doldurup 'Aboneliği Oluştur ve Önizle' butonuna basın. Seçilen indirim planına göre aylık ücret tablosu burada gösterilecek.")
    else:
        st.markdown(f"**Ürün:** {preview['sku']}  \n**Taban Fiyat:** {preview['base_price']:,.2f}₺  \n**İndirim Planı:** {preview['discount_plan']}")
        schedule = preview["schedule"]
        # show table
        rows_html = "<table style='width:100%; border-collapse: collapse;'>"
        rows_html += "<tr><th style='text-align:left; padding:6px;'>Ay</th><th style='text-align:right; padding:6px;'>Aylık Ücret</th></tr>"
        for s in schedule[:12]:
            rows_html += f"<tr><td style='padding:6px; border-bottom:1px solid rgba(0,0,0,0.06);'>Ay {s['month']}</td><td style='padding:6px; text-align:right; border-bottom:1px solid rgba(0,0,0,0.06);'>{s['price']:,.2f}₺</td></tr>"
        rows_html += "</table>"
        components.html(rows_html, height=320)
        total_12 = sum(x["price"] for x in schedule)
        total_6 = sum(x["price"] for x in schedule[:6])
        st.markdown(f"**Toplam (12 ay):** {total_12:,.2f}₺  \n**Toplam (ilk 6 ay):** {total_6:,.2f}₺")
        # final confirm button
        if st.button("✅ Aboneliği Onayla ve Kaydet"):
            # finalize: save to DB as active (status 'active' is sample; in real system should wait for payment confirmation)
            preview["status"] = "active"  # demo: mark active
            save_sub_to_db(preview)
            st.success("Abonelik veritabanına kaydedildi ve 'active' olarak işaretlendi. (Gerçek çekim için ödeme sağlayıcı ile entegrasyon gereklidir.)")
            # clear preview
            del st.session_state["last_preview"]
            st.experimental_rerun()

st.markdown("---")

# -----------------------
# Systems Operational Check (bottom)
# -----------------------
st.markdown("## Systems Operational Check")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("**requests**")
    if requests is not None:
        st.success("requests yüklü")
    else:
        st.error("requests bulunamadı — Iyzico API çağrıları çalışmaz (pip install requests).")

with col2:
    st.markdown("**IYZICO Anahtarları**")
    if IYZICO_API_KEY and IYZICO_SECRET_KEY:
        st.success("Iyzico API anahtarları ayarlı")
    else:
        st.warning("Iyzico anahtarları eksik. Sandbox/production çağrıları başarısız olur.")

with col3:
    st.markdown("**DB (yazma)**")
    try:
        # quick write test
        test_id = "TEST-" + str(uuid.uuid4())[:6]
        cur = conn.cursor()
        cur.execute("INSERT INTO subscriptions (id, created_at, email, name, phone, address, sku, base_price, discount_plan, discount_details, frequency, schedule_json, iyzico_token, iyzico_ref, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (test_id, datetime.utcnow().isoformat(), "test@local", "test", "+000", "nowhere", "TEST", 0.0, "none", "{}", "30 gün", "[]", "", "", "test"))
        conn.commit()
        # delete immediately
        cur.execute("DELETE FROM subscriptions WHERE id=?", (test_id,))
        conn.commit()
        st.success("DB yazma ok")
    except Exception as e:
        st.error(f"DB yazılamıyor: {e}")

with col4:
    st.markdown("**Webhook (CALLBACK_BASE_URL)**")
    if CALLBACK_BASE_URL:
        if requests is None:
            st.warning("CALLBACK_BASE_URL ayarlı ama 'requests' yok, canlı test yapılamaz.")
        else:
            try:
                # Do not perform external request if env variable points to production; do a HEAD with short timeout, but wrap in try
                resp = requests.head(CALLBACK_BASE_URL, timeout=3)
                st.success(f"Callback URL erişilebilir (status: {resp.status_code})")
            except Exception as e:
                st.warning(f"Callback URL test başarısız: {e}")
    else:
        st.info("CALLBACK_BASE_URL boş — webhook callback alınmaz (geliştirme için ngrok önerilir).")

st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
st.markdown("<div style='font-size:13px; color:#6b7280;'>Not: Bu demo uygulama ödeme sağlayıcı entegrasyon mantığını gösterir. Gerçek üretimde ödeme onayı, webhook doğrulama ve güvenlik kontrolleri eklenmelidir.</div>", unsafe_allow_html=True)

# small debug viewer
if st.checkbox("🔍 Debug: Son 10 abonelik kaydını göster"):
    cur = conn.cursor()
    cur.execute("SELECT id, created_at, email, sku, base_price, discount_plan, status FROM subscriptions ORDER BY created_at DESC LIMIT 10")
    rows = cur.fetchall()
    st.table(rows)
