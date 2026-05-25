from app import db
from datetime import datetime
from .user import User 


class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    fio = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    messenger = db.Column(db.String(50))
    email = db.Column(db.String(150))
    messenger_type = db.Column(db.String(20), default='telegram')
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    
    manager = db.relationship('User', backref=db.backref('clients', lazy=True))