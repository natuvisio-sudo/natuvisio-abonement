# streamlit_subscriptions_form.py
# NATUVISIO - Abonelik Formu (tek sayfa, Türkçe)
# - E-posta, İsim, Telefon, Adres
# - 2 ürün: BLACK STUFF WELLBEING, BLACK STUFF OXIFIT
# - Abonelik frekansı, kupon, not
# - Iyzico checkout oluşturma (sandbox) - opsiyonel
# - Kayıt: sqlite (natuvisio_subscriptions.sqlite)
# - Derin abonelik/iş akışı açıklamaları alt kısımda

import os
import json
import uuid
import sqlite3
import time
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

# Optional: requests for Iyzico API calls
try:
    import requests
except Exception:
    requests = None

st.set_page_config(page_title="NATUVISIO - Abonelik Formu", layout="wide")

# -----------------------
# AYARLAR / ORTAM DEGISKENLERI
# -----------------------
LOGO_URL = os.getenv("LOGO_URL", "https://res.cloudinary.com/deb1j92hy/image/upload/f_auto,q_auto/v1764805291/natuvisio_logo_gtqtfs.png")
BG_IMAGE = os.getenv("BG_IMAGE", "https://res.cloudinary.com/deb1j92hy/image/upload/v1764848571/man-standing-brown-mountain-range_elqddb.webp")

IYZICO_API_KEY = os.getenv("IYZICO_API_KEY", "")
IYZICO_SECRET_KEY = os.getenv("IYZICO_SECRET_KEY", "")
IYZICO_BASE_API = os.getenv("IYZICO_BASE_API", "https://sandbox-api.iyzipay.com")
IYZICO_CHECKOUT_BASE = os.getenv("IYZICO_CHECKOUT_URL", "https://sandbox-checkout.iyzipay.com/checkoutform/initialize")
CALLBACK_BASE_URL = os.getenv("CALLBACK_BASE_URL", "")  # ngrok veya public endpoint

DB_FILE = os.getenv("SUBSCRIPTIONS_DB", "natuvisio_subscriptions.sqlite")

# ÜRÜN HARITASI (SKU ve temel fiyat gösterimi - fiyat örnektir)
PRODUCTS = {
    "BLACK STUFF WELLBEING": {"sku": "BS-WELL-01", "price": 299, "desc": "Günlük gut mikrobiom destek formülü (30 kapsül)."},
    "BLACK STUFF OXIFIT": {"sku": "BS-OXIFIT-01", "price": 349, "desc": "Performans & oksijen taşıma destek formülü (30 kapsül)."}
}

# PLAN REFERANSLARI (Iyzico panelden alınacaksa buraya koyun)
WELL_PLAN_REF = os.getenv("WELL_PLAN_REF", "")
OXI_PLAN_REF = os.getenv("OXI_PLAN_REF", "")

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
      .card {{
        background: rgba(255,255,255,0.78);
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.07);
      }}
      .muted {{ color: #6b7280; font-size:13px; }}
      h1 {{ color: #234e35; }}
      iframe {{ border: none; border-radius: 8px; box-shadow: 0 8px 30px rgba(0,0,0,0.15); }}
      #MainMenu, header, footer {{ visibility: hidden; }}
    </style>
    """, unsafe_allow_html=True)

# -----------------------
# DB
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
        sku_price REAL,
        frequency TEXT,
        coupon TEXT,
        note TEXT,
        iyzico_token TEXT,
        iyzico_ref TEXT,
        status TEXT,
        raw_response TEXT
    )
    """)
    conn.commit()
    return conn

conn = init_db()

def save_record(rec):
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO subscriptions (id, created_at, email, name, phone, address, sku, sku_price, frequency, coupon, note, iyzico_token, iyzico_ref, status, raw_response)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rec.get("id"),
        rec.get("created_at"),
        rec.get("email"),
        rec.get("name"),
        rec.get("phone"),
        rec.get("address"),
        rec.get("sku"),
        rec.get("sku_price"),
        rec.get("frequency"),
        rec.get("coupon"),
        rec.get("note"),
        rec.get("iyzico_token"),
        rec.get("iyzico_ref"),
        rec.get("status"),
        json.dumps(rec.get("raw_response", {}), ensure_ascii=False)
    ))
    conn.commit()

# -----------------------
# Iyzico helper (simple)
# -----------------------
def ensure_requests():
    if requests is None:
        raise RuntimeError("requests kütüphanesi yüklü değil. 'pip install requests' çalıştırın.")

def create_iyzico_checkout(plan_ref, customer):
    """
    Basit sandbox çağrısı - gerçek üretime göre uyarlanmalı.
    Döndürülen token/checkout formu embed edilecek şekilde işlenecek.
    """
    ensure_requests()
    if not IYZICO_API_KEY or not IYZICO_SECRET_KEY:
        raise RuntimeError("Iyzico anahtarları (env) bulunamadı.")
    url = f"{IYZICO_BASE_API}/v2/subscription/checkout-form/initialize"
    payload = {
        "locale": "tr",
        "conversationId": str(uuid.uuid4()),
        "pricingPlanReferenceCode": plan_ref,
        "callbackUrl": f"{CALLBACK_BASE_URL}/iyzico_callback" if CALLBACK_BASE_URL else "",
        "customer": {
            "email": customer["email"],
            "name": customer["name"].split(" ")[0] if customer["name"] else "",
            "surname": " ".join(customer["name"].split(" ")[1:]) if customer["name"] and len(customer["name"].split(" "))>1 else "",
            "gsmNumber": customer["phone"]
        }
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, auth=(IYZICO_API_KEY, IYZICO_SECRET_KEY), json=payload, timeout=20)
    return resp

# -----------------------
# UI: form
# -----------------------
load_css()
st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)

colL, colR = st.columns([2,1])

with colL:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.image(LOGO_URL, width=120)
    st.header("NATUVISIO - Abonelik Formu")
    st.write("Lütfen formu doldurun. Abonelik, seçilen ürüne göre her periyotta otomatik ödemedir ve paketler kapınıza gönderilir.")
    st.markdown("### Müşteri Bilgileri")
    email = st.text_input("E-posta", placeholder="ornek@eposta.com")
    name = st.text_input("Ad - Soyad", placeholder="Adınız Soyadınız")
    phone = st.text_input("Telefon (örn. +90555...)", placeholder="+905...")
    address = st.text_area("Adres (Teslimat adresi)", placeholder="Cadde, Mahalle, Şehir, Posta Kodu", height=80)

    st.markdown("### Ürün Seçimi")
    sku = st.selectbox("Ürün", list(PRODUCTS.keys()))
    sku_meta = PRODUCTS[sku]
    st.markdown(f"**{sku}** — {sku_meta['desc']}  \nFiyat (örnek): **{sku_meta['price']}₺**")

    st.markdown("### Abonelik Seçenekleri")
    freq = st.selectbox("Frekans", ["30 gün (aylık)", "60 gün", "90 gün"])
    trial = st.selectbox("İlk ödeme / deneme", ["İlk ödeme tam", "İlk ödeme indirimli (%20)", "7 günlük ücretsiz deneme (sonra ücretlendirme)"])
    coupon = st.text_input("Kupon Kodu (opsiyonel)")
    note = st.text_area("Not / Sipariş açıklaması (opsiyonel)", height=60)

    st.markdown("### Onay & Gizlilik")
    agree = st.checkbox("Abonelik Şartlarını, İptal Politikası ve Otomatik Ödeme Talimatını okudum ve kabul ediyorum.", value=False)

    if st.button("Aboneliği Oluştur ve Ödeme Sayfasına Git"):
        if not (email and name and phone and address):
            st.error("Lütfen e-posta, isim, telefon ve adres bilgilerini doldurun.")
        elif not agree:
            st.error("Abonelik için gizlilik/şartlar onayı gereklidir.")
        else:
            # kaydı oluştur
            rec_id = "NV-SUB-" + datetime.utcnow().strftime("%Y%m%d%H%M%S") + "-" + str(uuid.uuid4())[:6]
            rec = {
                "id": rec_id,
                "created_at": datetime.utcnow().isoformat(),
                "email": email,
                "name": name,
                "phone": phone,
                "address": address,
                "sku": sku,
                "sku_price": sku_meta["price"],
                "frequency": freq,
                "coupon": coupon,
                "note": note,
                "iyzico_token": "",
                "iyzico_ref": "",
                "status": "created",
                "raw_response": {}
            }
            save_record(rec)
            st.success(f"Abonelik kaydı oluşturuldu — ID: {rec_id}")

            # Iyzico checkout (opsiyonel): plan referansı varsa çağır
            plan_ref = WELL_PLAN_REF if sku == "BLACK STUFF WELLBEING" else OXI_PLAN_REF
            if plan_ref and requests is not None:
                try:
                    st.info("Iyzico checkout oluşturuluyor (sandbox)...")
                    resp = create_iyzico_checkout(plan_ref, {"email": email, "name": name, "phone": phone})
                    if resp.status_code in (200,201):
                        data = resp.json()
                        token = data.get("token") or data.get("checkoutFormContent") or ""
                        # bazı durumlarda token HTML form içerir
                        # iframe için token varsa checkout url oluştur
                        checkout_url = None
                        if isinstance(token, str) and token.startswith("https://"):
                            checkout_url = token
                        elif token and len(token)<400:
                            checkout_url = f"{IYZICO_CHECKOUT_BASE}/{token}"
                        # güncelle DB
                        cur = conn.cursor()
                        cur.execute("UPDATE subscriptions SET iyzico_token=?, iyzico_ref=?, status=?, raw_response=? WHERE id=?",
                                    (token, data.get("subscriptionReference") or data.get("subscriptionReferenceCode") or "", "checkout_ready", json.dumps(data, ensure_ascii=False), rec_id))
                        conn.commit()
                        if checkout_url:
                            st.success("Ödeme sayfası hazır. Aşağıdaki iframe üzerinden ödeme tamamlanabilir.")
                            components.html(f'<iframe src="{checkout_url}" width="100%" height="700"></iframe>', height=700)
                        else:
                            st.warning("Iyzico'dan beklenen iframe URL'si gelmedi. Raw response gösteriliyor.")
                            st.code(json.dumps(data, ensure_ascii=False, indent=2))
                    else:
                        st.error(f"Iyzico hata: {resp.status_code} — {resp.text[:200]}")
                        # DB'yi hata ile güncelle
                        cur = conn.cursor()
                        cur.execute("UPDATE subscriptions SET status=?, raw_response=? WHERE id=?", ("iyzico_error", json.dumps({"status": resp.status_code, "text": resp.text}, ensure_ascii=False), rec_id))
                        conn.commit()
                except Exception as e:
                    st.exception(e)
                    cur = conn.cursor()
                    cur.execute("UPDATE subscriptions SET status=?, raw_response=? WHERE id=?", ("iyzico_exception", json.dumps({"error": str(e)}, ensure_ascii=False), rec_id))
                    conn.commit()
            else:
                # Iyzico plan yoksa veya requests yoksa sadece kayıt oluşturuldu uyarısı
                if not plan_ref:
                    st.info("Bu SKU için Iyzico plan referansı tanımlı değil. (WELL_PLAN_REF / OXI_PLAN_REF). Sadece kayıt oluşturuldu.")
                else:
                    st.info("Requests kütüphanesi veya Iyzico anahtarları eksik. Sadece kayıt oluşturuldu.")

    st.markdown("</div>", unsafe_allow_html=True)

with colR:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("## Özet & Hızlı Bilgiler")
    st.markdown(f"**Seçili Ürün:** {st.session_state.get('sku_selected', '—')}")
    st.markdown("**Abonelik Avantajları:**")
    st.write("- Otomatik teslimat her seçilen periyotta (ör: 30 gün).")
    st.write("- İlk ödeme seçenekleri: tam, indirimli veya deneme.")
    st.write("- İptal: Müşteri istediği anda iptal edebilir; bir sonraki çekim iptal edilir.")
    st.markdown("---")
    st.markdown("## İpuçları (Operasyon)")
    st.write("- Gönderimler: Abonelikte kargo etiketi abonelik id ile eşlenmeli.")
    st.write("- İade/iptal: İlk 14 gün içinde koşullara göre iade/iptal politikası uygulanır (ürüne göre farklılık gösterebilir).")
    st.write("- Faturalama: Aylık fatura otomatik üretilmeli; marka komisyonu reconciliation için CSV.")
    st.markdown("</div>", unsafe_allow_html=True)

# -----------------------
# ABONELIK DETAYLARI (derinlemesine)
# -----------------------
st.markdown("<div style='height:30px'></div>", unsafe_allow_html=True)
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.header("Abonelik Süreci — Detaylı Teknik ve Operasyonel Açıklama")
st.markdown("""
Aşağıda abonelik akışını, ödeme olaylarını, yönetim ve operasyon gereksinimlerini, iptal/dunning/faturalama mantığını ve marka-işletme (NATUVISIO <> marka partner) arasındaki finansal mutabakatı ayrıntılı olarak açıkladım.

---

### 1) Abonelik Oluşumu (Müşteri tarafı)
1. Müşteri formu doldurur: e-posta, isim, telefon, adres, ürün seçimi, frekans ve onay.
2. Sunucu tarafı bir kayıt (subscription record) oluşturur — `status: created`.
3. Eğer Iyzico gibi bir ödeme altyapısı kullanılıyorsa:
   - Backend `pricingPlanReferenceCode` (Iyzico plan reference) ile checkout formu başlatır.
   - Iyzico sandbox / production, bir *checkout token* veya *checkout form HTML* döner.
   - Token iframe içinde gösterilir; müşteri kart bilgilerini girer ve ilk ödeme işlenir.
4. Iyzico success callback (webhook) gönderir — backend doğrular ve `status: active` veya `status: failed` olarak günceller.

---

### 2) Abonelik Döngüsü
- Frekans: 30/60/90 gün gibi periyotlarla planlanır. Her periyot için Iyzico recurring charge otomatik olur.
- Gönderim: Ödeme onayı alındıktan sonra lojistik sistemine (pick&pack) sipariş oluşturulur ve kargo takip bilgisi üretilir.
- Faturalama: Her çekimde fatura oluşturulmalı veya muhasebe için detaylar kaydedilmelidir (mükellefiyete göre KDV vb.).

---

### 3) İptal & Değişiklikler
- Müşteri panelinden iptal: iptal talebi alındığında bir sonraki scheduled charge iptal edilir; mevcut çekim dönemi için ürün gönderimi genelde gerçekleşir.
- Erken iptal ve iade: işletme politikası ile uyumlu şekilde 14 gün içinde iade prosedürü uygulanabilir.
- Plan değişikliği: değiştirilen plan için pro-rata (kısmi ödeme) veya yeni plan uygulanır — tercih size bağlı.

---

### 4) Ödeme Hataları, Dunning (Tahsilat Yaklaşımı)
- Başarısız ödeme: ilk başarısızlıkta e-posta/SMS bilgilendirme, 2. başarısızlıkta 48 saat sonra tekrar deneme, 3. deneme sonrası abonelik askıya alınır.
- Askıya alma: askıya alınan abonelikte müşteriye uyarı, 7 gün sonra ödeme alınamazsa iptal prosedürü uygulanır.
- Ödeme retry politikası ve e-posta şablonları önceden hazırlanmalı.

---

### 5) Marka Komisyon & Reconciliation
- Sipariş başına komisyon oranı (ör: %15) ile marka payı hesaplanır.
- Her ay marka bazlı `payout` raporu oluşturulur: tamamlanan gönderimler -> toplam satış -> komisyon -> marka net ödemesi.
- Marka ödemesi banka transferi ile manuel veya otomatik olarak yapılır; ödeme kaydı sistemde tutulur (payment proof, fatura tarihi).

---

### 6) Güvenlik & Webhook Doğrulama
- Webhook endpoint'leri doğrulanmalı (signed payload veya secret token).
- Callback'leri sadece Iyzico IP bloklarından veya HMAC signature ile kabul edin.
- Özel anahtarlar (IYZICO_API_KEY, IYZICO_SECRET_KEY) kesinlikle sunucu ortam değişkenlerinde saklanmalı, kod deposuna konmamalı.

---

### 7) Operasyonel Notlar (Lojistik)
- Abonelik ID'si -> picklist oluşturma -> paketleme -> kargo takip numarası -> abonelik kaydına eklenmeli.
- Gönderim gecikmesi durumunda müşteri bilgilendirilmeli; otomatik çekim zamanı buna göre yönetilmeli.
- Abonelik durumu (active, suspended, cancelled, pending payment, completed) dashboard'da görünmelidir.

---

### 8) Raporlama
- Günlük/haftalık: yeni abonelikler, başarısız ödemeler, iptaller, net gelir.
- Aylık: marka hakedişleri, pazarlama maliyetleri, churn rate (aylık iptal oranı).

---

### 9) Geliştirme & Production checklist
1. Sandbox testler (Iyzico sandbox).
2. Webhook doğrulama & logging.
3. SSL + güvenli ortam.
4. Yedekleme & DB migration stratejisi.
5. Test senaryoları: iptal, kart güncelleme, başarısız ödemeler, pro-rata plan değişikliği.

---

Bu abonelik akışı NATUVISIO için kapsayıcı bir altyapı sağlar; ödeme sağlayıcınız (iyzico) özelliklerine göre küçük ayarlamalar gerekebilir (ör: plan referans kodları, checkout form türleri).
""")
st.markdown("</div>", unsafe_allow_html=True)

# -----------------------
# SON: küçük admin / debug panel (sadece lokal kullanım)
# -----------------------
st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
if st.checkbox("🔒 Debug: Son 20 kayıtları göster"):
    cur = conn.cursor()
    cur.execute("SELECT id, created_at, email, name, sku, frequency, status FROM subscriptions ORDER BY created_at DESC LIMIT 20")
    rows = cur.fetchall()
    st.table(rows)
