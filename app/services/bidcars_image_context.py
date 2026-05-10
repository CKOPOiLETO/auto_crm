# Временное хранилище контекста браузера для прокси картинок BidCars (Cloudflare).
import threading
import time
from uuid import uuid4

_TTL_SEC = 20 * 60
_lock = threading.Lock()
_store: dict[str, dict] = {}


def _prune_unlocked() -> None:
    now = time.time()
    for key in [k for k, v in _store.items() if v["expires"] < now]:
        del _store[key]


def store(selenium_cookies: list, user_agent: str, referer_url: str) -> str:
    token = uuid4().hex
    rec = {
        "expires": time.time() + _TTL_SEC,
        "cookies": list(selenium_cookies),
        "user_agent": (user_agent or "").strip(),
        "referer": (referer_url or "https://bid.cars/").strip(),
    }
    with _lock:
        _prune_unlocked()
        _store[token] = rec
    return token


def get(token: str) -> dict | None:
    if not token or not isinstance(token, str):
        return None
    with _lock:
        _prune_unlocked()
        rec = _store.get(token)
        if not rec:
            return None
        if rec["expires"] < time.time():
            del _store[token]
            return None
        return {
            "cookies": rec["cookies"],
            "user_agent": rec["user_agent"],
            "referer": rec["referer"],
        }
