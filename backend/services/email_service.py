import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from core.config import settings

def send_email(subject: str, body: str, to_email: str) -> None:
    """Send an email using the SMTP credentials from settings."""
    msg = MIMEMultipart()
    msg["From"] = settings.smtp.from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        if settings.smtp.use_ssl:
            server = smtplib.SMTP_SSL(settings.smtp.host, settings.smtp.port)
        else:
            server = smtplib.SMTP(settings.smtp.host, settings.smtp.port)
            if settings.smtp.use_tls:
                server.starttls()
        
        server.login(settings.smtp.user, settings.smtp.password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Error sending email: {e}")
        raise e
