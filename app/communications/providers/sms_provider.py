# app/communications/providers/sms_provider.py
from curl_cffi import requests
from flask import current_app

def send_sms(to: str, message: str) -> None:
    response = requests.post(
        "https://api.sandbox.africastalking.com/version1/messaging",
        headers={
            "apiKey": current_app.config["AT_API_KEY"],
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        data={
            "username": current_app.config["AT_USERNAME"],
            "to": to,
            "message": message,
        },
        impersonate="chrome",
    )
    data = response.json()
    recipients = data.get("SMSMessageData", {}).get("Recipients", [])
    if not recipients or recipients[0].get("status") != "Success":
        raise RuntimeError(f"Africa's Talking SMS failed: {data}")