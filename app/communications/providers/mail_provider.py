from flask_mail import Message
from app.extensions import mail

def send_email(to:str, subject:str, body:str) -> None:
    msg = Message(subject, recipients=[to], body=body)
    mail.send(msg)