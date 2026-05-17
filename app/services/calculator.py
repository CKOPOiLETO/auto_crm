# app/services/calculator.py
from datetime import datetime
from decimal import Decimal
from app.models.tariff import Tariff

class AutoCalculator:
    def __init__(self):
        # Загружаем актуальные тарифы из БД
        self.tariff = Tariff.query.first()
        
    def calculate_customs_duty_eur(self, price_eur: float, engine_volume: int, age_category: str, 
                                   engine_type: str = 'fuel', person_type: str = 'physical', 
                                   has_benefit: bool = True) -> float:
        """Точный расчет таможенной пошлины в ЕВРО согласно законодательству РБ/ЕАЭС"""
        
        # 1. ЭЛЕКТРОМОБИЛИ
        if engine_type == 'electric':
            base_duty = 0.0 if person_type == 'physical' else price_eur * 0.15
            
        # 2. АВТО С ДВС (Бензин / Дизель)
        else:
            if person_type == 'physical':
                # ДО 3 ЛЕТ (Считается от стоимости, но не менее X евро за кубик)
                if age_category == 'new':
                    if price_eur <= 8500: base_duty = max(price_eur * 0.54, engine_volume * 2.5)
                    elif price_eur <= 16700: base_duty = max(price_eur * 0.48, engine_volume * 3.5)
                    elif price_eur <= 42300: base_duty = max(price_eur * 0.48, engine_volume * 5.5)
                    elif price_eur <= 84500: base_duty = max(price_eur * 0.48, engine_volume * 7.5)
                    elif price_eur <= 169000: base_duty = max(price_eur * 0.48, engine_volume * 15.0)
                    else: base_duty = max(price_eur * 0.48, engine_volume * 20.0)
                    
                # ОТ 3 ДО 5 ЛЕТ
                elif age_category == 'medium':
                    if engine_volume <= 1000: base_duty = engine_volume * 1.5
                    elif engine_volume <= 1500: base_duty = engine_volume * 1.7
                    elif engine_volume <= 1800: base_duty = engine_volume * 2.5
                    elif engine_volume <= 2300: base_duty = engine_volume * 2.7
                    elif engine_volume <= 3000: base_duty = engine_volume * 3.0
                    else: base_duty = engine_volume * 3.6
                    
                # СТАРШЕ 5 ЛЕТ
                else: 
                    if engine_volume <= 1000: base_duty = engine_volume * 3.0
                    elif engine_volume <= 1500: base_duty = engine_volume * 3.2
                    elif engine_volume <= 1800: base_duty = engine_volume * 3.5
                    elif engine_volume <= 2300: base_duty = engine_volume * 4.8
                    elif engine_volume <= 3000: base_duty = engine_volume * 5.0
                    else: base_duty = engine_volume * 5.7
            
            # ЮРИДИЧЕСКИЕ ЛИЦА
            else: 
                duty = price_eur * 0.15
                vat = (price_eur + duty) * 0.20
                base_duty = duty + vat

        # 3. ПРИМЕНЕНИЕ ЛЬГОТЫ (Указ №140 - только для физлиц)
        if has_benefit and person_type == 'physical':
            return base_duty * 0.5
            
        return base_duty

    def calculate_all(self, price_usd: float, engine_volume: int, year: int, 
                      has_benefit: bool = True, custom_shipping: float = None, 
                      engine_type: str = 'fuel', person_type: str = 'physical') -> dict:
        """Главный метод калькуляции всех расходов"""
        if not self.tariff:
            return {"error": "Тарифы не настроены в панели администратора"}

        # 1. Курсы валют
        rate_usd = float(self.tariff.usd_rate)
        rate_eur = float(self.tariff.eur_rate)
        
        car_price = float(price_usd)
        
        # Переводим цену авто в ЕВРО для точного расчета пошлин
        if rate_eur > 0 and rate_usd > 0:
            price_eur = (car_price * rate_usd) / rate_eur
        else:
            price_eur = car_price * 0.9 # Заглушка, если база пустая
            
        # 2. Возраст автомобиля
        current_year = datetime.now().year
        age = current_year - year if year else 4
        if age < 3: age_category = 'new'
        elif 3 <= age <= 5: age_category = 'medium'
        else: age_category = 'old'

        # 3. Аукционный сбор
        auction_fee = car_price * (float(self.tariff.auction_fee_rate) / 100)
        
        # 4. Логистика (США + Море + Европа)
        shipping_eu_eur = float(self.tariff.shipping_eu)
        shipping_eu_usd = (shipping_eu_eur * rate_eur) / rate_usd if rate_usd > 0 else 0
        
        if custom_shipping is not None:
            logistics_usd = float(custom_shipping)
        else:
            logistics_usd = float(self.tariff.shipping_usa) + float(self.tariff.shipping_sea) + shipping_eu_usd
        
        # 5. ТАМОЖЕННАЯ ПОШЛИНА (вызов новой логики)
        duty_eur = self.calculate_customs_duty_eur(
            price_eur=price_eur, 
            engine_volume=engine_volume, 
            age_category=age_category, 
            engine_type=engine_type, 
            person_type=person_type, 
            has_benefit=has_benefit
        )
        
        # Переводим пошлину обратно в USD
        duty_usd = (duty_eur * rate_eur) / rate_usd if rate_usd > 0 else 0
        
        # 6. Утильсбор и таможенное оформление (в ЕВРО по аналогии с исходником)
        customs_fee_eur = 40.0 # Фикс сбор за таможенное оформление
        
        if person_type == 'physical':
            util_fee_eur = 150.0 if age_category == 'new' else 220.0
        else:
            util_fee_eur = 1200.0
            
        # Конвертируем сборы из ЕВРО в ДОЛЛАРЫ
        clearance_fees_eur = customs_fee_eur + util_fee_eur
        customs_clearance_usd = (clearance_fees_eur * rate_eur) / rate_usd if rate_usd > 0 else 0
        
        # 7. Комиссия компании
        company_fee_usd = 500.0

        # ИТОГО
        total_usd = car_price + auction_fee + logistics_usd + duty_usd + customs_clearance_usd + company_fee_usd
        total_byn = total_usd * rate_usd

        return {
            "car_price_usd": round(car_price, 2),
            "auction_fee_usd": round(auction_fee, 2),
            "logistics_usd": round(logistics_usd, 2),
            "duty_eur": round(duty_eur, 2),
            "duty_usd": round(duty_usd, 2),
            "customs_clearance_usd": round(customs_clearance_usd, 2), # Здесь теперь Утиль + Сбор 40€
            "company_fee_usd": round(company_fee_usd, 2),
            "total_usd": round(total_usd, 2),
            "total_byn": round(total_byn, 2),
            "has_benefit": has_benefit,
            "calc_year": year,
            "calc_volume": engine_volume,
            "rate_usd": round(rate_usd, 4),
            "rate_eur": round(rate_eur, 4),
            "shipping_usa": float(self.tariff.shipping_usa),
            "shipping_sea": float(self.tariff.shipping_sea),
            "shipping_eu_eur": round(shipping_eu_eur, 2),
            "shipping_eu_usd": round(shipping_eu_usd, 2),
            "auction_rate_pct": float(self.tariff.auction_fee_rate)
        }












# # app/services/calculator.py
# from datetime import datetime
# from decimal import Decimal
# from app.models.tariff import Tariff

# class AutoCalculator:
#     def __init__(self):
#         # Загружаем актуальные тарифы из БД при создании калькулятора
#         self.tariff = Tariff.query.first()
        
#     def calculate_customs_duty(self, engine_volume: int, year: int, has_benefit: bool = True) -> float:
#         """Расчет таможенной пошлины в ЕВРО на основе объема двигателя и возраста авто"""
#         if not engine_volume or engine_volume == 0:
#             return 0.0

#         current_year = datetime.now().year
#         age = current_year - year if year else 4 # По умолчанию считаем 3-5 лет
        
#         rate_eur = 0.0
        
#         # Авто от 3 до 5 лет (Самые популярные для пригона)
#         if 3 <= age <= 5:
#             if engine_volume <= 1000: rate_eur = 1.5
#             elif engine_volume <= 1500: rate_eur = 1.7
#             elif engine_volume <= 1800: rate_eur = 2.5
#             elif engine_volume <= 2300: rate_eur = 2.7
#             elif engine_volume <= 3000: rate_eur = 3.0
#             else: rate_eur = 3.6
            
#         # Авто старше 5 лет (Тарифы выше)
#         elif age > 5:
#             if engine_volume <= 1000: rate_eur = 3.0
#             elif engine_volume <= 1500: rate_eur = 3.2
#             elif engine_volume <= 1800: rate_eur = 3.5
#             elif engine_volume <= 2300: rate_eur = 4.8
#             elif engine_volume <= 3000: rate_eur = 5.0
#             else: rate_eur = 5.7
            
#         # Новые авто до 3 лет (считаются от стоимости, но для упрощения сделаем заглушку)
#         else:
#             rate_eur = 2.5 # Усредненный тариф для примера

#         # Считаем пошлину в Евро
#         duty_eur = engine_volume * rate_eur
        
#         # Применяем льготу 50% (Указ №140)
#         if has_benefit:
#             duty_eur *= 0.5
            
#         return duty_eur

#     def calculate_all(self, price_usd: float, engine_volume: int, year: int, has_benefit: bool = True, custom_shipping: float = None) -> dict:
#         """Главный метод калькуляции всех расходов"""
#         if not self.tariff:
#             return {"error": "Тарифы не настроены в панели администратора"}

#         # 1. Цена авто
#         car_price = float(price_usd)
        
#         # 2. Аукционный сбор
#         auction_fee = car_price * (float(self.tariff.auction_fee_rate) / 100)
        
#         # 3. Логистика (США + Море + Европа)
#         # Переводим доставку по Европе (EUR) в USD
#         shipping_eu_eur = float(self.tariff.shipping_eu)
#         if float(self.tariff.usd_rate) > 0:
#             shipping_eu_usd = (shipping_eu_eur * float(self.tariff.eur_rate)) / float(self.tariff.usd_rate)
#         else:
#             shipping_eu_usd = 0.0
        
#         # Если передана кастомная логистика (сохраненная в КП) - берем ее,
#         # иначе считаем ПОЛНЫЙ маршрут по умолчанию (США + Море + Европа)
#         if custom_shipping is not None:
#             logistics_usd = float(custom_shipping)
#         else:
#             logistics_usd = float(self.tariff.shipping_usa) + float(self.tariff.shipping_sea) + shipping_eu_usd
        
#         # 4. Таможня
#         duty_eur = self.calculate_customs_duty(engine_volume, year, has_benefit)
        
#         # Переводим таможню из ЕВРО в Доллары (через BYN по курсам НБРБ)
#         duty_byn = duty_eur * float(self.tariff.eur_rate)
#         duty_usd = duty_byn / float(self.tariff.usd_rate) if float(self.tariff.usd_rate) > 0 else 0
        
#         # 5. Утильсбор и таможенное оформление (фиксированно, примерно 150$)
#         customs_clearance_usd = 150.0 
        
#         # 6. Комиссия вашей компании за подбор
#         company_fee_usd = 500.0

#         # ИТОГО
#         total_usd = car_price + auction_fee + logistics_usd + duty_usd + customs_clearance_usd + company_fee_usd
#         total_byn = total_usd * float(self.tariff.usd_rate)

#         return {
#             "car_price_usd": round(car_price, 2),
#             "auction_fee_usd": round(auction_fee, 2),
#             "logistics_usd": round(logistics_usd, 2),
#             "duty_eur": round(duty_eur, 2),
#             "duty_usd": round(duty_usd, 2),
#             "customs_clearance_usd": round(customs_clearance_usd, 2),
#             "company_fee_usd": round(company_fee_usd, 2),
#             "total_usd": round(total_usd, 2),
#             "total_byn": round(total_byn, 2),
#             "has_benefit": has_benefit,
#             "calc_year": year,
#             "calc_volume": engine_volume,
#             # --- ТАРИФЫ ДЛЯ ВЫВОДА НА ЭКРАН И В PDF ---
#             "rate_usd": round(float(self.tariff.usd_rate), 4),
#             "rate_eur": round(float(self.tariff.eur_rate), 4),
#             "shipping_usa": float(self.tariff.shipping_usa),
#             "shipping_sea": float(self.tariff.shipping_sea),
#             "shipping_eu_eur": round(shipping_eu_eur, 2), # Для отображения по Европе в €
#             "shipping_eu_usd": round(shipping_eu_usd, 2), # Для отображения по Европе в $
#             "auction_rate_pct": float(self.tariff.auction_fee_rate)
#         }