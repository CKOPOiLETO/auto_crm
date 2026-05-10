# app/routes/parser.py
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort, Response
from decimal import Decimal
import re
import datetime
from urllib.parse import urlparse, unquote
from flask_login import current_user
from flask_login import login_required
import requests

from app import db
from app.models.car import Car
from app.models.client import Client # <--- Импортируем клиентов
from app.models.proposal import Proposal # <--- Импортируем предложения
from app.services.browser import create_driver
from app.services.bidcars_parser import BidCarsParser
from app.services import bidcars_image_context
import json
from app.services.calculator import AutoCalculator
from datetime import datetime
from selenium.common.exceptions import WebDriverException, NoSuchWindowException

parser_bp = Blueprint('parser', __name__, template_folder='../templates/parser')

_BIDCARS_HOST_EXACT = frozenset({'bid.cars', 'www.bid.cars'})
_BIDCARS_HOST_SUFFIX = '.bid.cars'
_MAX_PROXY_IMAGE_BYTES = 12 * 1024 * 1024
_IMAGE_REQ_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
}


def _allowed_bidcars_image_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ('http', 'https'):
            return False
        host = parsed.netloc.lower().split(':')[0]
        if host in _BIDCARS_HOST_EXACT:
            return True
        return host.endswith(_BIDCARS_HOST_SUFFIX)
    except Exception:
        return False


def _url_looks_like_image(url: str) -> bool:
    lower = url.lower().split('?', 1)[0]
    return lower.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))


def _fetch_bidcars_image_bytes(url: str, ctx: dict) -> tuple[bytes, str]:
    """Загрузка изображения с cookies/UA из сессии Selenium (иначе Cloudflare отдаёт 403)."""
    sess = requests.Session()
    for c in ctx.get('cookies') or []:
        name, value = c.get('name'), c.get('value')
        if not name:
            continue
        try:
            sess.cookies.set(
                name,
                value,
                domain=c.get('domain'),
                path=c.get('path') or '/',
            )
        except Exception:
            continue

    ref = (ctx.get('referer') or 'https://bid.cars/').strip()
    if not ref.endswith('/'):
        ref = ref + '/'
    try:
        p = urlparse(ref)
        origin = f'{p.scheme}://{p.netloc}' if p.scheme and p.netloc else 'https://bid.cars'
    except Exception:
        origin = 'https://bid.cars'

    ua = (ctx.get('user_agent') or '').strip() or _IMAGE_REQ_HEADERS['User-Agent']
    headers = {
        'User-Agent': ua,
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': ref,
        'Origin': origin,
        'Sec-Fetch-Dest': 'image',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'same-site',
    }
    r = sess.get(url, timeout=25, headers=headers, allow_redirects=True)
    r.raise_for_status()
    data = r.content
    if len(data) > _MAX_PROXY_IMAGE_BYTES:
        raise ValueError('image too large')
    head = data[:64].lstrip().lower()
    if head.startswith(b'<!doctype') or head.startswith(b'<html'):
        raise ValueError('unexpected html (cloudflare?)')
    ct = (r.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    if ct.startswith('image/'):
        content_type = ct
    elif _url_looks_like_image(url):
        content_type = 'image/jpeg'
    else:
        raise ValueError('not an image')
    return data, content_type


@parser_bp.route('/parser/bidcars-image')
def bidcars_image():
    """Прокси картинок: CORP + Cloudflare — нужны cookie/UA от Selenium (параметр ck)."""
    raw = request.args.get('url', '')
    url = unquote(raw) if raw else ''
    ck = (request.args.get('ck') or '').strip()
    if not _allowed_bidcars_image_url(url):
        abort(404)
    ctx = bidcars_image_context.get(ck) if ck else None
    if not ctx:
        abort(401)
    try:
        data, content_type = _fetch_bidcars_image_bytes(url, ctx)
    except (requests.RequestException, ValueError) as e:
        print(f"[!] bidcars-image failed: {e}")
        abort(502)
    return Response(
        data,
        mimetype=content_type,
        headers={'Cache-Control': 'private, max-age=300'},
    )


@parser_bp.route('/parser', methods=['GET', 'POST'])
#@login_required
def index():
    data = None
    calc_result = None
    clients = None 
    error = None
    img_ck_token = None

    if request.method == 'POST':
        url = request.form.get('url')
        if url:
            driver = None
            try:
                # 1. Запуск браузера и парсинг
                driver = create_driver()
                parser = BidCarsParser(driver)
                data = parser.parse_all(url)

                # Контекст для прокси фото (Cloudflare пропускает только с cookie из этого браузера)
                if data and data.get('photos'):
                    try:
                        ua = driver.execute_script("return navigator.userAgent")
                        lot_ref = (data.get('url') or url).strip()
                        img_ck_token = bidcars_image_context.store(
                            driver.get_cookies(), ua, lot_ref
                        )
                    except Exception as e:
                        print(f"[!] bidcars image context: {e}")

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

    return render_template(
        'index.html',
        data=data,
        calc_result=calc_result,
        clients=clients,
        error=error,
        img_ck_token=img_ck_token,
    )
# --- НОВЫЙ РОУТ ДЛЯ СОХРАНЕНИЯ КОММЕРЧЕСКОГО ПРЕДЛОЖЕНИЯ ---
# app/routes/parser.py

@parser_bp.route('/save_proposal', methods=['POST'])
@login_required
def save_proposal():
    try:
        client_id = request.form.get('client_id')
        vin = request.form.get('vin')
        title = request.form.get('title')
        auction_link = request.form.get('auction_link')
        price_usd = Decimal(request.form.get('price_usd', 0))
        photo_url = request.form.get('photo_url')
        engine_volume = int(request.form.get('engine_volume', 0))
        manufacture_year = int(request.form.get('manufacture_year', 0))
        
        # Получаем словари характеристик и фото
        import json
        all_params = json.loads(request.form.get('all_params_json', '{}'))
        all_photos = json.loads(request.form.get('all_photos_json', '[]'))

        # --- ИЗВЛЕКАЕМ ТИП ТОПЛИВА И ПОВРЕЖДЕНИЯ ---
        # Ограничиваем длину до 20 символов, чтобы не было ошибки базы данных
        fuel = all_params.get('Тип топлива', 'Не указан')[:20]
        
        # Склеиваем первичное и вторичное повреждения
        primary_dmg = all_params.get('Первичное повреждение', '')
        secondary_dmg = all_params.get('Вторичное повреждение', '')
        
        if primary_dmg and secondary_dmg:
            damage = f"{primary_dmg} / {secondary_dmg}"
        elif primary_dmg:
            damage = primary_dmg
        elif secondary_dmg:
            damage = secondary_dmg
        else:
            damage = "Не указано"
            
        # Ограничиваем длину до 100 символов, согласно VARCHAR(100) в БД
        damage = damage[:100]

        # 2. Проверяем, есть ли машина, если нет - создаем
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
                fuel_type=fuel,           # <--- СОХРАНЯЕМ ТИП ТОПЛИВА
                damage_type=damage,       # <--- СОХРАНЯЕМ ПОВРЕЖДЕНИЯ
                additional_params=all_params, 
                gallery_urls=all_photos
            )
            db.session.add(car)
            db.session.commit()

        # 3. Создаем коммерческое предложение
        new_proposal = Proposal(
            client_id=client_id,
            car_id=car.id,
            shipping_cost=Decimal(request.form.get('logistics_usd', 0)),
            customs_fee=Decimal(request.form.get('duty_usd', 0)),
            total_price_usd=Decimal(request.form.get('total_usd', 0)),
            total_price_byn=Decimal(request.form.get('total_byn', 0)),
            status='draft'
        )
        db.session.add(new_proposal)
        db.session.commit()
        
        flash(f'Коммерческое предложение успешно создано!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при сохранении предложения: {e}', 'danger')
        print(f"[!] Save Error: {e}")
        
    return redirect(url_for('parser.index'))