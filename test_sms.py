# test_sms.py — throwaway script, delete once it works
from curl_cffi import requests

response = requests.post(
    "https://api.sandbox.africastalking.com/version1/messaging",
    headers={
        "apiKey": "atsk_881cb58e4a4d9140afbbedcb08bc6020ba7bfa3b85d4ddf83e41f501d357a66ebd35abd4",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    },
    data={
        "username": "sandbox",
        "to": "+254114555298",
        "message": "Test message from Routify",
    },
    impersonate="chrome",
)
print(response.status_code)
print(response.json())