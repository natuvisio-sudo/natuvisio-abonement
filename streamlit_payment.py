# natuvisio_subscribe.py
# Run: streamlit run natuvisio_subscribe.py
# Requires: pip install streamlit flask requests

import os
import json
import requests
import sqlite3
import threading
import time
import uuid
from datetime import datetime

import streamlit as st
from flask import Flask, request, jsonify
import streamlit.components.v1 as components

# -----------------------
# CONFIG / ORTAM DEGISKENLERI
# -----------------------
IYZICO_API_KEY = os.getenv("IYZICO_API_KEY", "")
IYZICO_SECRET_KEY = os.getenv("IYZICO_SECRET_KEY", "")
BASE_API = os.getenv("IYZICO_BASE_API", "https://sandbox-api.iyzipay.com")
BASE_CHECKOUT = os.getenv("IYZICO_CHECKOUT_URL", "https://sandbox-checkout.iyzipay.com/checkoutform/initialize")

WELLBEING_PLAN_REF = os.getenv("WELLBEING_PLAN_REF", "")
OXIFIT_PLAN_REF = os.getenv("OXIFIT_PLAN_REF", "")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL", "")  # example: https://abcd1234.ngrok.io

DB_PATH = "subscriptions.db"

# -----------------------
# BASLANGIC: DB OLUŞTUR
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        sku TEXT,
        plan_reference TEXT,
        iyzico_subscription_reference TEXT,
        status TEXT,
        customer_email TEXT,
        customer_name TEXT,
        created_at TEXT,
        updated_at TEXT,
        raw_payload TEXT
    )
    """)
    conn.commit()
    return conn

conn = init_db()

# -----------------------
# IYZICO CHECKOUT TOKEN CREATION
# -----------------------
def create_subscription_checkout_token(plan_reference, customer_email, customer_name, gsm_number, conversation_id=None):
    """
    Iyzico subscription checkout token oluşturur.
    Dönen token ile iframe url oluşturulur.
    """
    if not IYZICO_API_KEY or not IYZICO_SECRET_KEY:
        raise RuntimeError("IYZICO API anahtarları ortam değişkenlerinde yok. IYZICO_API_KEY ve IYZICO_SECRET_KEY ayarlayın.")

    url = f"{BASE_API}/v2/subscription/checkout-form/initialize"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "locale": "tr",
        "conversationId": conversation_id or str(uuid.uuid4()),
        "pricingPlanReferenceCode": plan_reference,
        "callbackUrl": f"{CALLBACK_BASE_URL}/iyzico_callback",
        "customer": {
            "email": customer_email,
            "name": customer_name.split(" ")[0] if customer_name else "",
            "surname": " ".join(customer_name.split(" ")[1:]) if customer_name and len(customer_name.split(" "))>1 else "",
            "gsmNumber": gsm_number
        }
    }

    # istek
    resp = requests.post(url, headers=headers, auth=(IYZICO_API_KEY, IYZICO_SECRET_KEY), data=json.dumps(payload), timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Iyzico API hata: {resp.status_code} {resp.text}")
    data = resp.json()
    token = data.get("token")
    if not token:
        raise RuntimeError(f"Iyzico token gelmedi: {data}")
    checkout_url = f"{BASE_CHECKOUT}/{token}"
    return checkout_url, data

# -----------------------
# DB KAYIT/GUNCELLEME
# -----------------------
def save_subscription_record(sku, plan_reference, iyzico_ref, status, email, name, raw_payload):
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    id_ = str(uuid.uuid4())
    cur.execute("""
      INSERT INTO subscriptions (id, sku, plan_reference, iyzico_subscription_reference, status, customer_email, customer_name, created_at, updated_at, raw_payload)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (id_, sku, plan_reference, iyzico_ref, status, email, name, now, now, json.dumps(raw_payload)))
    conn.commit()
    return id_

def update_subscription_record_by_iyzico_ref(iyzico_ref, status, raw_payload):
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("""
      SELECT id FROM subscriptions WHERE iyzico_subscription_reference = ?
    """, (iyzico_ref,))
    row = cur.fetchone()
    if row:
        cur.execute("""
          UPDATE subscriptions SET status = ?, updated_at = ?, raw_payload = ? WHERE iyzico_subscription_reference = ?
        """, (status, now, json.dumps(raw_payload), iyzico_ref))
        conn.commit()
        return row[0]
    else:
        # yoksa yeni kayıt yap (opsiyonel)
        cur.execute("""
          INSERT INTO subscriptions (id, sku, plan_reference, iyzico_subscription_reference, status, created_at, updated_at, raw_payload)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), "", "", iyzico_ref, status, now, now, json.dumps(raw_payload)))
        conn.commit()
        return None

# -----------------------
# FLASK WEBHOOK (background thread)
# -----------------------
flask_app = Flask(__name__)

@flask_app.route("/iyzico_callback", methods=["POST"])
def iyzico_callback():
    try:
        payload = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": "invalid json", "msg": str(e)}), 400

    # Iyzico callback payload içeriğine göre parse edin.
    # Dokümanda farklı isimler olabilir. Burada genel yaklaşımdır.
    # Örnek field: payload["subscriptionReferenceCode"] veya payload["subscriptionReference"]
    # Örnek status field: payload["status"]
    # Bu alanlar sandbox testlerinde gelen gerçek payload ile eşleşecek şekilde uyarlanmalı.
    iyzico_ref = payload.get("subscriptionReferenceCode") or payload.get("subscriptionReference") or payload.get("subscriptionReferenceId")
    status = payload.get("status") or payload.get("paymentStatus") or "unknown"

    # DB'ye kaydet/guncelle
    if iyzico_ref:
        update_subscription_record_by_iyzico_ref(iyzico_ref, status, payload)
    else:
        # alert: payload şekli beklenmedikse kaydet
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        cur.execute("""
          INSERT INTO subscriptions (id, sku, plan_reference, iyzico_subscription_reference, status, created_at, updated_at, raw_payload)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), "", "", "", "callback_received", now, now, json.dumps(payload)))
        conn.commit()

    # Iyzico için 200 dön
    return jsonify({"ok": True}), 200

def run_flask():
    # internal debug server, production için ayrı bir deploy öneririm
    flask_app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

# Start flask in background thread if not already started
def ensure_flask_started():
    if not hasattr(ensure_flask_started, "started"):
        t = threading.Thread(target=run_flask, daemon=True)
        t.start()
        ensure_flask_started.started = True
        # Allow server to spin up
        time.sleep(0.5)

# -----------------------
# STREAMLIT UI
# -----------------------
st.set_page_config(page_title="NATUVISIO - Abonelik", layout="centered")
st.markdown("<style>body { font-family: Inter, system-ui, -apple-system; }</style>", unsafe_allow_html=True)

st.title("NATUVISIO — Abonelik Sistemi (Iyzico Sandbox)")

# başlat flask webhook
ensure_flask_started()

st.info("Not: Webhook URL'nizin Iyzico sandbox veya production panelinde /iyzico_callback olacak şekilde açık olduğundan emin olun. Lokal geliştirme için ngrok kullanabilirsiniz.")

# seçilecek SKU ve plan referansları
sku_choice = st.radio("Hangi ürün için abonelik başlatmak istiyorsunuz?", ("BLACK STUFF WELLBEING", "BLACK STUFF OXIFIT"))

plan_map = {
    "BLACK STUFF WELLBEING": WELLBEING_PLAN_REF,
    "BLACK STUFF OXIFIT": OXIFIT_PLAN_REF
}

plan_ref = plan_map.get(sku_choice)
if not plan_ref:
    st.warning("Bu SKU için plan referansı ortam değişkenlerinde tanımlı değil. WELLBEING_PLAN_REF veya OXIFIT_PLAN_REF ayarlayın.")

st.markdown("---")
st.subheader("Müşteri Bilgileri")
col1, col2 = st.columns(2)
with col1:
    cust_name = st.text_input("Ad Soyad", value="Musteri Örnek")
with col2:
    cust_email = st.text_input("E-posta", value="muster@ornek.com")
cust_phone = st.text_input("Telefon (örn. +90555...)", value="+905555555555")

st.selectbox("Abonelik Frekansı (Iyzico planınızı bu frekanslarla oluşturun)", ["Aylık (30 gün)", "Her 60 gün", "Custom - yönetim"], index=0, disabled=True)

discount_choice = st.selectbox("İndirim Uygulamak istiyor musunuz?", ["Yok", "İlk Ödeme İndirimi", "Her Ödeme İndirimi - plan ile ayrı oluşturun"], index=0)
if discount_choice != "Yok":
    st.info("İndirimler genelde Iyzico tarafında ayrı bir pricing plan oluşturarak uygulanır. Burada ilk ödeme indirimi için ayrı plan referansı kullanın.")

st.markdown("---")

# Abone ol butonu → checkout token oluştur ve iframe göster
if st.button("Abone Ol - Ödeme Sayfasını Aç"):
    if not plan_ref:
        st.error("Plan referansı eksik. Ortam değişkenlerini kontrol edin.")
    elif not CALLBACK_BASE_URL:
        st.error("CALLBACK_BASE_URL ortam değişkeni ayarlanmamış. Webhook için gerekli.")
    else:
        try:
            checkout_url, raw = create_subscription_checkout_token(plan_ref, cust_email, cust_name, cust_phone)
            st.success("Ödeme oturumu oluşturuldu. Aşağıdaki ödeme penceresinden kart bilgilerini girin.")
            # DB'ye ön kayıt (iyzico_ref henüz gelmediği için boş bırakıyoruz, webhook ile güncellenecek)
            save_subscription_record(sku_choice, plan_ref, raw.get("subscriptionReference") or raw.get("subscriptionReferenceCode") or "", "pending", cust_email, cust_name, raw)
            # iframe embed (Streamlit components)
            iframe_html = f"""<iframe src="{checkout_url}" width="100%" height="760" frameborder="0" scrolling="no"></iframe>"""
            components.html(iframe_html, height=760)
        except Exception as e:
            st.exception(e)

st.markdown("---")
st.subheader("Yönetim: Kayıtlı Abonelikler (yerel DB)")
try:
    cur = conn.cursor()
    cur.execute("SELECT id, sku, plan_reference, iyzico_subscription_reference, status, customer_email, created_at FROM subscriptions ORDER BY created_at DESC LIMIT 200")
    rows = cur.fetchall()
    if rows:
        for r in rows:
            st.write({
                "id": r[0],
                "sku": r[1],
                "plan_reference": r[2],
                "iyzico_subscription_reference": r[3],
                "status": r[4],
                "customer_email": r[5],
                "created_at": r[6]
            })
    else:
        st.write("Henüz abonelik kaydı yok.")
except Exception as e:
    st.error("DB okuma hatası: " + str(e))

st.markdown("#### Notlar")
st.markdown("""
- Iyzico'da indirimli ilk ödeme için ayrı bir 'pricing plan' oluşturmanız en doğru yöntemdir. 
- Production geçmeden önce tüm callback ve plan referanslarını doğrulayın.
- Lokal geliştirme için ngrok kullanın: `ngrok http 8080` ve CALLBACK_BASE_URL olarak ngrok URL'sini girin.
""")
