# app/routes/manager.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from app import db
from app.models.client import Client
from app.models.proposal import Proposal
from flask import Response # <-- Добавить
import pdfkit # Вместо weasyprint
from app.services.calculator import AutoCalculator # <-- Добавить
from flask_login import login_required
from flask_login import login_required, current_user
from sqlalchemy import or_
from datetime import datetime
from app.models.tariff import Tariff

from app.models.car import Car


# Создаем Blueprint для менеджера с префиксом /manager
manager_bp = Blueprint('manager', __name__, url_prefix='/manager', template_folder='../templates/manager')

# # 1. Список всех клиентов (Read)
# @manager_bp.route('/clients')
# @login_required
# def list_clients():
#     clients = Client.query.order_by(Client.created_at.desc()).all()
#     return render_template('clients.html', clients=clients)

# from flask_login import login_required, current_user

# app/routes/manager.py

@manager_bp.route('/clients')
@login_required
def list_clients():
    q = request.args.get('q', '') # Получаем запрос
    
    # Базовый запрос
    query = Client.query
    
    # Ограничение по ролям: менеджер видит только своих
    if current_user.role != 'admin':
        query = query.filter(Client.manager_id == current_user.id)
    
    # Если есть поиск
    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            Client.fio.ilike(term),
            Client.phone.ilike(term),
            Client.messenger.ilike(term)
        ))
        
    clients = query.order_by(Client.created_at.desc()).all()
    return render_template('clients.html', clients=clients, q=q)

# При добавлении клиента - привязываем его к текущему менеджеру
@manager_bp.route('/clients/add', methods=['GET', 'POST'])
@login_required
def add_client():
    if request.method == 'POST':
        new_client = Client(
            fio=request.form.get('fio'),
            phone=request.form.get('phone'),
            manager_id=current_user.id # <--- ПРИВЯЗКА К МЕНЕДЖЕРУ
        )
        db.session.add(new_client)
        db.session.commit()
        return redirect(url_for('manager.list_clients'))
    return render_template('client_form.html')

# 3. Редактирование клиента (Update)
@manager_bp.route('/clients/edit/<int:client_id>', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    client = Client.query.get_or_404(client_id) # Найти клиента или выдать ошибку 404

    if request.method == 'POST':
        client.fio = request.form.get('fio')
        client.phone = request.form.get('phone')
        client.messenger = request.form.get('messenger')
        client.status = request.form.get('status')
        db.session.commit()
        flash('Данные клиента обновлены!', 'info')
        return redirect(url_for('manager.list_clients'))

    return render_template('client_form.html', title="Редактировать клиента", client=client)

# 4. Удаление клиента (Delete)
@manager_bp.route('/clients/delete/<int:client_id>', methods=['POST'])
@login_required
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    db.session.delete(client)
    db.session.commit()
    flash('Клиент удален из базы.', 'warning')
    return redirect(url_for('manager.list_clients'))



@manager_bp.route('/proposals')
@login_required
def list_proposals():
    # 1. Получаем параметры из URL (q - поисковый запрос, sort_by - поле сортировки)
    q = request.args.get('q', '')
    sort_by = request.args.get('sort_by', 'date')
    order = request.args.get('order', 'desc')

    # 2. Начинаем строить базовый запрос
    query = Proposal.query.join(Client).join(Car)

    # 3. Применяем фильтр для менеджера (видит только свои) или админа (видит все)
    if current_user.role != 'admin':
        query = query.filter(Client.manager_id == current_user.id)
    
    # 4. Если есть поисковый запрос, добавляем фильтр
    if q:
        search_term = f"%{q}%"
        query = query.filter(or_(
            Client.fio.ilike(search_term),
            Car.title.ilike(search_term)
        ))
    
    # 5. Применяем сортировку
    # Безопасная карта, чтобы пользователь не мог сортировать по любым полям
    sort_map = {
        'date': Proposal.created_at,
        'client': Client.fio,
        'car': Car.title,
        'price': Proposal.total_price_usd,
        'status': Proposal.status,
    }
    sort_column = sort_map.get(sort_by, Proposal.created_at)

    if order == 'desc':
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # 6. Выполняем итоговый запрос
    proposals = query.all()
    
    # Передаем параметры поиска и сортировки обратно в шаблон, чтобы он "помнил" выбор
    return render_template('proposals.html', 
                           proposals=proposals, 
                           q=q, 
                           sort_by=sort_by, 
                           order=order)




# app/routes/manager.py

# --- НОВЫЙ РОУТ-ГЕНЕРАТОР PDF ---
@manager_bp.route('/proposals/pdf/<int:proposal_id>')
@login_required
def generate_proposal_pdf(proposal_id):
    # 1. Находим предложение
    proposal = Proposal.query.options(
        db.joinedload(Proposal.client),
        db.joinedload(Proposal.car)
    ).get_or_404(proposal_id)
    
    # 2. Пересчитываем стоимость
    calculator = AutoCalculator()
    calc_result = calculator.calculate_all(
        price_usd=float(proposal.car.price_usd),
        engine_volume=proposal.car.engine_volume,
        year=proposal.car.manufacture_year
    )

    # 3. Генерируем HTML из шаблона
    rendered_html = render_template('proposal_pdf.html', proposal=proposal, calc=calc_result)
    
    # 4. Настройка пути к wkhtmltopdf
    path_wkhtmltopdf = r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    
    # 5. Опции PDF (настройка внешнего вида)
    options = {
        'page-size': 'A4',
        'margin-top': '0.75in',
        'margin-right': '0.75in',
        'margin-bottom': '0.75in',
        'margin-left': '0.75in',
        'encoding': "UTF-8",
        'no-outline': None
    }
    
    # 6. Генерируем PDF
    pdf_bytes = pdfkit.from_string(rendered_html, False, configuration=config, options=options)
    
    # 7. Отдаем пользователю
    filename = f"Proposal_{proposal.id}.pdf"
    
    # Кодируем имя файла для заголовка Content-Disposition
    from urllib.parse import quote
    encoded_filename = quote(filename)
    
    response = Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    )
    return response





# --- ИЗМЕНЕНИЕ СТАТУСА ПРЕДЛОЖЕНИЯ ---
@manager_bp.route('/proposals/status/<int:proposal_id>', methods=['POST'])
@login_required
def update_proposal_status(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    
    # Защита: Менеджер может менять только свои предложения
    if current_user.role != 'admin' and proposal.client.manager_id != current_user.id:
        flash('У вас нет прав для изменения этого предложения.', 'danger')
        return redirect(url_for('manager.list_proposals'))
    
    new_status = request.form.get('status')
    if new_status in ['draft', 'sent', 'accepted', 'rejected']:
        proposal.status = new_status
        db.session.commit()
        flash('Статус предложения успешно обновлен.', 'success')
        
    return redirect(url_for('manager.list_proposals'))

# --- УДАЛЕНИЕ ПРЕДЛОЖЕНИЯ ---
@manager_bp.route('/proposals/delete/<int:proposal_id>', methods=['POST'])
@login_required
def delete_proposal(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    
    # Защита: Менеджер может удалять только свои предложения
    if current_user.role != 'admin' and proposal.client.manager_id != current_user.id:
        flash('У вас нет прав для удаления этого предложения.', 'danger')
        return redirect(url_for('manager.list_proposals'))
    
    db.session.delete(proposal)
    db.session.commit()
    flash('Коммерческое предложение удалено.', 'warning')
    
    return redirect(url_for('manager.list_proposals'))



# app/routes/manager.py

@manager_bp.route('/clients/status/<int:client_id>', methods=['POST'])
@login_required
def update_client_status(client_id):
    client = Client.query.get_or_404(client_id)
    
    # Защита: Менеджер может менять статус только своих клиентов
    if current_user.role != 'admin' and client.manager_id != current_user.id:
        flash('У вас нет прав для изменения этого клиента.', 'danger')
        return redirect(url_for('manager.list_clients'))
    
    new_status = request.form.get('status')
    # Список допустимых статусов (согласно вашему выбору в форме или ТЗ)
    valid_statuses = ['new', 'in_progress', 'done', 'rejected']
    
    if new_status in valid_statuses:
        client.status = new_status
        db.session.commit()
        flash(f'Статус клиента {client.fio} обновлен.', 'success')
    
    return redirect(url_for('manager.list_clients'))






@manager_bp.route('/car/<int:car_id>')
@login_required
def view_car(car_id):
    car = Car.query.get_or_404(car_id)
    return render_template('manager/car_details.html', car=car)



# --- ДАШБОРД (ГЛАВНАЯ СТРАНИЦА) ---
@manager_bp.route('/dashboard')
@login_required
def dashboard():
    # 1. Получаем актуальные тарифы
    tariff = Tariff.query.first()
    
    # 2. Подготавливаем базовые запросы
    client_query = Client.query
    proposal_query = Proposal.query.join(Client)
    
    # 3. Разграничение прав: менеджер видит только свои цифры
    if current_user.role != 'admin':
        client_query = client_query.filter_by(manager_id=current_user.id)
        proposal_query = proposal_query.filter(Client.manager_id == current_user.id)
        
    # 4. Считаем статистику
    clients_count = client_query.count()
    proposals_count = proposal_query.count()
    
    # 5. Получаем последние 5 расчетов для таблицы
    recent_proposals = proposal_query.order_by(Proposal.created_at.desc()).limit(5).all()
    
    return render_template(
        'manager/dashboard.html', 
        tariff=tariff,
        clients_count=clients_count,
        proposals_count=proposals_count,
        recent_proposals=recent_proposals
    )