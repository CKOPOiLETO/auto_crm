# app/services/currency_updater.py
import requests

def get_nbrb_rates():
    """
    Получает актуальные курсы валют с официального API Нацбанка РБ.
    """
    try:
        # Используем современный адрес api.nbrb.by
        usd_resp = requests.get("https://api.nbrb.by/exrates/rates/431", timeout=5)
        eur_resp = requests.get("https://api.nbrb.by/exrates/rates/451", timeout=5)
        
        if usd_resp.status_code == 200 and eur_resp.status_code == 200:
            usd_data = usd_resp.json()
            eur_data = eur_resp.json()
            
            return {
                "usd": round(usd_data['Cur_OfficialRate'], 4),
                "eur": round(eur_data['Cur_OfficialRate'], 4),
                "date": usd_data['Date'][:10] # Дата курса (ГГГГ-ММ-ДД)
            }
    except Exception as e:
        print(f"[-] Ошибка при получении курсов: {e}")
    
    # Резервные данные, если Нацбанк "лежит"
    return {"usd": 3.2500, "eur": 3.4500, "date": "Error"}