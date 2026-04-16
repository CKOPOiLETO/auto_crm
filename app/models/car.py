# app/models/car.py
from app import db
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY # Импортируем спец. типы PG

class Car(db.Model):
    __tablename__ = 'cars'
    id = db.Column(db.Integer, primary_key=True)
    vin = db.Column(db.String(17), unique=True)
    title = db.Column(db.String(255), nullable=False)
    auction_link = db.Column(db.Text)
    price_usd = db.Column(db.Numeric(12, 2), nullable=False)
    damage_type = db.Column(db.String(100))
    photo_url = db.Column(db.Text) # Главное фото
    engine_volume = db.Column(db.Integer)
    manufacture_year = db.Column(db.Integer)
    fuel_type = db.Column(db.String(20))
    
    # НОВЫЕ ПОЛЯ
    additional_params = db.Column(JSONB) # Храним словарь параметров
    gallery_urls = db.Column(db.ARRAY(db.Text)) # Храним список ссылок на фото
    
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)