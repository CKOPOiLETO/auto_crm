# app/__init__.py
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from .config import Config

# Инициализируем расширения
db = SQLAlchemy()
login_manager = LoginManager()

def create_app(config_class=Config):
    """Фабрика для создания экземпляра приложения Flask."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Привязываем расширения к приложению
    db.init_app(app)
    login_manager.init_app(app)
    
    # Указываем, куда перенаправлять неавторизованных
    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Пожалуйста, войдите в систему для доступа к этой странице."
    login_manager.login_message_category = "warning"


    @login_manager.user_loader
    def load_user(user_id):
        from .models.user import User
        return User.query.get(int(user_id))

    # 3. Импортируем и регистрируем Блупринты
    from .routes.auth import auth_bp
    from .routes.parser import parser_bp
    from .routes.admin import admin_bp
    from .routes.manager import manager_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(parser_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(manager_bp)


    @app.route('/')
    def home():
        # Сразу перекидываем на парсер (если не залогинен - кинет на логин)
        return redirect(url_for('parser.index'))

    return app

# Импортируем модели в конце, чтобы SQLAlchemy их увидел
from . import models