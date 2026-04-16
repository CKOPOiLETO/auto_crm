# app/models/tariff.py
from app import db
from datetime import datetime

class Tariff(db.Model):
    __tablename__ = 'tariffs'
    id = db.Column(db.Integer, primary_key=True)
    usd_rate = db.Column(db.Numeric(10, 4), nullable=False)
    eur_rate = db.Column(db.Numeric(10, 4), nullable=False)
    shipping_usa = db.Column(db.Numeric(10, 2), nullable=False)
    shipping_sea = db.Column(db.Numeric(10, 2), nullable=False)
    shipping_eu = db.Column(db.Numeric(10, 2), nullable=False, default=500.00) # <--- НОВОЕ ПОЛЕ
    auction_fee_rate = db.Column(db.Numeric(5, 2), nullable=False)
    updated_at = db.Column(db.TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)