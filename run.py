# run.py
from app import create_app

# Создаем экземпляр приложения с помощью нашей фабрики
app = create_app()

if __name__ == '__main__':
    # Запускаем сервер
    # debug=False важно, чтобы Selenium не запускался дважды при автообновлении
    app.run(debug=True, host='0.0.0.0', port=5000)