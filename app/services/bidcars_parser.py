# app/services/bidcars_parser.py
import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class BidCarsParser:
    def __init__(self, driver, timeout=30):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    # Находим метод open_lot в файле app/services/bidcars_parser.py и заменяем:

    def open_lot(self, url: str):
        print(f"[*] Переход на страницу: {url}")
        try:
            self.driver.get(url)
            print("[*] Ожидаю загрузки данных лота...")
            
            # Умное ожидание с проверкой на None
            def check_loaded(d):
                try:
                    source = d.page_source
                    if source is None: return False
                    return "VIN" in source or "Одометр" in source or "Current Bid" in source
                except:
                    return False

            self.wait.until(check_loaded)
            time.sleep(3) 
            self.click_show_more()
        except Exception as e:
            print(f"[-] Данные не появились или окно закрылось: {e}")
            # Не выбрасываем ошибку дальше, чтобы парсер попытался 
            # собрать то, что успело загрузиться

    def click_show_more(self):
        selectors = [
            "//div[contains(@class, 'show-more')]",
            "//span[contains(text(), 'Показать больше')]",
            "//button[contains(text(), 'Показать больше')]",
            "//*[contains(text(), 'Show more')]"
        ]
        for xpath in selectors:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)
                    break
            except:
                continue

    def parse_vin(self, url: str) -> str:
        # 1. Ищем в URL (учитываем любой регистр)
        match = re.search(r'[a-hj-npr-z0-9]{17}', url, re.IGNORECASE)
        if match: 
            return match.group(0).upper()
            
        # 2. Ищем в заголовке H1 (как выяснилось, сайт иногда пихает VIN туда)
        try:
            h1 = self.driver.find_element(By.TAG_NAME, "h1").text.strip()
            if re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', h1, re.IGNORECASE):
                return h1.upper()
        except: pass
            
        # 3. Ищем просто в тексте страницы любую 17-значную строку
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            match_any = re.search(r'\b[A-HJ-NPR-Z0-9]{17}\b', body_text, re.IGNORECASE)
            if match_any:
                return match_any.group(0).upper()
        except: pass

        return "VIN не найден"

    def parse_title(self) -> str:
        # 1. Надежный способ: берем из названия вкладки браузера
        try:
            page_title = self.driver.title
            # Отрезаем слова "купить", "аукцион", "bid.cars" и всё, что после них
            clean_title = re.split(r'(?i)купить|аукцион|bid\.cars|\||-', page_title)[0].strip()
            
            # Проверяем, что в названии есть год (например, 2019) и это НЕ 17-значный VIN
            if re.search(r'\b(19|20)\d{2}\b', clean_title) and not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', clean_title, re.IGNORECASE):
                return clean_title
        except: pass

        # 2. Запасной способ: ищем по тексту страницы
        selectors =[".title", ".name", ".lot-title", "h2", "h1"]
        for s in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, s)
                for el in elements:
                    text = el.text.strip()
                    if re.search(r'\b(19|20)\d{2}\b', text) and not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', text, re.IGNORECASE):
                        return text.split('\n')[0]
            except: continue
            
        return "Название не найдено"

    def parse_price(self) -> str:
        # Метод 1: Строгий поиск по XPath относительно фразы "Текущая ставка"
        try:
            # Ищем любой текст, содержащий "Текущая ставка", и берем первый элемент с '$' после него
            xpath = "//*[contains(text(), 'Текущая ставка') or contains(text(), 'Current bid')]/following::*[contains(text(), '$')][1]"
            price_element = self.driver.find_element(By.XPATH, xpath)
            # Извлекаем только саму сумму, отбрасывая 'USD' и прочий текст
            match = re.search(r'\$[\d,]+', price_element.text)
            if match:
                return match.group(0)
        except:
            pass

        # Метод 2: Построчный анализ видимого текста (самый надежный для динамики)
        try:
            # Берем только видимый текст на странице (без скрытых депозитов за $200)
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            lines =[line.strip() for line in body_text.split('\n') if line.strip()]
            
            for i, line in enumerate(lines):
                # Ищем строку с ключевыми словами аукциона
                if "Текущая ставка" in line or "Current Bid" in line or "Купить сейчас" in line:
                    # Смотрим саму строку и следующие 2 строки вниз
                    for j in range(0, 3):
                        if i + j < len(lines):
                            cand = lines[i+j]
                            if "$" in cand:
                                match = re.search(r'\$[\d,]+', cand)
                                if match:
                                    return match.group(0)
        except:
            pass
            
        return "Цена не найдена"

    def parse_params(self) -> dict:
        params = {}
        target_keys =[
            "Тип кузова", "Модель", "Серия", "Двигатель", 
            "Тип топлива", "Цилиндры", "Коробка передач", 
            "Тип приводной линии", "Внешний вид", "Одометр",
            "Первичное повреждение", "Вторичное повреждение", "Местоположение"
        ]
        
        try:
            # Метод 1: поиск по классам label/value
            labels = self.driver.find_elements(By.XPATH, "//*[contains(@class, 'label') or contains(@class, 'name')]")
            values = self.driver.find_elements(By.XPATH, "//*[contains(@class, 'value') or contains(@class, 'data')]")
            
            for i in range(len(labels)):
                key = labels[i].text.replace(":", "").strip()
                if key in target_keys:
                    try:
                        params[key] = values[i].text.strip()
                    except: pass

            # Метод 2: построчное чтение текста (запасной)
            if len(params) < 3:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                lines =[l.strip() for l in body_text.split('\n') if l.strip()]
                for i, line in enumerate(lines):
                    clean_key = line.replace(":", "").strip()
                    if clean_key in target_keys and i + 1 < len(lines):
                        params[clean_key] = lines[i+1].strip()

            # Обработка объема двигателя для таможенного калькулятора
            if "Двигатель" in params:
                vol_match = re.search(r'(\d+\.\d+)', params["Двигатель"])
                if vol_match:
                    params["engine_volume"] = int(float(vol_match.group(1)) * 1000)

        except Exception as e:
            print(f"[-] Ошибка параметров: {e}")
            
        return params

    def parse_photos(self) -> list:
        photos =[]
        try:
            self.driver.execute_script("window.scrollTo(0, 600);")
            time.sleep(2)
            
            imgs = self.driver.find_elements(By.TAG_NAME, "img")
            
            # Жёсткий "черный список". Добавили '/img/upd/' для отсечения иконок портов
            bad_words =[
                'logo', 'icon', 'map', 'avatar', 'user', 'flag', 
                'banner', 'placeholder', 'svg', 'manager', 
                'team', 'similar', 'related', 'thumb', 'employee',
                '/img/upd/', 'port'  # <--- НОВЫЕ ФИЛЬТРЫ
            ]
            
            for img in imgs:
                full_src = img.get_attribute("full-src")
                src = img.get_attribute("src")
                
                img_url = full_src if full_src else src
                
                if not img_url: 
                    continue
                    
                img_url_lower = img_url.lower()
                
                # 1. Проверяем формат
                if not any(ext in img_url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    continue
                    
                # 2. Отсеиваем карты, логотипы, аватарки и ИКОНКИ ПОРТОВ
                if any(bad in img_url_lower for bad in bad_words):
                    continue
                
                # 3. Фильтр мелких картинок
                try:
                    width = int(img.get_attribute("width") or 0)
                    if not full_src and width > 0 and width < 250:
                        continue 
                except:
                    pass

                if img_url not in photos:
                    photos.append(img_url)
                    
        except Exception as e:
            print(f"[-] Ошибка при парсинге фотографий: {e}")
            
        return photos

    def parse_all(self, url: str) -> dict:
        self.open_lot(url)
        return {
            "url": url,
            "title": self.parse_title(),
            "price": self.parse_price(),
            "vin": self.parse_vin(url),
            "params": self.parse_params(),
            "photos": self.parse_photos()
        }