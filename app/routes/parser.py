# app/routes/parser.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from decimal import Decimal
import re
import datetime
from flask_login import current_user

from app import db
from app.models.car import Car
from app.models.client import Client # <--- Импортируем клиентов
from app.models.proposal import Proposal # <--- Импортируем предложения
from app.services.browser import create_driver
from app.services.bidcars_parser import BidCarsParser
import json
from app.services.calculator import AutoCalculator
from datetime import datetime
from selenium.common.exceptions import WebDriverException, NoSuchWindowException

parser_bp = Blueprint('parser', __name__, template_folder='../templates/parser')

@parser_bp.route('/parser', methods=['GET', 'POST'])
#@login_required
def index():
    data = None
    calc_result = None
    clients = None 
    error = None
    
    if request.method == 'POST':
        url = request.form.get('url')
        if url:
            driver = None
            try:
                # 1. Запуск браузера и парсинг
                driver = create_driver()
                parser = BidCarsParser(driver)
                data = parser.parse_all(url)

                # 2. Проверяем, удалось ли получить данные
                # Если цена вернулась как "$0" или None, значит защита нас заблокировала
                if data and data.get('price') and data.get('price') != "$0":
                    
                    # Извлекаем чистое число из цены (убираем $, запятые)
                    clean_price = re.sub(r'[^\d.]', '', data.get('price', '0'))
                    price_val = float(clean_price) if clean_price else 0.0
                    
                    # Извлекаем объем двигателя из параметров
                    engine_vol = data.get('params', {}).get('engine_volume', 0)
                    
                    # Определяем год выпуска из заголовка
                    year_val = datetime.now().year - 4 # Значение по умолчанию
                    if data.get('title'):
                        year_match = re.search(r'\b(19|20)\d{2}\b', data['title'])
                        if year_match:
                            year_val = int(year_match.group(0))
                    
                    # 3. ВЫЗЫВАЕМ КАЛЬКУЛЯТОР
                    calculator = AutoCalculator()
                    calc_result = calculator.calculate_all(
                        price_usd=price_val, 
                        engine_volume=engine_vol, 
                        year=year_val
                    )
                    
                    # 4. ПОДГРУЖАЕМ КЛИЕНТОВ (для модального окна сохранения)
                    if current_user.role == 'admin':
                        clients = Client.query.order_by(Client.fio).all()
                    else:
                        clients = Client.query.filter_by(manager_id=current_user.id).order_by(Client.fio).all()
                
                else:
                    # Если данные пустые, выводим ошибку пользователю
                    error = "Не удалось получить данные лота. Возможно, сайт временно ограничил доступ или ссылка неверна. Попробуйте еще раз через минуту."
                    data = None # Обнуляем, чтобы не показывать пустую карточку

            except (NoSuchWindowException, WebDriverException) as e:
                db.session.rollback()
                error = "Окно браузера было закрыто или соединение прервано. Пожалуйста, не закрывайте окно Chrome во время работы бота."
                print(f"[!] Selenium Error: {e}")
            except Exception as e:
                db.session.rollback()
                error = f"Произошла техническая ошибка: {str(e)}"
                print(f"[!] General Error: {e}")
            finally:
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass 

    return render_template('index.html', data=data, calc_result=calc_result, clients=clients, error=error)
# --- НОВЫЙ РОУТ ДЛЯ СОХРАНЕНИЯ КОММЕРЧЕСКОГО ПРЕДЛОЖЕНИЯ ---
@parser_bp.route('/save_proposal', methods=['POST'])
def save_proposal():
    try:
        # 1. Получаем данные из скрытых полей формы
        client_id = request.form.get('client_id')
        vin = request.form.get('vin')
        title = request.form.get('title')
        auction_link = request.form.get('auction_link')
        price_usd = Decimal(request.form.get('price_usd', 0))
        photo_url = request.form.get('photo_url')
        engine_volume = int(request.form.get('engine_volume', 0))
        manufacture_year = int(request.form.get('manufacture_year', 0))
        all_params = json.loads(request.form.get('all_params_json', '{}'))
        all_photos = json.loads(request.form.get('all_photos_json', '[]'))
        
        
        # 2. Проверяем, есть ли уже такая машина в БД. Если нет - создаем.
        car = Car.query.filter_by(vin=vin).first()
        if not car:
            car = Car(
                vin=vin,
                title=title,
                auction_link=auction_link,
                price_usd=price_usd,
                photo_url=photo_url,
                engine_volume=engine_volume,
                manufacture_year=manufacture_year,
                additional_params=all_params, 
                gallery_urls=all_photos
            )
            db.session.add(car)
            db.session.commit() # Важно закоммитить, чтобы получить car.id

        # 3. Создаем коммерческое предложение и привязываем к машине и клиенту
        new_proposal = Proposal(
            client_id=client_id,
            car_id=car.id,
            shipping_cost=Decimal(request.form.get('logistics_usd', 0)),
            customs_fee=Decimal(request.form.get('duty_usd', 0)),
            total_price_usd=Decimal(request.form.get('total_usd', 0)),
            total_price_byn=Decimal(request.form.get('total_byn', 0)),
            status='draft' # Начальный статус - черновик
        )
        db.session.add(new_proposal)
        db.session.commit()
        
        flash(f'Коммерческое предложение для клиента успешно создано!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при сохранении предложения: {e}', 'danger')
        
    # Возвращаемся на главную страницу парсера
    return redirect(url_for('parser.index'))