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
                    if source is None:
                        return False
                    # Активные и завершённые лоты (финальная ставка / sold)
                    markers = (
                        "VIN", "Одометр", "Current Bid", "Текущая ставка",
                        "Final bid", "Финальная", "Sold for", "Продано",
                    )
                    return any(m in source for m in markers)
                except Exception:
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

    # Допустимые символы VIN (без I, O, Q по стандарту; на сайте иногда встречаются — разрешаем при явной метке)
    _VIN_CHARS = "A-HJ-NPR-Z0-9"
    _VIN_ISO_BODY = re.compile(rf"\b[{_VIN_CHARS}]{{17}}\b", re.IGNORECASE)
    _VIN_LOOSE = re.compile(r"\b[A-Z0-9]{8,17}\b", re.IGNORECASE)
    _VIN_LABELED = re.compile(
        rf"(?:VIN|ВИН)\s*[:#.\-]?\s*([{_VIN_CHARS}]{{6,17}})\b",
        re.IGNORECASE,
    )
    _VIN_LABELED_LOOSE = re.compile(
        r"(?:VIN|ВИН)\s*[:#.\-]?\s*([A-Z0-9]{6,17})\b",
        re.IGNORECASE,
    )

    def parse_vin(self, url: str) -> str:
        def _norm_iso(s: str) -> str | None:
            s = (s or "").strip().upper()
            if len(s) != 17:
                return None
            if not re.fullmatch(rf"[{self._VIN_CHARS}]{{17}}", s, re.IGNORECASE):
                return None
            return s

        def _norm_alnum(s: str) -> str | None:
            s = (s or "").strip().upper()
            if 6 <= len(s) <= 17 and re.fullmatch(r"[A-Z0-9]+", s):
                return s
            return None

        # 1. URL — классический 17-символьный VIN
        match = re.search(rf"[{self._VIN_CHARS}]{{17}}", url, re.IGNORECASE)
        if match:
            v = _norm_iso(match.group(0))
            if v:
                return v

        # 2. Таблица характеристик: строка «VIN» / «ВИН»
        try:
            labels = self.driver.find_elements(
                By.XPATH, "//*[contains(@class, 'label') or contains(@class, 'name')]"
            )
            values = self.driver.find_elements(
                By.XPATH, "//*[contains(@class, 'value') or contains(@class, 'data')]"
            )
            for i in range(min(len(labels), len(values))):
                key = labels[i].text.replace(":", "").strip().upper()
                if key in ("VIN", "ВИН"):
                    raw = values[i].text.strip()
                    v = _norm_iso(raw) or _norm_alnum(raw)
                    if v:
                        return v
        except Exception:
            pass

        # 3. H1 — только если целиком похож на идентификатор (17 или короче с буквами+цифрами)
        try:
            h1 = self.driver.find_element(By.TAG_NAME, "h1").text.strip().split("\n")[0].strip()
            v = _norm_iso(h1) or _norm_alnum(h1)
            if v and len(v) >= 8:
                return v
        except Exception:
            pass

        # 4. Текст страницы: явная метка VIN / ВИН
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            m = self._VIN_LABELED.search(body_text)
            if m:
                v = _norm_iso(m.group(1)) or _norm_alnum(m.group(1))
                if v:
                    return v
            m2 = self._VIN_LABELED_LOOSE.search(body_text)
            if m2:
                v = _norm_iso(m2.group(1)) or _norm_alnum(m2.group(1))
                if v:
                    return v
            # 5. Любой 17-символьный ISO в теле
            match_any = self._VIN_ISO_BODY.search(body_text)
            if match_any:
                return match_any.group(0).upper()
            # 6. Строки с меткой VIN — нестандартная длина (напр. номер кузова 8–16 символов)
            lines = [line.strip() for line in body_text.split("\n") if line.strip()]
            for line in lines:
                ul = line.upper()
                if "VIN" not in ul and "ВИН" not in line:
                    continue
                for cand in self._VIN_LOOSE.finditer(line):
                    token = cand.group(0).upper()
                    if not (8 <= len(token) <= 16):
                        continue
                    if not re.search(r"\d", token):
                        continue
                    if not re.search(r"[A-Z]", token):
                        continue
                    return token
        except Exception:
            pass

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

    def _extract_dollar_amount(self, text: str) -> str | None:
        if not text:
            return None
        m = re.search(r"\$[\d,]+(?:\.\d{2})?", text.replace("\xa0", " "))
        return m.group(0) if m else None

    def parse_price(self) -> str:
        # Метод 1: XPath — текущая или финальная ставка (активный и завершённый лот)
        xpaths = [
            "//*[(contains(string(), 'Текущая ставка')) or (contains(string(), 'Current bid'))]"
            "/following::*[contains(string(), '$')][1]",
            "//*[(contains(string(), 'Финальная ставка')) or (contains(string(), 'Final bid')) "
            "or (contains(string(), 'Final price')) or (contains(string(), 'Итоговая ставка')) "
            "or (contains(string(), 'Sold for')) or (contains(string(), 'Продано за')) "
            "or (contains(string(), 'Winning bid')) or (contains(string(), 'Closing bid'))]"
            "/following::*[contains(string(), '$')][1]",
        ]
        for xpath in xpaths:
            try:
                price_element = self.driver.find_element(By.XPATH, xpath)
                got = self._extract_dollar_amount(price_element.text)
                if got:
                    return got
            except Exception:
                continue

        # Метод 2: построчный анализ видимого текста
        price_keywords = (
            "Текущая ставка",
            "Current Bid",
            "Current bid",
            "Купить сейчас",
            "Buy now",
            "Финальная ставка",
            "Final bid",
            "Final price",
            "Итоговая ставка",
            "Окончательная",
            "Sold for",
            "Продано за",
            "Winning bid",
            "Closing bid",
        )
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            lines = [line.strip() for line in body_text.split("\n") if line.strip()]

            for i, line in enumerate(lines):
                if any(k in line for k in price_keywords):
                    for j in range(0, 4):
                        if i + j >= len(lines):
                            break
                        cand = lines[i + j]
                        got = self._extract_dollar_amount(cand)
                        if got:
                            return got
        except Exception:
            pass

        return "Цена не найдена"

    def parse_params(self) -> dict:
        params = {}
        target_keys =[
            "Тип кузова", "Модель", "Серия", "Двигатель",
            "Тип топлива", "Цилиндры", "Коробка передач",
            "Тип приводной линии", "Внешний вид", "Одометр",
            "Первичное повреждение", "Вторичное повреждение", "Местоположение",
            "VIN", "ВИН",
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