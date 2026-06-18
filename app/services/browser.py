# app/services/browser.py
import re
import subprocess
import undetected_chromedriver as uc


def _detect_chrome_major() -> int | None:
    """Определяем major-версию установленного Chrome (Windows / Linux / macOS)."""
    try:
        import winreg

        for hive, path in (
            (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Google\Chrome\BLBeacon"),
        ):
            try:
                with winreg.OpenKey(hive, path) as key:
                    version, _ = winreg.QueryValueEx(key, "version")
                    major = int(str(version).split(".", 1)[0])
                    return major
            except OSError:
                continue
    except ImportError:
        pass

    for cmd in (
        ["google-chrome", "--version"],
        ["chromium-browser", "--version"],
        ["chromium", "--version"],
        [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--version"],
    ):
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=5)
            m = re.search(r"(\d+)\.", out)
            if m:
                return int(m.group(1))
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            continue
    return None


def create_driver():
    def get_options():
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.page_load_strategy = "eager"
        return options

    chrome_major = _detect_chrome_major()
    attempts: list[dict] = []
    if chrome_major:
        attempts.append({"version_main": chrome_major})
    attempts.append({})
    if chrome_major:
        attempts.append({"version_main": chrome_major, "use_subprocess": False})

    last_error = None
    for kwargs in attempts:
        try:
            driver = uc.Chrome(options=get_options(), use_subprocess=True, **kwargs)
            driver.set_page_load_timeout(45)
            driver.implicitly_wait(2)
            return driver
        except Exception as e:
            last_error = e
            print(f"[!] Ошибка запуска Chrome ({kwargs or 'auto'}): {e}")

    raise RuntimeError(f"Не удалось запустить Chrome: {last_error}")
