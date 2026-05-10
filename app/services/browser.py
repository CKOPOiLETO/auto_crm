# app/services/browser.py
import undetected_chromedriver as uc

def create_driver():
    # Выносим настройки в отдельную функцию, чтобы избегать ошибки "cannot reuse ChromeOptions"
    def get_options():
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        return options

    try:
        # Жестко указываем 147 версию (так как у вас установлен Chrome 147)
        driver = uc.Chrome(options=get_options(), use_subprocess=True, version_main=147)
        driver.set_page_load_timeout(30)
    except Exception as e:
        print(f"[!] Ошибка запуска Chrome: {e}")
        # Пробуем второй раз с НОВЫМИ опциями
        driver = uc.Chrome(options=get_options(), use_subprocess=True, version_main=147)
        driver.set_page_load_timeout(30)
        
    return driver
# import undetected_chromedriver as uc
# import os

# def create_driver():
#     options = uc.ChromeOptions()
#     options.add_argument("--window-size=1920,1080")
#     options.add_argument("--disable-dev-shm-usage") # Помогает при нехватке памяти
#     options.add_argument("--no-sandbox")
    
#     # Пытаемся запустить без жесткой привязки к версии, 
#     # библиотека сама найдет подходящий патч.
#     # use_subprocess=True критически важен для стабильности на Windows
#     try:
#         driver = uc.Chrome(options=options, use_subprocess=True)
#     except Exception as e:
#         print(f"[!] Ошибка запуска Chrome: {e}")
#         # Если не вышло, пробуем еще раз (иногда со второй попытки ок)
#         driver = uc.Chrome(options=options, use_subprocess=True)
        
#     return driver