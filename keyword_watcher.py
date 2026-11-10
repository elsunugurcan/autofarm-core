"""Monitoring plus explicit single-account replies to inbound requests in owned groups."""
import json
import os
from pathlib import Path
import re
import signal
import shlex
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from src import watcher_history as history
from src import comment_reply
from src.facebook_navigation import clean_post_url, open_post_comments
from src.delivery_check import recheck_comment
from src import operation_timing as timing

WATCH_FILE = str(Path(__file__).resolve().parent / "config/watched_posts.json")
STOP = False


def log(message):
    global STOP
    try:
        print(message, flush=True)
    except BrokenPipeError:
        STOP = True
        sys.stdout = open(os.devnull, "w")


def valid_target(value):
    try:
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"https", "http"} and (host == "facebook.com" or host.endswith(".facebook.com")) and parsed.path not in {"", "/"} and "..." not in value
    except (ValueError, AttributeError):
        return False


def normalized(text):
    text = text.replace("İ", "i").replace("I", "ı").casefold().replace("ı", "i")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def match_keyword(text, keywords):
    haystack = normalized(text)
    for keyword in keywords.split(","):
        keyword = keyword.strip()
        if not keyword:
            continue
        if keyword == "*":
            return "*"
        needle = normalized(keyword)
        if not needle:
            continue
        pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)" if needle[0].isalnum() else re.escape(needle)
        if re.search(pattern, haystack):
            return keyword
    return ""


def visible_text(xml):
    texts, seen = [], set()
    for node in ET.fromstring(xml).iter("node"):
        if node.attrib.get("visible-to-user") == "false":
            continue
        if node.attrib.get("class") in {"android.widget.EditText", "android.widget.Button"}:
            continue
        for attribute in ("text", "content-desc"):
            value = " ".join(node.attrib.get(attribute, "").split())
            if 4 <= len(value) <= 1500 and value not in seen:
                texts.append(value)
                seen.add(value)
    return texts


def adb(*args, timeout=20):
    result = subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "ADB komutu başarısız")[:300])
    return result.stdout


def online_serials():
    lines = adb("devices").splitlines()[1:]
    return {parts[0] for line in lines if len(parts := line.split()) >= 2 and parts[1] == "device"}


def stopping(run_id):
    return STOP or history.should_stop(run_id)


def wait_for(seconds, run_id):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if stopping(run_id):
            return False
        time.sleep(min(0.5, max(0, end - time.monotonic())))
    return not stopping(run_id)


def read_target(serial, target, run_id):
    import uiautomator2 as u2
    device = u2.connect(serial)
    device.implicitly_wait(1)
    device.screen_on()
    log(f"[HEDEF AÇILIŞI] {clean_post_url(target)}")
    adb("-s", serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(clean_post_url(target)), "com.facebook.katana")
    if not wait_for(5, run_id):
        return [], "Durdurma istendi."
    if device.app_current().get("package") != "com.facebook.katana":
        raise RuntimeError("Facebook hedef görünümü açılamadı; farklı uygulamadaki metinler kaydedilmedi.")
    auth = device(textMatches="(?i)^log in$|^giriş yap$|^enter password$|^şifre gir$")
    if auth.exists:
        raise RuntimeError("Giriş/doğrulama ekranı görünüyor. Oturumu telefonda kendiniz kontrol edin.")
    # Open the comments view only via an identified reading control. No coordinate fallback.
    comments = device(descriptionMatches="(?i)^comments?$|^yorumlar$|^yorum yap$")
    if comments.exists:
        comments[0].click()
        if not wait_for(1, run_id):
            return [], "Durdurma istendi."
    texts = []
    for page in range(3):
        if stopping(run_id):
            break
        texts.extend(visible_text(device.dump_hierarchy()))
        if page < 2:
            device.swipe_ext("up", scale=0.5)
            if not wait_for(1, run_id):
                break
    return list(dict.fromkeys(texts)), "Görünür ekran metni tarandı. Yorum sahibi/yorum kimliği ve tüm yorumların okunduğu doğrulanmadı."


def sleep_phone(serial):
    # Close Facebook after every scan (including errors/stops), then sleep.
    for args in [("am", "force-stop", "com.facebook.katana"), ("input", "keyevent", "3"), ("input", "keyevent", "223")]:
        try:
            adb("-s", serial, "shell", *args, timeout=10)
        except Exception as exc:
            log(f"[NÖBETÇİ KAPATMA HATASI] {serial}: {exc}")
    try:
        pid = adb("-s", serial, "shell", "pidof com.facebook.katana || true", timeout=10).strip()
        log(f"[NÖBETÇİ GÖREV SONU] {serial}: " + ("Facebook kapalı: doğrulandı." if not pid else "Facebook kapanışı doğrulanamadı."))
    except Exception as exc:
        log(f"[NÖBETÇİ KAPATMA KONTROLÜ] {serial}: {exc}")


def check_readiness(serial):
    tunnel = adb("-s", serial, "shell", "ip", "addr", "show", "tun0")
    if "inet " not in tunnel:
        return False, "VPN tüneli kapalı; hedef açılmadı."
    battery = adb("-s", serial, "shell", "dumpsys", "battery")
    match = re.search(r"temperature:\s*(\d+)", battery)
    if not match:
        return False, "Batarya sıcaklığı okunamadı; hedef açılmadı."
    temperature = int(match.group(1)) / 10
    if temperature >= 42.5:
        return False, f"Sıcaklık {temperature}°C; telefon dinlenmeye bırakıldı."
    return True, ""


def auto_reply_target(serial, target, run_id, scan_id, settings, node, account):
    import uiautomator2 as u2
    device = u2.connect(serial)
    device.implicitly_wait(1)
    device.screen_on()
    log(f"[HEDEF AÇILIŞI] {clean_post_url(target)}")
    adb("-s", serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(clean_post_url(target)), "com.facebook.katana")
    if not wait_for(5, run_id):
        return 0, 0, "Durdurma istendi."
    if device.app_current().get("package") != "com.facebook.katana":
        raise RuntimeError("Facebook hedef görünümü açılamadı.")
    diagnostic = Path(WATCH_FILE).parent.parent / "logs" / "watcher_layout"
    diagnostic.mkdir(parents=True, exist_ok=True)
    def record_navigation(stage, xml):
        (diagnostic / f"scan_{scan_id}_{stage}.xml").write_text(xml, encoding="utf-8")
    open_post_comments(device, lambda seconds: wait_for(seconds, run_id), lambda: stopping(run_id), record_navigation)
    attempts, found = 0, 0
    skipped_replied, skipped_recorded = set(), set()
    own_names = {comment_reply.norm(v.get("fb_name", "")) for v in settings.get("device_metadata", {}).values() if v.get("fb_name")}
    for page in range(3):
        if stopping(run_id):
            break
        xml = device.dump_hierarchy()
        candidates = comment_reply.comments_from_xml(xml)
        # Local diagnostic data for selector calibration; never send it to a third party.
        (diagnostic / f"scan_{scan_id}_page_{page+1}.xml").write_text(xml, encoding="utf-8")
        found += len(candidates)
        for candidate in candidates:
            if stopping(run_id) or attempts >= settings["max_replies_per_visit"]:
                break
            if comment_reply.norm(candidate["author"]) in own_names:
                continue
            if candidate.get("has_replies"):
                skipped_replied.add((candidate["author"], candidate["text"]))
                log(f"[YANIT ATLANDI] {candidate['author']}: View reply göstergesi var.")
                continue
            keyword = match_keyword(candidate["text"], settings["keywords"])
            if not keyword:
                continue
            history.add_finding(run_id, scan_id, node, serial, account, target,
                                candidate["text"], keyword, settings["reply_template"])
            key = comment_reply.comment_key(target, candidate["author"], candidate["text"])
            row_id = history.reserve_auto_reply(key, run_id, scan_id, node, serial, account, target,
                                                candidate["author"], candidate["text"], settings["reply_template"])
            if row_id is None:
                skipped_recorded.add((candidate["author"], candidate["text"]))
                continue
            attempts += 1
            sending = False
            def before_send():
                nonlocal sending
                history.update_auto_reply(row_id, "SENDING", "Send düğmesi tetikleniyor; sonuç henüz doğrulanmadı.")
                sending = True
            try:
                def delivery_record(stage, xml):
                    (diagnostic / f"scan_{scan_id}_reply_{row_id}_{stage}.xml").write_text(xml, encoding="utf-8")
                def reopen_target():
                    if stopping(run_id):
                        return False
                    adb("-s", serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(clean_post_url(target)), "com.facebook.katana")
                    return wait_for(5, run_id) and device.app_current().get("package") == "com.facebook.katana"
                def verify_delivery():
                    return recheck_comment(device, account, settings["reply_template"], reopen_target,
                        lambda seconds: wait_for(seconds, run_id), candidate, delivery_record)
                state, message = comment_reply.send_reply(device, candidate, settings["reply_template"],
                    lambda: stopping(run_id), lambda seconds: wait_for(seconds, run_id), before_send,
                    recheck=verify_delivery, record=delivery_record)
                history.update_auto_reply(row_id, state, message)
                log(f"[OTOMATİK YANIT] {node} | {candidate['author']}: {message}")
            except Exception as exc:
                try:
                    (diagnostic / f"scan_{scan_id}_reply_{row_id}_error.xml").write_text(device.dump_hierarchy(), encoding="utf-8")
                except Exception:
                    pass
                history.update_auto_reply(row_id, "UNKNOWN" if sending else "NOT_SENT", str(exc))
                log(f"[OTOMATİK YANIT DURDU] {node}: {exc}")
                # Leave an uncertain composer untouched; never redirect later actions into it.
                return found, attempts, f"Yanıt akışı durdu: {exc}. Ayrıntılar Otomatik Yanıt Kayıtları sekmesinde."
        if attempts >= settings["max_replies_per_visit"] or stopping(run_id):
            break
        if page < 2:
            device.swipe_ext("up", scale=0.5)
            if not wait_for(1, run_id):
                break
    message = f"{found} açık yorum satırı, {attempts} yanıt denemesi. Yayın sonucu Facebook'tan kontrol edilmeli."
    message += f" Yanıt göstergesi olan {len(skipped_replied)}, önceki denemesi kayıtlı {len(skipped_recorded)} yorum atlandı."
    if not found:
        message = "Yorum yazarı/metni/Reply düğmesi aynı satırda güvenilir biçimde eşleştirilemedi; yanıt gönderilmedi. XML tanı dosyaları logs/watcher_layout içinde."
    return found, attempts, message


def scan_cycle(run_id, settings, reader=read_target):
    if settings.get("auto_reply_enabled") and settings.get("sequential_enabled"):
        from src.sequential_watcher import scan_cycle as sequential_cycle
        return sequential_cycle(sys.modules[__name__], run_id, settings)
    online = online_serials()
    selected = settings["selected_serials"]
    devices = settings.get("device_metadata", {})
    limit = max(1, min(50, int(settings.get("max_replies_per_visit", 3))))
    options = timing.validate(settings["timing"]) if "timing" in settings else None
    for index, target in enumerate(settings["posts"]):
        if stopping(run_id):
            break
        if index and options:
            seconds = timing.delay(options)
            log(f"[CİHAZ ARALIĞI] Sonraki hedef için {seconds} saniye bekleniyor.")
            if not wait_for(seconds, run_id):
                break
        serial = selected[index % len(selected)]
        meta = devices.get(serial, {})
        node, account = meta.get("node_id", "Bilinmiyor"), meta.get("fb_name", "Kayıtlı ad yok")
        scan_id = history.start_scan(run_id, node, serial, account, target)
        history.update_run(run_id, "RUNNING", f"{node} / {serial}: {target}")
        log(f"[NÖBETÇİ] {node} | {serial} | Kontrol: {target}")
        if serial not in online:
            history.finish_scan(scan_id, "SKIPPED", "Telefon OFFLINE; kontrol yapılmadı.")
            continue
        try:
            ready, reason = check_readiness(serial)
            if not ready:
                history.finish_scan(scan_id, "SKIPPED", reason)
                continue
            if options and options["prewarm_enabled"]:
                import uiautomator2 as u2
                warm_device = u2.connect(serial)
                warm_device.screen_on()
                adb("-s", serial, "shell", "monkey", "-p", "com.facebook.katana", "-c", "android.intent.category.LAUNCHER", "1")
                warm_options = dict(options)
                if not settings.get("auto_reply_enabled"):
                    warm_options["like_percent"] = 0
                if not timing.prewarm(warm_device, warm_options, lambda seconds: wait_for(seconds, run_id), log, lambda: stopping(run_id)):
                    history.finish_scan(scan_id, "INTERRUPTED", "Ön ısınma sırasında durduruldu.")
                    break
            if settings.get("auto_reply_enabled"):
                count, attempts, note = auto_reply_target(serial, target, run_id, scan_id, settings, node, account)
                state = "INTERRUPTED" if stopping(run_id) else "AUTO_ATTEMPTED" if attempts else "CONTEXT_MISSING" if not count else "DONE"
                history.finish_scan(scan_id, state, note, attempts, count)
                log(f"[NÖBETÇİ] {node}: {note}")
                continue
            texts, note = reader(serial, target, run_id)
            new_matches = 0
            for candidate in texts:
                # Identified adapters may supply a permalink; native screen-only reads stay unverified.
                text = candidate.get("text", "") if isinstance(candidate, dict) else candidate
                comment_url = candidate.get("comment_url", "") if isinstance(candidate, dict) else ""
                author = candidate.get("author", "") if isinstance(candidate, dict) else ""
                keyword = match_keyword(text, settings["keywords"])
                if keyword and new_matches < limit:
                    new_matches += history.add_finding(run_id, scan_id, node, serial, account, target,
                                                       text, keyword, settings.get("reply_template", ""), comment_url, author)
            state = "INTERRUPTED" if stopping(run_id) else "DONE" if texts else "UNREADABLE"
            history.finish_scan(scan_id, state, note, new_matches, len(texts))
            log(f"[NÖBETÇİ] {node}: {len(texts)} metin, {new_matches} yeni eşleşme. Yanıt gönderilmedi.")
        except Exception as exc:
            history.finish_scan(scan_id, "ERROR", str(exc)[:1500])
            log(f"[NÖBETÇİ HATA] {node}: {exc}")
        finally:
            sleep_phone(serial)


def validate_settings(settings):
    settings = dict(settings)
    if "timing" in settings:
        settings["timing"] = timing.validate(settings["timing"])
    settings["posts"] = list(dict.fromkeys(p.strip() for p in settings.get("posts", []) if valid_target(p)))
    settings["selected_serials"] = list(dict.fromkeys(s for s in settings.get("selected_serials", []) if s))
    if not settings["posts"]:
        raise ValueError("İzleme listesine geçerli bir Facebook grup/gönderi bağlantısı ekleyin.")
    if not settings["selected_serials"]:
        raise ValueError("En az bir ONLINE telefon seçin.")
    if not settings.get("keywords", "").strip():
        raise ValueError("En az bir anahtar kelime girin.")
    cycle = int(settings.get("cycle_minutes", 16))
    limit = int(settings.get("max_replies_per_visit", 3))
    if not 1 <= cycle <= 1440 or not 1 <= limit <= 50:
        raise ValueError("Periyot 1–1440 dakika, yeni eşleşme sınırı 1–50 olmalı.")
    sequential = settings.get("sequential_enabled", False)
    if not isinstance(sequential, bool):
        raise ValueError("Sıralı dağıtım ayarı açık/kapalı olmalı.")
    settings["reply_delay_seconds"] = int(settings.get("reply_delay_seconds", 10))
    if not 0 <= settings["reply_delay_seconds"] <= 3600:
        raise ValueError("Yanıtlar arası süre 0–3600 saniye olmalı.")
    auto_reply = settings.get("auto_reply_enabled", False)
    if not isinstance(auto_reply, bool):
        raise ValueError("Otomatik yanıt ayarı açık/kapalı olmalı.")
    if auto_reply:
        if not sequential and len(settings["selected_serials"]) != 1:
            raise ValueError("Otomatik yanıt için yalnız bir telefon seçin.")
        if not settings.get("owned_targets_confirmed"):
            raise ValueError("Otomatik yanıt yalnız kendi yönettiğiniz hedeflerde kullanılabilir; sahiplik kutusunu doğrulayın.")
        if not settings.get("reply_template", "").strip():
            raise ValueError("Gönderilecek yanıt metnini girin.")
        if "*" in settings["keywords"]:
            raise ValueError("Otomatik yanıtta * kullanmayın; fiyat/link gibi açık anahtar kelimeler girin.")
        if not sequential and limit > 3:
            raise ValueError("Tek telefonlu eski modda otomatik yanıt sınırı en fazla 3 olabilir.")
        for serial in settings["selected_serials"]:
            name = settings.get("device_metadata", {}).get(serial, {}).get("fb_name", "").strip()
            if not name or re.fullmatch(r"FB\s*Hesap\s*\d+", name, re.I):
                raise ValueError("Filo bölümünde seçili her telefonun gerçek Facebook hesap adını kaydedin; FB Hesap 01 örnek etiketi yeterli değil.")
    settings.update(cycle_minutes=cycle, max_replies_per_visit=limit, auto_reply_enabled=auto_reply, review_only=not auto_reply)
    return settings


def run_16min_keyword_loop(selected_serials_str, metadata=None, run_id=None, once=False):
    global STOP
    STOP = False
    if run_id:
        run = history.get_run(run_id)
        if not run:
            raise ValueError("İzleme oturumu bulunamadı.")
        settings = validate_settings(json.loads(run["settings"]))
    else:
        settings = json.loads(Path(WATCH_FILE).read_text(encoding="utf-8"))
        settings["selected_serials"] = selected_serials_str.split(",")
        if metadata:
            settings["device_metadata"] = metadata.get("devices", {})
        settings = validate_settings(settings)
        run_id = history.create_run(settings)
    sequential_plan = None
    if settings.get("auto_reply_enabled") and settings.get("sequential_enabled"):
        from src import sequential_jobs
        sequential_plan = sequential_jobs.watcher_plan(settings)
        sequential_jobs.acquire(sequential_plan)
        history.interrupt_auto_replies(sequential_jobs.recover(sequential_plan))
        sequential_jobs.update_data(sequential_plan, settings)
    history.update_run(run_id, "RUNNING", ("Sıralı otomatik yanıt başladı." if settings.get("sequential_enabled") else "Tek hesaplı otomatik yanıt başladı.") if settings.get("auto_reply_enabled") else "İzleme başladı. Yalnız okuma; otomatik yanıt yok.", process_id=os.getpid())
    try:
        while not stopping(run_id):
            scan_cycle(run_id, settings)
            if once or stopping(run_id):
                break
            next_check = (datetime.now().astimezone() + timedelta(minutes=settings["cycle_minutes"])).isoformat(timespec="seconds")
            history.update_run(run_id, "WAITING", "Tur tamamlandı; sonraki kontrol bekleniyor.", next_check=next_check)
            if not wait_for(settings["cycle_minutes"] * 60, run_id):
                break
    except Exception as exc:
        history.update_run(run_id, "ERROR", str(exc)[:1500])
        raise
    else:
        history.update_run(run_id, "STOPPED", "Nöbetçi durduruldu. Yanıt denemelerini takip ekranından kontrol edin." if settings.get("auto_reply_enabled") else "İzleme durduruldu. Otomatik yanıt gönderilmedi.")
    finally:
        if sequential_plan is not None:
            sequential_jobs.release(sequential_plan)
    return run_id


def handle_stop(signum, frame):
    global STOP
    STOP = True


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    try:
        run_16min_keyword_loop(sys.argv[1] if len(sys.argv) > 1 else "", run_id=sys.argv[2] if len(sys.argv) > 2 else None)
    except Exception as exc:
        log(f"[NÖBETÇİ HATA] {exc}")
        sys.exit(1)
