# streamlit_subscriptions.py
# NATUVISIO - Abonelik Paneli (Iyzico Sandbox hazır)
# Türkçe arayüz - Streamlit UI
# Flask optional (webhook) - if Flask is not installed, webhook is disabled gracefully.

import os
import json
import uuid
import time
import sqlite3
import threading
from datetime import datetime
import urllib.parse

import streamlit as st
import streamlit.components.v1 as components

# Optional imports
try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except Exception:
    FLASK_AVAILABLE = False

try:
    import requests
except Exception:
    requests = None

# -----------------------
# CONFIG / ORTAM DEGISKENLERI (ENV vars recommended)
# -----------------------
st.set_page_config(page_title="NATUVISIO - Abonelik", layout="wide")

LOGO_URL = os.getenv("LOGO_URL", "https://res.cloudinary.com/deb1j92hy/image/upload/f_auto,q_auto/v1764805291/natuvisio_logo_gtqtfs.png")
BG_IMAGE = os.getenv("BG_IMAGE", "https://res.cloudinary.com/deb1j92hy/image/upload/v1764848571/man-standing-brown-mountain-range_elqddb.webp")

# Iyzico (varsayılan sandbox endpoints; production değiştirin)
IYZICO_API_KEY = os.getenv("IYZICO_API_KEY", "")
IYZICO_SECRET_KEY = os.getenv("IYZICO_SECRET_KEY", "")
IYZICO_BASE_API = os.getenv("IYZICO_BASE_API", "https://sandbox-api.iyzipay.com")
IYZICO_CHECKOUT_BASE = os.getenv("IYZICO_CHECKOUT_URL", "https://sandbox-checkout.iyzipay.com/checkoutform/initialize")

# Plan ref kodları (iyzico dashboard / partner panelden alınacak)
WELLBEING_PLAN_REF = os.getenv("WELLBEING_PLAN_REF", "")
OXIFIT_PLAN_REF = os.getenv("OXIFIT_PLAN_REF", "")

# Webhook callback base url (ngrok / public endpoint) örn: https://abcd-1234.ngrok.io
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL", "")

DATA_DB = os.getenv("SUBSCRIPTIONS_DB", "natuvisio_subscriptions.sqlite")

ADMIN_PASS = os.getenv("ADMIN_PASS", "admin2025")

# -----------------------
# STYLES
# -----------------------
def load_css():
    st.markdown(f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
      .stApp {{
        background-image: linear-gradient(rgba(255,255,255,0.08), rgba(255,255,255,0.08)), url("{BG_IMAGE}");
        background-size: cover;
        background-position: center;
        font-family: Inter, sans-serif;
      }}
      .glass-card {{
        background: rgba(255,255,255,0.66);
        border-radius: 12px;
        padding: 18px;
        box-shadow: 0 8px 30px rgba(0,0,0,0.08);
      }}
      .muted {{ color: #6b7280; font-size:13px; }}
      .big-title {{ font-size:20px; font-weight:700; color:#164e33; }}
      iframe {{ border: none; border-radius: 8px; }}
      #MainMenu, header, footer {{ visibility: hidden; }}
    </style>
    """, unsafe_allow_html=True)

# -----------------------
# DB (sqlite) - basit, ACID-safe
# -----------------------
def init_db():
    conn = sqlite3.connect(DATA_DB, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        sku TEXT,
        plan_reference TEXT,
        iyzico_checkout_token TEXT,
        iyzico_subscription_reference TEXT,
        status TEXT,
        customer_name TEXT,
        customer_email TEXT,
        customer_phone TEXT,
        created_at TEXT,
        updated_at TEXT,
        raw_payload TEXT
    )
    """)
    conn.commit()
    return conn

conn = init_db()

def save_subscription_record(record: dict):
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO subscriptions (id, sku, plan_reference, iyzico_checkout_token, iyzico_subscription_reference, status, customer_name, customer_email, customer_phone, created_at, updated_at, raw_payload)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.get("id"),
        record.get("sku"),
        record.get("plan_reference"),
        record.get("iyzico_checkout_token"),
        record.get("iyzico_subscription_reference"),
        record.get("status"),
        record.get("customer_name"),
        record.get("customer_email"),
        record.get("customer_phone"),
        record.get("created_at"),
        record.get("updated_at"),
        json.dumps(record.get("raw_payload", {}), ensure_ascii=False)
    ))
    conn.commit()

def update_subscription_by_iyzico_ref(iyz_ref, status, payload):
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("UPDATE subscriptions SET status=?, updated_at=?, raw_payload=? WHERE iyzico_subscription_reference=?", (status, now, json.dumps(payload, ensure_ascii=False), iyz_ref))
    if cur.rowcount == 0:
        # not found -> insert minimal record
        cur.execute("""INSERT INTO subscriptions (id, sku, plan_reference, iyzico_checkout_token, iyzico_subscription_reference, status, created_at, updated_at, raw_payload)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (str(uuid.uuid4()), "", "", "", iyz_ref, status, now, now, json.dumps(payload, ensure_ascii=False)))
    conn.commit()

def fetch_subscriptions(limit=200):
    cur = conn.cursor()
    cur.execute("SELECT id, sku, plan_reference, iyzico_subscription_reference, status, customer_name, customer_email, customer_phone, created_at FROM subscriptions ORDER BY created_at DESC LIMIT ?", (limit,))
    return cur.fetchall()

# -----------------------
# IYZICO helper
# -----------------------
def ensure_requests():
    if requests is None:
        raise RuntimeError("requests kütüphanesi bulunamadı. 'pip install requests' çalıştırın.")

def create_subscription_checkout(plan_reference, customer_email, customer_name, gsm_number, conversation_id=None):
    """
    Iyzico sandbox: POST /v2/subscription/checkout-form/initialize
    Returns checkout_url, raw_response
    """
    ensure_requests()
    if not IYZICO_API_KEY or not IYZICO_SECRET_KEY:
        raise RuntimeError("IYZICO_API_KEY veya IYZICO_SECRET_KEY tanımlı değil. Ortam değişkenlerini ayarlayın.")
    url = f"{IYZICO_BASE_API}/v2/subscription/checkout-form/initialize"
    payload = {
        "locale": "tr",
        "conversationId": conversation_id or str(uuid.uuid4()),
        "pricingPlanReferenceCode": plan_reference,
        "callbackUrl": f"{CALLBACK_BASE_URL}/iyzico_callback" if CALLBACK_BASE_URL else "",
        "customer": {
            "email": customer_email,
            "name": (customer_name.split(" ")[0] if customer_name else ""),
            "surname": (" ".join(customer_name.split(" ")[1:]) if customer_name and len(customer_name.split(" "))>1 else ""),
            "gsmNumber": gsm_number
        }
    }
    headers = {"Content-Type": "application/json"}
    # Basic auth with API key / secret may work; some iyzico clients expect special headers. This is sandbox approach.
    resp = requests.post(url, headers=headers, auth=(IYZICO_API_KEY, IYZICO_SECRET_KEY), json=payload, timeout=20)
    if resp.status_code != 200 and resp.status_code != 201:
        raise RuntimeError(f"Iyzico hata ({resp.status_code}): {resp.text}")
    data = resp.json()
    token = data.get("token") or data.get("checkoutFormContent")
    # token may be direct checkout content; if it's token, compose checkout url
    checkout_url = None
    if isinstance(token, str) and token.startswith("https://"):
        checkout_url = token
    elif token and len(token) < 400:
        checkout_url = f"{IYZICO_CHECKOUT_BASE}/{token}"
    else:
        # sometimes API returns HTML form; we can embed it
        checkout_url = None
    return checkout_url, data

# -----------------------
# Flask webhook (optional)
# -----------------------
if FLASK_AVAILABLE:
    flask_app = Flask(__name__)

    @flask_app.route("/iyzico_callback", methods=["POST"])
    def iyzico_callback():
        payload = request.get_json(force=True)
        # Try multiple possible keys for subscription reference
        iyz_ref = payload.get("subscriptionReferenceCode") or payload.get("subscriptionReference") or payload.get("subscriptionReferenceId") or payload.get("subscriptionCode")
        status = payload.get("status") or payload.get("paymentStatus") or "unknown"
        if iyz_ref:
            update_subscription_by_iyzico_ref(iyz_ref, status, payload)
        else:
            # store raw payload
            update_subscription_by_iyzico_ref(str(uuid.uuid4()), "callback_received", payload)
        return jsonify({"ok": True}), 200

    def run_flask():
        flask_app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

    def ensure_flask_started():
        if not hasattr(ensure_flask_started, "started"):
            t = threading.Thread(target=run_flask, daemon=True)
            t.start()
            ensure_flask_started.started = True
            time.sleep(0.4)
else:
    def ensure_flask_started():
        return

# -----------------------
# UI: login + subscription flow
# -----------------------
def login_screen():
    load_css()
    st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.image(LOGO_URL, width=120)
        st.markdown("<div class='big-title'>NATUVISIO - Abonelik Yönetimi</div>", unsafe_allow_html=True)
        st.markdown("<div class='muted'>Admin veya Partner hesabınız ile giriş yapın.</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        mode = st.radio("Giriş Tipi", ["Admin", "Partner"], horizontal=True)
        if mode == "Admin":
            pwd = st.text_input("Admin Şifre", type="password", key="admin_pwd")
            if st.button("Giriş Yap (Admin)"):
                if pwd == ADMIN_PASS:
                    st.session_state.admin_logged_in = True
                    st.success("Admin olarak giriş yapıldı.")
                    st.experimental_rerun()
                else:
                    st.error("Hatalı şifre")
        else:
            # basit partner auth (demo): email & password karşılaştırması için local sqlite 'partners' table isteğe bağlı
            st.info("Partner girişi: demo modu. Email yazıp 'Partner Giriş'e basın.")
            email = st.text_input("E-posta (partner demo)", key="partner_email")
            if st.button("Partner Giriş"):
                if email:
                    st.session_state.is_partner_logged_in = True
                    st.session_state.partner_brand = "HAKI HEAL"  # demo default
                    st.success("Partner oturumu açıldı (demo).")
                    st.experimental_rerun()

# -----------------------
# ADMIN DASHBOARD (basit)
# -----------------------
def admin_dashboard():
    load_css()
    ensure_flask_started()
    st.markdown("<div class='big-title'>Admin - Abonelik Yönetimi</div>", unsafe_allow_html=True)
    st.markdown("<div class='muted'>Iyzico Sandbox ile abonelik oturumları oluşturun ve kayıtları görüntüleyin.</div>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("### Sanity Check / Ayarlar")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("Iyzico API Key set:")
        st.code(IYZICO_API_KEY or "— boş —", language="text")
    with col2:
        st.write("Iyzico Secret Key set:")
        st.code(IYZICO_SECRET_KEY or "— boş —", language="text")
    with col3:
        st.write("Callback base URL:")
        st.code(CALLBACK_BASE_URL or "— boş —", language="text")

    st.markdown("---")
    st.markdown("### Abonelik Oluştur (Sandbox)")
    sku_choice = st.selectbox("Ürün SKU", ["BLACK STUFF WELLBEING", "BLACK STUFF OXIFIT"])
    plan_map = {"BLACK STUFF WELLBEING": WELLBEING_PLAN_REF, "BLACK STUFF OXIFIT": OXIFIT_PLAN_REF}
    plan_ref = plan_map.get(sku_choice)

    st.markdown("#### Müşteri Bilgileri")
    c1, c2 = st.columns(2)
    with c1:
        cust_name = st.text_input("Ad Soyad", value="Musteri Ornek")
    with c2:
        cust_email = st.text_input("E-posta", value="muster@ornek.com")
    cust_phone = st.text_input("Telefon (örn. +90555...)", value="+905555555555")

    if st.button("Abonelik Ödeme Sayfası Oluştur ve iframe göster"):
        try:
            if not plan_ref:
                st.error("Bu SKU için plan referansı ayarlı değil. WELLBEING_PLAN_REF veya OXIFIT_PLAN_REF ortam değişkenlerini ayarlayın.")
            else:
                checkout_url, raw = create_subscription_checkout(plan_ref, cust_email, cust_name, cust_phone)
                rec_id = str(uuid.uuid4())
                rec = {
                    "id": rec_id,
                    "sku": sku_choice,
                    "plan_reference": plan_ref,
                    "iyzico_checkout_token": raw.get("token", "") or "",
                    "iyzico_subscription_reference": raw.get("subscriptionReference") or raw.get("subscriptionReferenceCode") or "",
                    "status": "pending",
                    "customer_name": cust_name,
                    "customer_email": cust_email,
                    "customer_phone": cust_phone,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "raw_payload": raw
                }
                save_subscription_record(rec)
                st.success("Abonelik kaydı oluşturuldu. Checkout iframe aşağıda gösteriliyor (sandbox).")
                if checkout_url:
                    components.html(f'<iframe src="{checkout_url}" width="100%" height="720"></iframe>', height=720)
                else:
                    # fallback: show raw payload content (maybe contains checkout form HTML)
                    st.code(json.dumps(raw, ensure_ascii=False, indent=2))
        except Exception as e:
            st.exception(e)

    st.markdown("---")
    st.markdown("### Kayıtlı Abonelikler (Son 200)")
    rows = fetch_subscriptions(200)
    if rows:
        for r in rows:
            st.markdown(f"**ID:** {r[0]}  —  **SKU:** {r[1]}  —  **IyzRef:** {r[3] or '<boş>'}  —  **Durum:** {r[4]}  —  **Müşteri:** {r[5]} / {r[6]}")
    else:
        st.info("Henüz abonelik kaydı yok.")

    st.markdown("---")
    if st.button("Çıkış"):
        st.session_state.admin_logged_in = False
        st.experimental_rerun()

# -----------------------
# PARTNER DASHBOARD (demo, hafif)
# -----------------------
def partner_dashboard():
    load_css()
    st.markdown("<div class='big-title'>Partner - Abonelik Özet (Demo)</div>", unsafe_allow_html=True)
    st.markdown("<div class='muted'>Partnerler için temel görünüm: abonelik durumu ve müşteri listesi.</div>", unsafe_allow_html=True)
    st.markdown("---")
    rows = fetch_subscriptions(200)
    st.markdown("### Abonelikleriniz (demo filtre yok)")
    if rows:
        for r in rows:
            st.markdown(f"• {r[0]} | {r[1]} | {r[4]} | {r[5]} — {r[6]}")
    else:
        st.info("Kayıtlı abonelik yok.")
    if st.button("Çıkış (Partner)"):
        st.session_state.is_partner_logged_in = False
        st.session_state.partner_brand = None
        st.experimental_rerun()

# -----------------------
# MAIN
# -----------------------
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False
if "is_partner_logged_in" not in st.session_state:
    st.session_state.is_partner_logged_in = False
if "partner_brand" not in st.session_state:
    st.session_state.partner_brand = None

if __name__ == "__main__":
    # Show optional warning if requests missing
    if requests is None:
        st.error("Uyarı: 'requests' kütüphanesi yüklü değil. Lütfen 'pip install requests' çalıştırın. API çağrıları çalışmaz.")
    if not IYZICO_API_KEY or not IYZICO_SECRET_KEY:
        st.warning("Iyzico API anahtarları boş. Ortam değişkenlerini ayarlayın (IYZICO_API_KEY, IYZICO_SECRET_KEY). Sandbox testi için gerekli.")
    if not CALLBACK_BASE_URL:
        st.info("CALLBACK_BASE_URL boş: webhook callback'leri alınmayacaktır. Geliştirme için ngrok kullanın ve bu değeri ayarlayın.")
    if FLASK_AVAILABLE:
        st.success("Flask bulundu: webhook endpoint'leri otomatik olarak başlatılacak.")
    else:
        st.info("Flask yüklü değil: webhook endpoint devre dışı kalacak. 'pip install flask' ile etkinleştirin.")

    if st.session_state.admin_logged_in:
        admin_dashboard()
    elif st.session_state.is_partner_logged_in:
        partner_dashboard()
    else:
        login_screen()
