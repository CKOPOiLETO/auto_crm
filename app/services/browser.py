# # app/services/browser.py исправленный вариант
# import undetected_chromedriver as uc

# def create_driver():
#     options = uc.ChromeOptions()
#     options.add_argument("--window-size=1920,1080")
    
#     # Пытаемся запустить (библиотека сама найдет версию вашего Chrome)
#     driver = uc.Chrome(options=options)
    
#     return driver
# app/services/browser.py
import undetected_chromedriver as uc
import os

def create_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage") # Помогает при нехватке памяти
    options.add_argument("--no-sandbox")
    
    # Пытаемся запустить без жесткой привязки к версии, 
    # библиотека сама найдет подходящий патч.
    # use_subprocess=True критически важен для стабильности на Windows
    try:
        driver = uc.Chrome(options=options, use_subprocess=True)
    except Exception as e:
        print(f"[!] Ошибка запуска Chrome: {e}")
        # Если не вышло, пробуем еще раз (иногда со второй попытки ок)
        driver = uc.Chrome(options=options, use_subprocess=True)
        
    return driver