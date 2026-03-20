from app import db
from datetime import datetime

class Proposal(db.Model):
    __tablename__ = 'proposals'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'))
    car_id = db.Column(db.Integer, db.ForeignKey('cars.id', ondelete='CASCADE'))
    shipping_cost = db.Column(db.Numeric(12, 2))
    customs_fee = db.Column(db.Numeric(12, 2))
    total_price_byn = db.Column(db.Numeric(12, 2))
    total_price_usd = db.Column(db.Numeric(12, 2))
    status = db.Column(db.String(20), default='draft')
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)

    client = db.relationship('Client', backref=db.backref('proposals', lazy=True))
    car = db.relationship('Car', backref=db.backref('proposals', lazy=True))