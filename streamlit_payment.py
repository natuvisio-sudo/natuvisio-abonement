import streamlit as st
import requests
import json

# -----------------------------------------
# PAGE CONFIG
# -----------------------------------------
st.set_page_config(page_title="NATUVISIO Subscription", layout="wide")

# -----------------------------------------
# BACKGROUND IMAGE (Elite Apple-Style UI)
# -----------------------------------------
bg_image_url = "https://res.cloudinary.com/deb1j92hy/image/upload/v1764848571/man-standing-brown-mountain-range_elqddb.webp"

page_bg = f"""
<style>
[data-testid="stAppViewContainer"] {{
    background-image: url("{bg_image_url}");
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
}}

[data-testid="stAppViewContainer"]::before {{
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    backdrop-filter: blur(12px) brightness(0.85);
    z-index: 0;
}}

.main-container {{
    position: relative;
    z-index: 2;
}}

.glass-card {{
    backdrop-filter: blur(18px) saturate(160%);
    -webkit-backdrop-filter: blur(18px) saturate(160%);
    background: rgba(255, 255, 255, 0.12);
    border-radius: 24px;
    border: 1px solid rgba(255,255,255,0.25);
    padding: 48px;
    max-width: 720px;
    margin: auto;
    margin-top: 5vh;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}}

.title-text {{
    color: white;
    font-size: 38px;
    font-weight: 600;
    text-align: center;
    letter-spacing: -0.5px;
}}

.subtitle-text {{
    color: rgba(255,255,255,0.85);
    text-align: center;
    font-size: 18px;
    margin-top: 12px;
    margin-bottom: 32px;
    line-height: 1.6;
}}

.payment-section {{
    margin-top: 32px;
}}

.iframe-container {{
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.2);
    background: rgba(255,255,255,0.05);
}}
</style>
"""

st.markdown(page_bg, unsafe_allow_html=True)

# -----------------------------------------
# UI STRUCTURE
# -----------------------------------------

with st.container():
    st.markdown('<div class="main-container">', unsafe_allow_html=True)

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)

    st.markdown('<div class="title-text">REALVISIO Brand Membership</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="subtitle-text">'
        'Unlock premium visibility, trust verification, analytics, and monthly growth tools.<br>'
        'This subscription renews automatically.'
        '</div>',
        unsafe_allow_html=True
    )

    # ---------------------------
    # PAY BUTTON
    # ---------------------------
    st.write("")

    start_payment = st.button("Subscribe – 5.000 TL / month")

    if start_payment:
        
        # ---------------------------
        # CREATE CHECKOUT TOKEN
        # ---------------------------
        API_KEY = "YOUR_IYZICO_API_KEY"
        SECRET_KEY = "YOUR_IYZICO_SECRET_KEY"
        BASE_URL = "https://sandbox-api.iyzipay.com"
        PLAN_REFERENCE = "YOUR_PLAN_REFERENCE"
        CALLBACK_URL = "https://your-domain.com/iyzico-callback"

        url = f"{BASE_URL}/v2/subscription/checkout-form/initialize"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "locale": "tr",
            "conversationId": "demo",
            "pricingPlanReferenceCode": PLAN_REFERENCE,
            "callbackUrl": CALLBACK_URL,
            "customer": {
                "email": "brand@example.com",
                "name": "Brand",
                "surname": "Owner",
                "gsmNumber": "+905555555555"
            }
        }

        response = requests.post(url, headers=headers, auth=(API_KEY, SECRET_KEY), data=json.dumps(payload))

        if response.status_code == 200:
            token = response.json().get("token")

            iframe_url = f"https://sandbox-checkout.iyzipay.com/checkoutform/initialize/{token}"

            st.markdown('<div class="payment-section">', unsafe_allow_html=True)

            st.markdown(
                f"""
                <div class="iframe-container">
                <iframe src="{iframe_url}" 
                        width="100%" 
                        height="820px" 
                        frameborder="0"
                        scrolling="no">
                </iframe>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.markdown('</div>', unsafe_allow_html=True)

        else:
            st.error("Could not create subscription checkout. Verify API keys.")

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
