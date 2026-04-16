import pdfkit

path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

try:
    pdfkit.from_string('<h1>Hello! It works!</h1>', 'test.pdf', configuration=config)
    print("✅ СИСТЕМА ГОТОВА: Файл test.pdf успешно создан в папке проекта.")
except Exception as e:
    print(f"❌ ОШИБКА СИСТЕМЫ: {e}")