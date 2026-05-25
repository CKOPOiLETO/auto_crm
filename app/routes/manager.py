# app/routes/manager.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from app import db
from app.models.client import Client
from app.models.proposal import Proposal
from flask import Response 
import pdfkit 
from app.services.calculator import AutoCalculator 
from flask_login import login_required
from flask_login import login_required, current_user
from sqlalchemy import or_
from datetime import datetime
from app.models.tariff import Tariff
import cloudscraper
from app.models.car import Car
import os
import re
import hashlib
from selenium.common.exceptions import WebDriverException, NoSuchWindowException
from app.services.browser import create_driver
from app.services.bidcars_parser import BidCarsParser
from app.routes.parser import _fetch_bidcars_image_bytes
from app.services.email_sender import send_proposal_email
from app.models.user import User 
from decimal import Decimal





# Создаем Blueprint для менеджера с префиксом /manager
manager_bp = Blueprint('manager', __name__, url_prefix='/manager', template_folder='../templates/manager')

def create_pdf_bytes(proposal):
    """Общая функция генерации PDF для скачивания и отправки на почту"""
    calculator = AutoCalculator()
    calc_result = calculator.calculate_all(
        price_usd=float(proposal.car.price_usd),
        engine_volume=proposal.car.engine_volume,
        year=proposal.car.manufacture_year,
        custom_shipping=float(proposal.shipping_cost)
    )

    def _static_url_to_file_url(static_url: str) -> str | None:
        if not static_url or not isinstance(static_url, str): return None
        if not static_url.startswith('/static/'): return None
        rel = static_url[len('/static/'):].lstrip('/\\')
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        static_dir = os.path.join(app_dir, 'static')
        abs_path = os.path.abspath(os.path.join(static_dir, rel))
        if not os.path.exists(abs_path): return None
        return 'file:///' + abs_path.replace('\\', '/')

    def _to_pdf_img_src(u: str) -> str | None:
        if not u: return None
        if isinstance(u, str) and u.startswith('/static/'): return _static_url_to_file_url(u)
        if isinstance(u, str) and (u.startswith('http://') or u.startswith('https://')): return u
        return None

    main_photo_pdf = _to_pdf_img_src(proposal.car.photo_url)
    gallery_pdf = []
    if proposal.car.gallery_urls:
        for u in proposal.car.gallery_urls:
            src = _to_pdf_img_src(u)
            if src: gallery_pdf.append(src)

    # Рендерим HTML с фото
    rendered_html = render_template(
        'manager/proposal_pdf.html', 
        proposal=proposal, 
        calc=calc_result,
        main_photo_pdf=main_photo_pdf,
        gallery_pdf=gallery_pdf
    )
    
    path_wkhtmltopdf = r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    options = {
        'page-size': 'A4', 'margin-top': '0.75in', 'margin-right': '0.75in',
        'margin-bottom': '0.75in', 'margin-left': '0.75in', 'encoding': "UTF-8",
        'no-outline': None, 'enable-local-file-access': None, 'quiet': ''
    }
    
    return pdfkit.from_string(rendered_html, False, configuration=config, options=options)

@manager_bp.route('/clients')
@login_required
def list_clients():
    q = request.args.get('q', '')
    manager_filter = request.args.get('manager_id', '') # Новый параметр фильтра
    
    query = Client.query
    
    # Админу достаем список всех менеджеров для выпадающего списка
    all_managers = []
    
    if current_user.role == 'admin':
        all_managers = User.query.all()
        # Если админ выбрал фильтр по менеджеру:
        if manager_filter:
            query = query.filter(Client.manager_id == int(manager_filter))
    else:
        # Обычный менеджер видит только своих
        query = query.filter(Client.manager_id == current_user.id)
    
    if q:
        term = f"%{q}%"
        from sqlalchemy import or_
        query = query.filter(or_(
            Client.fio.ilike(term),
            Client.phone.ilike(term),
            Client.messenger.ilike(term)
        ))
        
    clients = query.order_by(Client.created_at.desc()).all()
    return render_template('clients.html', clients=clients, q=q, all_managers=all_managers, manager_filter=manager_filter)


@manager_bp.route('/clients/add', methods=['GET', 'POST'])
@login_required
def add_client():
    # Админу передаем список всех сотрудников для возможности выбора
    managers = User.query.order_by(User.full_name).all() if current_user.role == 'admin' else []

    if request.method == 'POST':
        fio = request.form.get('fio')
        phone = request.form.get('phone')
        messenger = request.form.get('messenger')
        messenger_type = request.form.get('messenger_type')
        email = request.form.get('email')
        
        if not re.fullmatch(r'^\+375 \(\d{2}\) \d{3}-\d{2}-\d{2}$', phone):
            flash('Ошибка: Введите корректный белорусский номер!', 'danger')
            return redirect(request.url)

        # Определяем, за кем закрепить клиента
        assigned_manager_id = current_user.id
        if current_user.role == 'admin':
            selected_manager = request.form.get('manager_id')
            if selected_manager:
                assigned_manager_id = int(selected_manager)

        new_client = Client(
            fio=fio,
            phone=phone,
            messenger=messenger,
            manager_id=assigned_manager_id,
            messenger_type=messenger_type,
            email = email
        )
        db.session.add(new_client)
        db.session.commit()
        flash('Новый клиент успешно добавлен!', 'success')
        return redirect(url_for('manager.list_clients'))

    return render_template('manager/client_form.html', title="Добавить нового клиента", managers=managers)


@manager_bp.route('/clients/edit/<int:client_id>', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
    
    if current_user.role != 'admin' and client.manager_id != current_user.id:
        flash('Нет доступа.', 'danger')
        return redirect(url_for('manager.list_clients'))

    # Админу передаем список всех сотрудников для переназначения
    managers = User.query.order_by(User.full_name).all() if current_user.role == 'admin' else []

    if request.method == 'POST':
        phone = request.form.get('phone')
        
        if not re.fullmatch(r'^\+375 \(\d{2}\) \d{3}-\d{2}-\d{2}$', phone):
            flash('Ошибка: Введите корректный белорусский номер!', 'danger')
            return redirect(request.url)

        client.fio = request.form.get('fio')
        client.phone = phone
        client.messenger = request.form.get('messenger')
        client.status = request.form.get('status')
        client.messenger_type = request.form.get('messenger_type')
        client.email = request.form.get('email')
        
        # Если это админ, обновляем менеджера
        if current_user.role == 'admin':
            new_manager_id = request.form.get('manager_id')
            if new_manager_id:
                client.manager_id = int(new_manager_id)

        db.session.commit()
        flash('Данные клиента обновлены!', 'info')
        return redirect(url_for('manager.list_clients'))

    return render_template('manager/client_form.html', title="Редактировать клиента", client=client, managers=managers)
# 4. Удаление клиента (Delete)
@manager_bp.route('/clients/delete/<int:client_id>', methods=['POST'])
@login_required
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    db.session.delete(client)
    db.session.commit()
    flash('Клиент удален из базы.', 'warning')
    return redirect(url_for('manager.list_clients'))


# app/routes/manager.py

@manager_bp.route('/proposals')
@login_required
def list_proposals():
    # 1. Получаем все параметры поиска и фильтрации из URL
    q = request.args.get('q', '')
    sort_by = request.args.get('sort_by', 'date')
    order = request.args.get('order', 'desc')
    
    # НОВЫЕ ФИЛЬТРЫ
    client_id_filter = request.args.get('client_id', '')
    status_filter = request.args.get('status', '')

    query = Proposal.query.join(Client).join(Car)

    # Разграничение прав
    if current_user.role != 'admin':
        query = query.filter(Client.manager_id == current_user.id)
    
    # --- ПРИМЕНЯЕМ ФИЛЬТРЫ К SQL-ЗАПРОСУ ---
    if client_id_filter:
        query = query.filter(Proposal.client_id == int(client_id_filter))
        
    if status_filter:
        query = query.filter(Proposal.status == status_filter)
        
    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            Client.fio.ilike(term),
            Car.title.ilike(term)
        ))
    
    # Сортировка
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

    proposals = query.all()

    # Выгружаем клиентов для модального окна И ДЛЯ ФИЛЬТРА
    if current_user.role == 'admin':
        my_clients = Client.query.order_by(Client.fio).all()
    else:
        my_clients = Client.query.filter_by(manager_id=current_user.id).order_by(Client.fio).all()
    
    # Не забываем передать новые переменные фильтров в HTML
    return render_template('manager/proposals.html', 
                           proposals=proposals, 
                           q=q, 
                           sort_by=sort_by, 
                           order=order, 
                           my_clients=my_clients,
                           client_id_filter=client_id_filter,
                           status_filter=status_filter)

@manager_bp.route('/proposals/clone/<int:proposal_id>', methods=['POST'])
@login_required
def clone_proposal(proposal_id):
    old_proposal = Proposal.query.get_or_404(proposal_id)
    
    # Защита прав
    if current_user.role != 'admin' and old_proposal.client.manager_id != current_user.id:
        flash('У вас нет доступа к этому предложению.', 'danger')
        return redirect(url_for('manager.list_proposals'))
        
    new_client_id = request.form.get('new_client_id')
    if not new_client_id:
        flash('Клиент не выбран!', 'warning')
        return redirect(url_for('manager.list_proposals'))

    try:
        # Создаем точную копию предложения, но для нового клиента
        new_proposal = Proposal(
            client_id=new_client_id,
            car_id=old_proposal.car_id,
            shipping_cost=old_proposal.shipping_cost,
            customs_fee=old_proposal.customs_fee,
            total_price_byn=old_proposal.total_price_byn,
            total_price_usd=old_proposal.total_price_usd,
            status='draft' # Новая копия всегда "Черновик"
        )
        db.session.add(new_proposal)
        db.session.commit()
        flash('Предложение успешно скопировано для нового клиента! Теперь вы можете отправить ему письмо.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при дублировании: {e}', 'danger')

    return redirect(url_for('manager.list_proposals'))
# --- НОВЫЙ РОУТ-ГЕНЕРАТОР PDF ---
@manager_bp.route('/proposals/pdf/<int:proposal_id>')
@login_required
def generate_proposal_pdf(proposal_id):
    proposal = Proposal.query.options(db.joinedload(Proposal.client), db.joinedload(Proposal.car)).get_or_404(proposal_id)
    
    # Используем нашу общую функцию!
    pdf_bytes = create_pdf_bytes(proposal)
    
    from urllib.parse import quote
    filename = f"Proposal_{proposal.id}.pdf"
    
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    )

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
    
    # Ищем коммерческое предложение для этого автомобиля
    proposal = Proposal.query.filter_by(car_id=car.id).first()
    
    calc_result = None
    if car.price_usd is not None:
        calculator = AutoCalculator()
        # Если КП есть, берем логистику оттуда, иначе считаем по умолчанию
        shipping_cost = float(proposal.shipping_cost) if proposal and proposal.shipping_cost else None
        
        calc_result = calculator.calculate_all(
            price_usd=float(car.price_usd),
            engine_volume=car.engine_volume or 0,
            year=car.manufacture_year or datetime.now().year - 4,
            custom_shipping=shipping_cost
        )

    return render_template('manager/car_details.html', car=car, proposal=proposal, calc=calc_result)
def _cache_one_image(url: str, ctx: dict, vin_dir: str) -> str | None:
    if not url:
        return None
    try:
        data, content_type = _fetch_bidcars_image_bytes(url, ctx)
        ext = _ext_from_content_type(content_type)
        digest = hashlib.sha1(url.encode('utf-8', errors='ignore')).hexdigest()[:16]
        rel_dir = os.path.join('car_photos', vin_dir)
        abs_dir = os.path.join(os.path.dirname(__file__), '..', 'static', rel_dir)
        abs_dir = os.path.abspath(abs_dir)
        os.makedirs(abs_dir, exist_ok=True)
        filename = f'{digest}{ext}'
        abs_path = os.path.join(abs_dir, filename)
        with open(abs_path, 'wb') as f:
            f.write(data)
        return '/static/' + '/'.join([rel_dir.replace('\\', '/'), filename]).replace('\\', '/')
    except Exception as e:
        print(f"[!] cache image failed: {e}")
        return None

@manager_bp.route('/car/<int:car_id>/cache_images', methods=['POST'])
@login_required
def cache_car_images(car_id):
    car = Car.query.get_or_404(car_id)
    if not car.auction_link:
        flash('Нет ссылки аукциона — не могу обновить фото.', 'warning')
        return redirect(url_for('manager.view_car', car_id=car_id))

    driver = None
    try:
        driver = create_driver()
        parser = BidCarsParser(driver)
        data = parser.parse_all(car.auction_link)

        photos = (data or {}).get('photos') or []
        if not photos:
            flash('Не удалось найти фото на странице лота.', 'warning')
            return redirect(url_for('manager.view_car', car_id=car_id))

        ua = driver.execute_script("return navigator.userAgent")
        ctx = {
            'cookies': driver.get_cookies(),
            'user_agent': (ua or '').strip(),
            'referer': (car.auction_link or '').strip() or 'https://bid.cars/',
        }

        vin_dir = _safe_vin_dir(car.vin)
        cached_main = _cache_one_image(photos[0], ctx, vin_dir)
        cached_gallery: list[str] = []
        for u in photos:
            cu = _cache_one_image(u, ctx, vin_dir)
            if cu:
                cached_gallery.append(cu)

        if cached_main:
            car.photo_url = cached_main
        if cached_gallery:
            car.gallery_urls = cached_gallery
        db.session.commit()
        flash('Фото обновлены и сохранены локально.', 'success')
    except (NoSuchWindowException, WebDriverException) as e:
        db.session.rollback()
        flash('Браузер Selenium был закрыт или упал. Попробуйте еще раз.', 'danger')
        print(f"[!] Selenium Error: {e}")
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка обновления фото: {e}', 'danger')
        print(f"[!] Cache photos error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return redirect(url_for('manager.view_car', car_id=car_id))



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



@manager_bp.route('/proposals/export_history')
@login_required
def export_history_pdf():
    if current_user.role == 'admin':
        proposals = Proposal.query.order_by(Proposal.created_at.desc()).all()
    else:
        proposals = Proposal.query.join(Client).filter(Client.manager_id == current_user.id).order_by(Proposal.created_at.desc()).all()

    rendered_html = render_template('manager/history_pdf.html', proposals=proposals, user=current_user)
    
    import pdfkit
    path_wkhtmltopdf = r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    
    options = {'page-size': 'A4', 'encoding': "UTF-8", 'orientation': 'Landscape'}
    
    try:
        pdf_bytes = pdfkit.from_string(rendered_html, False, configuration=config, options=options)
        return Response(pdf_bytes, mimetype="application/pdf", headers={"Content-Disposition": "attachment; filename=History_Report.pdf"})
    except Exception as e:
        return f"Ошибка генерации отчета: {e}", 500
    



    # --- РОУТ ОТПРАВКИ ПИСЬМА И ТРИГГЕРОВ ---
@manager_bp.route('/proposals/send_email/<int:proposal_id>', methods=['POST'])
@login_required
def send_proposal_to_client(proposal_id):
    try:
        proposal = Proposal.query.get_or_404(proposal_id)
        
        if not proposal.client.email:
            flash('У этого клиента не заполнен E-mail.', 'danger')
            return redirect(url_for('manager.list_proposals'))

        # Используем ту же самую функцию (теперь фото будут и в письме!)
        pdf_bytes = create_pdf_bytes(proposal)
        filename = f"AutoCapital_Proposal_{proposal.id}.pdf"

        # Отправляем письмо
        from app.services.email_sender import send_proposal_email
        send_proposal_email(proposal.client.email, proposal.client.fio, pdf_bytes, filename)

        # ТРИГГЕРЫ СТАТУСОВ
        proposal.status = 'sent'
        if proposal.client.status == 'new':
            proposal.client.status = 'in_progress'
            
        db.session.commit()
        flash(f'КП успешно отправлено на почту {proposal.client.email}!', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка отправки письма: {e}', 'danger')
        print(f"[-] Email Error: {e}")

    return redirect(url_for('manager.list_proposals'))



@manager_bp.route('/proposals/recalculate/<int:proposal_id>', methods=['POST'])
@login_required
def recalculate_proposal(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    
    if current_user.role != 'admin' and proposal.client.manager_id != current_user.id:
        flash('У вас нет прав для изменения этого предложения.', 'danger')
        return redirect(url_for('manager.list_proposals'))
    
    driver = None
    try:
        car = proposal.car
        
        # 1. ЗАПУСКАЕМ ПАРСЕР, ЧТОБЫ УЗНАТЬ НОВУЮ СТАВКУ
        if car.auction_link:
            driver = create_driver()
            parser = BidCarsParser(driver)
            data = parser.parse_all(car.auction_link)
            
            # Если данные успешно получены и цена не пустая
            if data and data.get('price') and data.get('price') != "$0":
                clean_price = re.sub(r'[^\d.]', '', data.get('price', '0'))
                if clean_price:
                    # Обновляем цену машины в базе данных!
                    car.price_usd = Decimal(clean_price)
        
        # 2. ПЕРЕСЧИТЫВАЕМ ЭКОНОМИКУ (уже с новой ценой авто и свежими тарифами)
        calculator = AutoCalculator()
        calc_result = calculator.calculate_all(
            price_usd=float(car.price_usd),
            engine_volume=car.engine_volume or 0,
            year=car.manufacture_year or 2020,
            custom_shipping=float(proposal.shipping_cost or 0)
        )
        
        # 3. ОБНОВЛЯЕМ ПРЕДЛОЖЕНИЕ
        proposal.customs_fee = Decimal(calc_result['duty_usd'])
        proposal.total_price_usd = Decimal(calc_result['total_usd'])
        proposal.total_price_byn = Decimal(calc_result['total_byn'])
        
        db.session.commit()
        flash(f'Данные обновлены! Актуальная ставка: ${car.price_usd}, Итоговая стоимость: ${proposal.total_price_usd}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при пересчете (возможно, лот удален с аукциона): {e}', 'danger')
    finally:
        # Обязательно закрываем браузер
        if driver:
            try:
                driver.quit()
            except:
                pass
                
    return redirect(url_for('manager.list_proposals'))


