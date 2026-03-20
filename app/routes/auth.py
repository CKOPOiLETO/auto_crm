# app/routes/auth.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_user
from werkzeug.security import check_password_hash
import bcrypt # <--- Добавляем этот импорт
from app.models.user import User
from flask_login import login_user, logout_user 

auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form.get('login')
        password_input = request.form.get('password')
        
        user = User.query.filter_by(login=login_input).first()
        
        if user:
            # Если хэш старого формата (bcrypt)
            if user.password_hash.startswith('$2b$'):
                # Проверяем пароль через bcrypt
                if bcrypt.checkpw(password_input.encode('utf-8'), user.password_hash.encode('utf-8')):
                    login_user(user)
                    return redirect(url_for('parser.index'))
            
            # Если хэш нового формата (werkzeug/pbkdf2)
            elif check_password_hash(user.password_hash, password_input):
                login_user(user)
                return redirect(url_for('parser.index'))
                
        flash('Неверный логин или пароль', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))