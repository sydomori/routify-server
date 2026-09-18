import africastalking
from flask import current_app

_initialized = False

def _ensure_initialized():
    global _initialized
    if not _initialized:
        africastalking.initialize(
            current_app.config["AT_USERNAME"],
            current_app.config["AT_API_KEY"],
        )
        _initialized = True

def send_sms(to: str, message: str) -> None:
    _ensure_initialized()
    sms = africastalking.SMS
    response = sms.send(message, [to])

    recipients = response.get("SMSMessageData", {}).get("Recipients", [])
    if not recipients or recipients[0].get("status") != "Success":
        # Africa's Talking returns 200 with a per-recipient status field even
        # on failure — it doesn't raise on its own, so we raise here to keep
        # the same contract service.py already expects (an exception on failure).
        raise RuntimeError(f"Africa's Talking SMS failed: {response}")