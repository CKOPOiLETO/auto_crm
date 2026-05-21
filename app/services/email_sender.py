# app/services/email_sender.py
import smtplib
from email.message import EmailMessage
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# НАСТРОЙКИ ВАШЕЙ ТЕСТОВОЙ ПОЧТЫ (Лучше вынести в .env, но пока можно тут)
SMTP_SERVER = "smtp.gmail.com" # Или smtp.yandex.ru
SMTP_PORT = 465
SENDER_EMAIL = "ckopoiieto@gmail.com"
# Сюда нужно вставить "Пароль приложения" (App Password) от Gmail, а не обычный пароль!
SENDER_PASSWORD = "npsg vwjo lvwm qukk" 

def send_proposal_email(to_email: str, client_name: str, pdf_bytes: bytes, filename: str):
    """Отправляет письмо с прикрепленным PDF клиенту"""
    if not to_email:
        raise ValueError("У клиента не указан E-mail адрес.")

    msg = MIMEMultipart()
    msg['Subject'] = 'Ваше коммерческое предложение | AutoCapital'
    msg['From'] = f"AutoCapital <{SENDER_EMAIL}>"
    msg['To'] = to_email

    # Текст письма
    text = f"""
    Здравствуйте, {client_name}!
    
    Благодарим вас за обращение в нашу компанию.
    Во вложении вы найдете подробный расчет стоимости автомобиля "под ключ".
    
    С уважением,
    Ваш менеджер.
    """
    msg.attach(MIMEText(text, 'plain'))

    # Прикрепляем PDF
    part = MIMEApplication(pdf_bytes, Name=filename)
    part['Content-Disposition'] = f'attachment; filename="{filename}"'
    msg.attach(part)

    # Отправка
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)