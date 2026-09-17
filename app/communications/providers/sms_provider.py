from twilio.rest import Client
from flask import current_app

def send_sms(to:str, message:str) -> None:
    client = Client(
        current_app.config["TWILIO_ACCOUNT_SID"],
        current_app.config["TWILIO_AUTH_TOKEN"]
    )
    client.messages.create(
        to=to,
        from_=current_app.config["TWILIO_PHONE_NUMBER"],
        body=message
    )