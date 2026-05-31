# notifier.py
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def send_email(subject: str, body: str):
    from_email = os.getenv("EMAIL_FROM")
    password = os.getenv("EMAIL_PASSWORD")
    to_email = os.getenv("EMAIL_TO")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))

    if not all([from_email, password, to_email, smtp_server]):
        print("Email не настроен. Проверьте .env")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(from_email, password)
            server.send_message(msg)
        print(f"Email отправлен на {to_email}")
    except Exception as e:
        print(f"Ошибка отправки email: {e}")
