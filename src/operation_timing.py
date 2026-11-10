"""Per-operation timing snapshots and bounded pre-task browsing."""
from contextlib import closing
from pathlib import Path
import json
import random
import sqlite3

FILE = Path("config/operation_timing.json")
DEFAULTS = {"delay_min": 5, "delay_max": 14, "prewarm_enabled": True,
            "prewarm_seconds": 30, "like_percent": 100}


def validate(value):
    result = dict(DEFAULTS, **value)
    for key in ("delay_min", "delay_max", "prewarm_seconds", "like_percent"):
        try:
            result[key] = int(result[key])
        except (TypeError, ValueError):
            raise ValueError("Süre ve oran alanlarına tam sayı girin.")
    if not 0 <= result["delay_min"] <= result["delay_max"] <= 3600:
        raise ValueError("Cihaz aralığı: 0 ≤ minimum ≤ maksimum ≤ 3600 saniye olmalı.")
    if not 0 <= result["like_percent"] <= 100 or not 0 <= result["prewarm_seconds"] <= 300:
        raise ValueError("Beğeni oranı 0–100, ısınma süresi 0–300 saniye olmalı.")
    if not isinstance(result["prewarm_enabled"], bool):
        raise ValueError("Ön ısınma açık/kapalı olmalı.")
    return result


def load(scope):
    try:
        settings = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    return validate(settings.get(scope, {}))


def save(scope, settings):
    settings = validate(settings)
    try:
        all_settings = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        all_settings = {}
    all_settings[scope] = settings
    FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(all_settings, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(FILE)
    return settings


def store_campaign(database, code, settings):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS campaign_timing (camp_code TEXT PRIMARY KEY, settings TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO campaign_timing VALUES (?,?)", (code, json.dumps(validate(settings))))


def campaign_settings(database, code):
    with closing(sqlite3.connect(database)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='campaign_timing'").fetchone():
            return None
        row = db.execute("SELECT settings FROM campaign_timing WHERE camp_code=?", (code,)).fetchone()
    return validate(json.loads(row[0])) if row else None


def delay(settings):
    return random.randint(settings["delay_min"], settings["delay_max"])


def prewarm(device, settings, wait, log=print, stopped=lambda: False):
    """Browse first; at most 1–2 observed unliked controls, never comments."""
    if not settings["prewarm_enabled"]:
        return True
    budget = random.randint(1, 2)
    attempted = 0
    remaining = settings["prewarm_seconds"]
    log(f"[ÖN ISINMA] {remaining} saniye; beğeni üst sınırı {budget}, oran %{settings['like_percent']}.")
    while remaining > 0:
        if stopped():
            return False
        if device is not None:
            try:
                if device.app_current().get("package") == "com.facebook.katana":
                    if attempted < budget and random.random() * 100 < settings["like_percent"]:
                        candidates = device(descriptionMatches="(?i)^like$|^like button[.].*|^beğen$")
                        for item in candidates:
                            info = item.info
                            description = (info.get("contentDescription") or info.get("text") or "").lower()
                            if "pressed" in description or "liked" in description or not info.get("enabled", True):
                                continue
                            b = info.get("bounds", {})
                            if b and b.get("right", 0) > b.get("left", 0) and b.get("bottom", 0) > b.get("top", 0):
                                device.click((b["left"] + b["right"]) // 2, (b["top"] + b["bottom"]) // 2)
                                attempted += 1
                                break
                    device.swipe_ext("up", scale=0.5)
            except Exception as exc:
                log(f"[ÖN ISINMA] Ekran adımı atlandı: {exc}")
        seconds = min(5, remaining)
        if wait(seconds) is False:
            return False
        remaining -= seconds
    log(f"[ÖN ISINMA BİTTİ] {attempted} beğeni denemesi; otomatik yorum yapılmadı.")
    return True
