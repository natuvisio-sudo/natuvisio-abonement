import streamlit as st
import requests
import json

# ----------------------
# IYZICO SETTINGS
# ----------------------
API_KEY = "YOUR_IYZICO_API_KEY"
SECRET_KEY = "YOUR_IYZICO_SECRET_KEY"
BASE_URL = "https://sandbox-api.iyzipay.com"   # Change to PRODUCTION later

PLAN_REFERENCE = "YOUR_SUBSCRIPTION_PLAN_REFERENCE"

CALLBACK_URL = "https://your-domain.com/iyzico-callback"  # You must host this
# ----------------------

st.set_page_config(page_title="NATUVISIO Subscription", layout="centered")

st.title("REALVISIO – Brand Subscription")
st.write("Join NATUVISIO’s verified brand ecosystem. Your subscription renews monthly.")

st.divider()

if st.button("Start Subscription (5.000 TL/month)"):
    
    # ----------------------
    # CREATE SUBSCRIPTION CHECKOUT TOKEN
    # ----------------------
    url = f"{BASE_URL}/v2/subscription/checkout-form/initialize"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "locale": "tr",
        "conversationId": "123456789",
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
        data = response.json()
        token = data["token"]

        checkout_url = f"https://sandbox-checkout.iyzipay.com/checkoutform/initialize/{token}"

        st.success("Subscription checkout generated successfully.")

        st.markdown(
            f"""
            <iframe src="{checkout_url}" width="100%" height="850px" frameborder="0"></iframe>
            """,
            unsafe_allow_html=True
        )
    else:
        st.error("Could not create payment session. Check your API credentials.")
