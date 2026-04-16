# app/routes/admin.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from app import db
from app.models.tariff import Tariff
from flask_login import login_required, current_user
from functools import wraps
from flask import abort
from app.models.user import User
from werkzeug.security import generate_password_hash
from sqlalchemy import or_
from sqlalchemy import func, desc # Для подсчета, суммирования и сортировки
from app.models.proposal import Proposal
from app.models.car import Car
from sqlalchemy import func, desc, case
from app.models.client import Client
from app.models.proposal import Proposal
from app.models.car import Car

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# Обязательно импортируем нашу функцию парсера валют
from app.services.currency_updater import get_nbrb_rates

admin_bp = Blueprint('admin', __name__, url_prefix='/admin', template_folder='../templates/admin')
@admin_bp.route('/tariffs', methods=['GET', 'POST'])
@login_required
@admin_required
def tariffs():
    tariff = Tariff.query.first()
    
    if not tariff:
        # Стартовые значения
        tariff = Tariff(
            usd_rate=3.2500, 
            eur_rate=3.5500, 
            shipping_usa=600.00, 
            shipping_sea=1400.00,
            shipping_eu=500.00, 
            auction_fee_rate=5.00
        )
        db.session.add(tariff)
        db.session.commit()

    # Кусок файла app/routes/admin.py
    if request.method == 'POST':
        try:
            tariff.usd_rate = request.form.get('usd_rate')
            tariff.eur_rate = request.form.get('eur_rate')
            tariff.shipping_usa = request.form.get('shipping_usa')
            tariff.shipping_sea = request.form.get('shipping_sea')
            tariff.shipping_eu = request.form.get('shipping_eu')
            tariff.auction_fee_rate = request.form.get('auction_fee_rate')
            
            db.session.commit()
            flash('Тарифы успешно обновлены!', 'success')
            return redirect(url_for('admin.tariffs'))
        except Exception as e:
            # --- ИСПРАВЛЕНИЕ: ОТМЕНЯЕМ ОШИБОЧНУЮ ТРАНЗАКЦИЮ ---
            db.session.rollback() 
            flash(f'Ошибка при сохранении: {str(e)}', 'danger')

    return render_template('tariffs.html', tariff=tariff)

@admin_bp.route('/tariffs/update-nbrb', methods=['POST'])
@login_required
@admin_required
def update_nbrb():
    try:
        tariff = Tariff.query.first()
        if not tariff:
            flash('Сначала сохраните базовые тарифы!', 'warning')
            return redirect(url_for('admin.tariffs'))
            
        rates = get_nbrb_rates()
        
        if rates:
            tariff.usd_rate = rates['usd']
            tariff.eur_rate = rates['eur']
            db.session.commit()
            
            if rates['date'] != 'Error':
                flash(f"Курсы на {rates['date']} успешно загружены! USD: {rates['usd']}, EUR: {rates['eur']}", 'success')
            else:
                flash(f"Сайт НБРБ недоступен. Установлены резервные курсы: USD {rates['usd']}, EUR {rates['eur']}", 'warning')
        else:
            flash('Не удалось получить данные. Проверьте консоль.', 'danger')
            
    except Exception as e:
        # Если произойдет сбой в БД или коде, мы не получим 500 ошибку, а увидим красную плашку
        flash(f'Внутренняя ошибка сервера: {str(e)}', 'danger')

    return redirect(url_for('admin.tariffs'))


# --- УПРАВЛЕНИЕ СОТРУДНИКАМИ ---

@admin_bp.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_users():
    if request.method == 'POST':
        new_user = User(
            login=request.form.get('login'),
            password_hash=generate_password_hash(request.form.get('password')),
            full_name=request.form.get('full_name'),
            role=request.form.get('role')
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Сотрудник добавлен!', 'success')
        return redirect(url_for('admin.manage_users'))
    # Логика поиска (GET)
    q = request.args.get('q', '')
    query = User.query
    
    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            User.login.ilike(term),
            User.full_name.ilike(term)
        ))
    
    users = query.order_by(User.full_name).all()
    return render_template('admin/users.html', users=users, q=q)
    
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.login = request.form.get('login')
        user.full_name = request.form.get('full_name')
        user.role = request.form.get('role')
        
        # Если админ ввел новый пароль, обновляем хэш
        new_password = request.form.get('password')
        if new_password:
            user.password_hash = generate_password_hash(new_password)
            
        db.session.commit()
        flash('Данные сотрудника успешно обновлены!', 'info')
        return redirect(url_for('admin.manage_users'))
        
    return render_template('admin/user_edit.html', user=user)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    # Защита от самоудаления
    if current_user.id == user_id:
        flash('Вы не можете удалить свою собственную учетную запись!', 'danger')
        return redirect(url_for('admin.manage_users'))
        
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f'Сотрудник {user.login} удален из системы.', 'warning')
    return redirect(url_for('admin.manage_users'))



@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    # 1. Заявки в разрезе статуса (для круговой диаграммы)
    status_counts = db.session.query(Proposal.status, func.count(Proposal.id)).group_by(Proposal.status).all()
    status_labels = [s[0] for s in status_counts]
    status_data = [s[1] for s in status_counts]

    # 2. Конверсия (Отправленные vs Успешные)
    # Считаем все, что ушло клиенту (отправлено, принято, отказ)
    sent_proposals = Proposal.query.filter(Proposal.status.in_(['sent', 'accepted', 'rejected'])).count()
    accepted_proposals = Proposal.query.filter_by(status='accepted').count()
    
    conversion_rate = round((accepted_proposals / sent_proposals * 100), 2) if sent_proposals > 0 else 0

    # 3. Эффективность менеджеров (Кол-во предложений и успешных сделок)
    manager_stats = db.session.query(
        User.full_name,
        func.count(Proposal.id).label('total_proposals'),
        func.sum(case((Proposal.status == 'accepted', 1), else_=0)).label('accepted_proposals')
    ).join(Client, Client.manager_id == User.id)\
     .join(Proposal, Proposal.client_id == Client.id)\
     .group_by(User.id).all()

    # 4. Общая выручка (как было)
    total_revenue = db.session.query(func.sum(Proposal.total_price_usd)).filter_by(status='accepted').scalar() or 0

    return render_template('admin/analytics.html', 
                           conversion_rate=conversion_rate,
                           total_revenue=total_revenue,
                           sent_proposals=sent_proposals,
                           accepted_proposals=accepted_proposals,
                           status_labels=status_labels,
                           status_data=status_data,
                           manager_stats=manager_stats)