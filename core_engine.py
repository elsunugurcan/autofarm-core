import subprocess, threading, time, random, json, os, sys, sqlite3
import uiautomator2 as u2
from src.recovery_policy import FREEZE_STEP_LIMIT, FreezeTracker
from src.campaign_comment import post_comment
from src.facebook_navigation import clean_post_url
from src.delivery_check import recheck_comment
from src.report_flow import complete_report
from src import operation_timing as timing
import uuid
import shlex
from pathlib import Path

os.makedirs("config", exist_ok=True)
os.makedirs("kanitlar", exist_ok=True)
os.makedirs("downloads", exist_ok=True)

PROF_FILE = "config/fleet_profiles.json"
FRIEND_LOG_FILE = "config/friend_requests_log.json"
GROUPS_FILE = "config/saved_groups.json"
PAGES_FILE = "config/saved_pages.json"
DB_FILE = "autofarm.db"

PERSONAS = ["Gece_Kusu_Analist", "Yavas_Geleneksel", "Dikkatli_Okuyucu", "Sabirsiz_Genclik"]

def init_db():
    db = sqlite3.connect(DB_FILE)
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS campaign_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camp_code TEXT,
        node_id TEXT,
        serial TEXT,
        fb_name TEXT,
        persona TEXT,
        task_type TEXT,
        target_url TEXT,
        comment_text TEXT,
        delay_sec INTEGER,
        status TEXT
    )""")
    db.commit()
    db.close()

init_db()

def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, "r", encoding="utf-8"))
        except Exception:
            pass
    return default

def save_json(path, data):
    json.dump(data, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

def lock_portrait_mode(ser):
    """Telefonun ekranini surekli dikey (Portrait) modda kalacak sekilde kilitler"""
    subprocess.run(f"adb -s {ser} shell settings put system accelerometer_rotation 0", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell settings put system user_rotation 0", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell content insert --uri content://settings/system --bind name:s:accelerometer_rotation --bind value:i:0", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell wm user-rotation lock 0", shell=True, capture_output=True)
    # Android 15 can honor app-requested landscape even when auto-rotate is off.
    # These commands are supported by the test phone's wm help; older devices
    # can reject them while the basic lock remains in place.
    for command in (("fixed-to-user-rotation", "enabled"), ("set-ignore-orientation-request", "true")):
        try:
            subprocess.run(["adb", "-s", ser, "shell", "wm", *command], capture_output=True, timeout=6)
        except (OSError, subprocess.TimeoutExpired):
            pass

def mute_device_audio(ser):
    for st in [3, 2, 5, 4, 1]:
        subprocess.run(f"adb -s {ser} shell media volume --show --stream {st} --set 0", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell cmd audio set-ringer-mode SILENT", shell=True, capture_output=True)

def wake_and_home(ser):
    """Ekrani uyandirir, dikey moda kilitler, sesi kapatir ve anasayfaya doner"""
    lock_portrait_mode(ser)
    subprocess.run(f"adb -s {ser} shell input keyevent 224", shell=True, capture_output=True)
    time.sleep(0.3)
    subprocess.run(f"adb -s {ser} shell wm dismiss-keyguard", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell input keyevent 82", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell input swipe 360 1280 360 320 220", shell=True, capture_output=True)
    time.sleep(0.3)
    subprocess.run(f"adb -s {ser} shell input keyevent 3", shell=True, capture_output=True)
    mute_device_audio(ser)

def home_and_sleep(ser):
    """Islem kalmadiginda arka planda Facebook ve TikTok'u kapatir, anasayfaya donup ekrani kapatir"""
    lock_portrait_mode(ser)
    subprocess.run(f"adb -s {ser} shell am force-stop com.facebook.katana", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell am force-stop com.zhiliaoapp.musically", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell am force-stop com.ss.android.ugc.trill", shell=True, capture_output=True)
    time.sleep(0.3)
    subprocess.run(f"adb -s {ser} shell input keyevent 3", shell=True, capture_output=True)
    time.sleep(0.4)
    subprocess.run(f"adb -s {ser} shell input keyevent 223", shell=True, capture_output=True)

def check_vpn_and_temp(ser):
    vpn_out = subprocess.run(f"adb -s {ser} shell ip addr show tun0", shell=True, capture_output=True, text=True).stdout
    vpn_ok = "inet " in vpn_out
    batt_out = subprocess.run(f"adb -s {ser} shell dumpsys battery", shell=True, capture_output=True, text=True).stdout
    temp = 30.0
    level = 100
    for line in batt_out.splitlines():
        if "temperature:" in line:
            try: temp = int(line.split(":")[1].strip()) / 10.0
            except: pass
        elif "level:" in line:
            try: level = int(line.split(":")[1].strip())
            except: pass
    return vpn_ok, level, temp

def force_restart_fb(ser, node_id, reason):
    print(f"[KURTARICI] [{node_id}] {reason} -> Facebook kapatilip yeniden baslatiliyor...", flush=True)
    lock_portrait_mode(ser)
    subprocess.run(f"adb -s {ser} shell am force-stop com.facebook.katana", shell=True, capture_output=True)
    time.sleep(2.0)
    subprocess.run(f"adb -s {ser} shell input keyevent 3", shell=True, capture_output=True)
    time.sleep(1.2)
    subprocess.run(f"adb -s {ser} shell monkey -p com.facebook.katana -c android.intent.category.LAUNCHER 1", shell=True, capture_output=True)
    time.sleep(random.uniform(6.0, 8.5))

def type_text_3tier(d, ser, text):
    if d:
        try:
            d.set_input_ime(True)
            time.sleep(0.4)
            d.send_keys(text, clear=False)
            time.sleep(0.5)
            d.set_input_ime(False)
            return True
        except Exception:
            pass
    if d:
        try:
            edit = d(className="android.widget.EditText")
            if edit.exists:
                edit[0].set_text(text)
                time.sleep(0.5)
                return True
        except Exception:
            pass
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    clean_text = text.translate(tr_map)
    for ch in clean_text:
        if ch == " ":
            subprocess.run(f"adb -s {ser} shell input keyevent 62", shell=True, capture_output=True)
        elif ch in "#@!?.:-_0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ":
            subprocess.run(f'adb -s {ser} shell input text "{ch}"', shell=True, capture_output=True)
        time.sleep(random.uniform(0.05, 0.14))
    return True

def smart_scroll_and_center(d, ser, W=720, H=1600):
    """
    1) Once dogal bir ana kaydirma ile sonraki gonderiye gecer.
    2) Ardindan ekrandaki gonderinin Begen/Yorum barini ve basligini tespit edip
       fark varsa mikro-kaydirma ile gonderiyi tam ekranin ortasina hizalar.
    """
    # 1. Ana Biyometrik Kaydirma
    x1 = random.randint(int(W * 0.38), int(W * 0.62))
    y1 = random.randint(int(H * 0.72), int(H * 0.80))
    x2 = x1 + random.randint(-28, 28)
    y2 = random.randint(int(H * 0.24), int(H * 0.32))
    subprocess.run(f"adb -s {ser} shell input swipe {x1} {y1} {x2} {y2} {random.randint(280, 460)}", shell=True, capture_output=True)
    time.sleep(random.uniform(0.55, 0.85))

    if not d:
        return

    # 2. Gonderinin Ekrandaki Konumunu Oku ve Tam Ortala
    try:
        like_btns = d(descriptionMatches="(?i)^like$|^beğen$|.*like button.*|.*beğen düğmesi.*")
        if not like_btns.exists:
            like_btns = d(textMatches="(?i)^like$|^beğen$")

        if like_btns.exists:
            # Ekranda gorunur olan gonderi alt barlarindan orta-alt bolgeye en yakin olani sec
            aday_y_listesi = []
            for btn in like_btns:
                b = btn.info.get("bounds", {})
                if b:
                    cy = (b.get("top", 0) + b.get("bottom", 0)) // 2
                    if int(H * 0.15) < cy < int(H * 0.94):
                        aday_y_listesi.append(cy)

            if aday_y_listesi:
                # Bir gonderinin tam ortada durmasi icin altindaki Begen/Yorum barinin
                # ekranin %70-%73 yuksekliginde (ustteki gorsel/videonun ise %25-%70 arasinda) olmasi gerekir.
                ideal_alt_bar_y = int(H * 0.71)
                mevcut_y = min(aday_y_listesi, key=lambda y: abs(y - ideal_alt_bar_y))
                fark_y = mevcut_y - ideal_alt_bar_y

                # Eger gonderi ideal merkezden 65 pikselden fazla asagida veya yukarida kalmissa mikro-hizalama yap
                if abs(fark_y) > 65:
                    kaydirma_miktari = max(-int(H * 0.38), min(int(H * 0.38), int(fark_y * 0.92)))
                    mx1 = random.randint(int(W * 0.42), int(W * 0.58))
                    my1 = int(H * 0.55)
                    mx2 = mx1 + random.randint(-12, 12)
                    my2 = max(int(H * 0.15), min(int(H * 0.85), my1 - kaydirma_miktari))
                    sure_ms = random.randint(210, 330)
                    subprocess.run(f"adb -s {ser} shell input swipe {mx1} {my1} {mx2} {my2} {sure_ms}", shell=True, capture_output=True)
                    time.sleep(0.35)
    except Exception:
        pass

def organic_sandwich_scroll(d, ser, node_id, seconds=10):
    print(f"  [SANDVIC] [{node_id}] {seconds} sn dogal akis gezinmesi yapiliyor...", flush=True)
    end_t = time.time() + seconds
    while time.time() < end_t:
        smart_scroll_and_center(d, ser, 720, 1600)
        time.sleep(random.uniform(3.0, 5.5))

def update_queue_status(row_id, new_status):
    if not row_id:
        return
    try:
        db = sqlite3.connect(DB_FILE)
        c = db.cursor()
        c.execute("UPDATE campaign_queue SET status=? WHERE id=?", (new_status, row_id))
        db.commit()
        db.close()
    except Exception:
        pass

def natural_report_target(d, ser, node_id, url, reason_keyword, W, H):
    """Kisi, grup veya sayfa linkini dogal yollardan sikayet eder"""
    if d is None or d.app_current().get("package") != "com.facebook.katana":
        return "[SIKAYET GONDERILMEDI] Facebook ön planda değil veya arayüze erişilemedi."
    print(f"  -> [SIKAYET] [{node_id}] Hedef dogal olarak inceleniyor: {url[:45]}...", flush=True)
    # 1. Once sayfada biraz asagi yukari dogal gezin
    subprocess.run(f"adb -s {ser} shell input swipe 360 1050 360 550 350", shell=True, capture_output=True)
    time.sleep(random.uniform(2.0, 3.5))
    subprocess.run(f"adb -s {ser} shell input swipe 360 550 360 1050 350", shell=True, capture_output=True)
    time.sleep(random.uniform(1.5, 2.5))

    # 2. Üç nokta (More / Diğer / Seçenekler) butonunu bul ve tikla
    more_clicked = False
    if d:
        more_btn = d(descriptionMatches="(?i).*more.*|.*diğer.*|.*seçenekler.*|.*options.*|.*menu.*|.*profil ayarları.*")
        if more_btn.exists:
            mb = more_btn[0].info.get("bounds", {})
            if mb:
                subprocess.run(f"adb -s {ser} shell input tap {(mb['left']+mb['right'])//2} {(mb['top']+mb['bottom'])//2}", shell=True, capture_output=True)
                more_clicked = True
                time.sleep(2.5)

    if not more_clicked:
        return "[SIKAYET GONDERILMEDI] Hedefin seçenekler menüsü bulunamadı; rastgele alana tıklanmadı."

    # 3. 'Şikayet Et' / 'Destek bul veya şikayet et' / 'Find support or report' secenegini tikla
    report_clicked = False
    if d:
        rep_btn = d(textMatches="(?i).*report.*|.*şikayet.*|.*destek bul.*|.*find support.*")
        if not rep_btn.exists:
            rep_btn = d(descriptionMatches="(?i).*report.*|.*şikayet.*|.*destek bul.*")
        if rep_btn.exists:
            rb = rep_btn[0].info.get("bounds", {})
            subprocess.run(f"adb -s {ser} shell input tap {(rb['left']+rb['right'])//2} {(rb['top']+rb['bottom'])//2}", shell=True, capture_output=True)
            report_clicked = True
            time.sleep(3.0)

    if not report_clicked:
        return "[SIKAYET GONDERILMEDI] Şikayet menüsü bulunamadı; rastgele alana tıklanmadı."

    folder = Path("logs/report_layout") / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    def record(stage, xml):
        (folder / f"{stage}.xml").write_text(xml, encoding="utf-8")
    try:
        result = complete_report(d, reason_keyword.upper(), time.sleep, record)
    except Exception as exc:
        result = f"[SIKAYET BELIRSIZ] {exc}; alındı onayı yok. Otomatik tekrar yok."
    print(f"[ŞİKAYET SONUCU] [{node_id}] {result} | Ekran kayıtları: {folder}", flush=True)
    return result


def worker_warmup(idx, ser, duration_min, like_prob):
    try:
        node_id = f"NODE-{idx:02d}"
        time.sleep((idx - 1) * 1.1)

        vpn_ok, level, temp = check_vpn_and_temp(ser)
        if not vpn_ok:
            print(f"[!] [{node_id} | {ser}] VPN (tun0) KAPALI! Isitma iptal edildi.", flush=True)
            return
        if temp >= 42.5:
            print(f"[KALKAN] [{node_id}] Sicaklik {temp}C! Cihaz dinlenmeye alindi.", flush=True)
            return

        wake_and_home(ser)
        d = None
        W, H = 720, 1600
        try:
            d = u2.connect(ser)
            W, H = d.info.get("displayWidth", 720), d.info.get("displayHeight", 1600)
            if W > H: W, H = H, W
        except Exception:
            pass

        print(f"[ISITMA BASLADI] [{node_id} | {ser}] FB Aciliyor | Sure: {duration_min} dk | Pil: %{level} ({temp}C)", flush=True)
        subprocess.run(f"adb -s {ser} shell monkey -p com.facebook.katana -c android.intent.category.LAUNCHER 1", shell=True, capture_output=True)
        time.sleep(random.uniform(6.0, 8.5))

        end_time = time.time() + (duration_min * 60)
        freeze_tracker = FreezeTracker()
        step = 0

        while time.time() < end_time:
            step += 1
            try:
                lock_portrait_mode(ser)
                vpn_ok, level, temp = check_vpn_and_temp(ser)
                if not vpn_ok:
                    print(f"[ACIL DURDURMA] [{node_id}] VPN koptu! Uygulamalar kapatiliyor...", flush=True)
                    break
                if temp >= 43.0:
                    print(f"[SICAKLIK KALKANI] [{node_id}] Cihaz {temp}C ulasti, sogumaya aliniyor...", flush=True)
                    break

                win_out = subprocess.run(f"adb -s {ser} shell dumpsys window displays", shell=True, capture_output=True, text=True).stdout
                if "com.facebook.katana" not in win_out:
                    freeze_tracker.reset()
                    force_restart_fb(ser, node_id, "Facebook kapandi veya arka plana dustu")
                    continue

                if d:
                    if d(textMatches="(?i).*no internet.*|.*connection lost.*|.*bağlantı yok.*|.*tekrar dene.*|.*try again.*|.*isn't responding.*|.*yanıt vermiyor.*").exists:
                        freeze_tracker.reset()
                        force_restart_fb(ser, node_id, "Internet cekmemesi veya ANR uyarisi")
                        continue

                    if freeze_tracker.observe(d.dump_hierarchy()):
                        freeze_tracker.reset()
                        force_restart_fb(ser, node_id, f"Ekran donmasi ({FREEZE_STEP_LIMIT} degismeyen kontrol)")
                        continue

                wait_s = round(random.uniform(3.0, 5.5), 1) if random.random() < 0.3 else round(random.uniform(6.5, 14.5), 1)
                print(f"[{node_id}] Isitma Adim #{step} | Izleme: {wait_s} sn | Sicaklik: {temp}C", flush=True)
                time.sleep(wait_s)

                if d and wait_s > 6.0 and (random.random() * 100) < like_prob:
                    like_btn = d(descriptionMatches="(?i)^like$|^beğen$|.*like button.*|.*beğen düğmesi.*")
                    if like_btn.exists:
                        b = like_btn[0].info.get("bounds", {})
                        if b and b.get("top", 0) > int(H * 0.18) and b.get("bottom", H) < int(H * 0.85):
                            lx, ly = (b["left"] + b["right"]) // 2, (b["top"] + b["bottom"]) // 2
                            subprocess.run(f"adb -s {ser} shell input tap {lx} {ly}", shell=True, capture_output=True)
                            print(f"  -> [LIKE] [{node_id}] Akista gonderi begenildi ({lx}, {ly})", flush=True)
                            time.sleep(1.5)

                smart_scroll_and_center(d, ser, W, H)

            except Exception as e:
                freeze_tracker.reset()
                force_restart_fb(ser, node_id, f"UI Yanit Hatasi ({str(e)[:25]})")

        print(f"[ISITMA BITTI] [{node_id}] Facebook & TikTok kapatilip ekran uyku moduna aliniyor...", flush=True)
    finally:
        home_and_sleep(ser)

def execute_queue_tasks(sandwich_enabled=True, campaign_code=None):
    used_serials = set()
    try:
        db = sqlite3.connect(DB_FILE)
        c = db.cursor()
        query = "SELECT id, camp_code, node_id, serial, fb_name, persona, task_type, target_url, comment_text, delay_sec FROM campaign_queue WHERE status LIKE '%PENDING%'"
        if campaign_code:
            rows = c.execute(query + " AND camp_code=? ORDER BY id ASC", (campaign_code,)).fetchall()
        else:
            rows = c.execute(query + " ORDER BY id ASC").fetchall()
        db.close()

        if not rows:
            print("[BILGI] Kuyrukta bekleyen [PENDING] gorev bulunmuyor.", flush=True)
            return

        print(f"[*] DRIP-FEED MOTORU BASLATILDI: Kuyrukta {len(rows)} gorev islenecek...", flush=True)
        f_log = load_json(FRIEND_LOG_FILE, {})
        used_serials = set()

        for job_index, r in enumerate(rows):
            row_id, camp_code, node_id, ser, fb_name, persona, task_type, url, comment_txt, delay_s = r
            if job_index and delay_s > 0:
                print(f"[CİHAZ ARALIĞI] {delay_s} saniye bekleniyor.", flush=True)
                time.sleep(delay_s)
            used_serials.add(ser)

            vpn_ok, level, temp = check_vpn_and_temp(ser)
            if not vpn_ok:
                print(f"[!] [{node_id} | {fb_name}] VPN KAPALI! Gorev #{row_id} atlandi.", flush=True)
                update_queue_status(row_id, "[VPN KAPALI]")
                home_and_sleep(ser)
                continue

            update_queue_status(row_id, f"[CALISIYOR] {comment_txt}")
            wake_and_home(ser)

            d = None
            W, H = 720, 1600
            try:
                d = u2.connect(ser)
                W, H = d.info.get("displayWidth", 720), d.info.get("displayHeight", 1600)
                if W > H: W, H = H, W
            except Exception:
                pass

            options = timing.campaign_settings(DB_FILE, camp_code)
            if options is None:
                options = timing.validate({"prewarm_enabled": sandwich_enabled, "like_percent": 0})
            if options["prewarm_enabled"]:
                subprocess.run(["adb", "-s", ser, "shell", "monkey", "-p", "com.facebook.katana", "-c", "android.intent.category.LAUNCHER", "1"], capture_output=True)
                time.sleep(1)
                timing.prewarm(d, options, time.sleep, lambda text: print(f"[{node_id}] {text}", flush=True))

            print(f"[GOREV #{row_id}] [{node_id} | {fb_name}] -> {task_type} aciliyor...", flush=True)
            subprocess.run(["adb", "-s", ser, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(clean_post_url(url)), "com.facebook.katana"], capture_output=True)
            time.sleep(random.uniform(6.0, 8.5))

            # 1) SAYILI YORUM + BEGENI
            if "YORUM" in task_type or "BEGENI" in task_type:
                if "BEGENI" in task_type:
                    liked = False
                    if d:
                        like_btn = d(descriptionMatches="(?i)^like$|^beğen$|.*like button.*|.*beğen düğmesi.*")
                        if not like_btn.exists:
                            like_btn = d(textMatches="(?i)^like$|^beğen$")
                        if like_btn.exists:
                            b = like_btn[0].info.get("bounds", {})
                            subprocess.run(f"adb -s {ser} shell input tap {(b['left']+b['right'])//2} {(b['top']+b['bottom'])//2}", shell=True, capture_output=True)
                            liked = True
                            print(f"  -> [LIKE] [{node_id}] Begeni atildi.", flush=True)
                    if not liked:
                        subprocess.run(f"adb -s {ser} shell input tap 360 750", shell=True, capture_output=True)
                        time.sleep(0.12)
                        subprocess.run(f"adb -s {ser} shell input tap 360 750", shell=True, capture_output=True)

                    time.sleep(2.0)

                if "YORUM" in task_type:
                    diagnostic_dir = Path("logs/campaign_layout")
                    diagnostic_dir.mkdir(parents=True, exist_ok=True)
                    def diagnostic(stage, xml):
                        (diagnostic_dir / f"task_{row_id}_{stage}.xml").write_text(xml, encoding="utf-8")
                    def reopen_target():
                        subprocess.run(["adb", "-s", ser, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(clean_post_url(url)), "com.facebook.katana"], capture_output=True, timeout=20)
                        time.sleep(5)
                        return d.app_current().get("package") == "com.facebook.katana"
                    def verify_delivery():
                        return recheck_comment(d, fb_name, comment_txt, reopen_target, time.sleep, record=diagnostic)
                    result = post_comment(d, comment_txt, lambda: lock_portrait_mode(ser), time.sleep, diagnostic, recheck=verify_delivery)
                    update_queue_status(row_id, result)
                    print(f"  -> [{node_id}] {result}", flush=True)
                else:
                    update_queue_status(row_id, "[BEGENI DENENDI] Yayın durumu Facebook'tan kontrol edilmeli.")

            # 2) GRUBA KATILMA
            elif "GRUP" in task_type:
                joined = False
                if d:
                    j_btn = d(textMatches="(?i)^join group$|^gruba katıl$|^katıl$|^join$")
                    if not j_btn.exists:
                        j_btn = d(descriptionMatches="(?i).*join group.*|.*gruba katıl.*|.*katıl.*")
                    if j_btn.exists:
                        jb = j_btn[0].info.get("bounds", {})
                        subprocess.run(f"adb -s {ser} shell input tap {(jb['left']+jb['right'])//2} {(jb['top']+jb['bottom'])//2}", shell=True, capture_output=True)
                        joined = True
                update_queue_status(row_id, "[KATILDI]" if joined else "[ZATEN UYE]")

            # 3) KISI EKLEME (HATA KORUMALI)
            elif "KISI" in task_type:
                if url not in f_log:
                    f_log[url] = {}
                prev = f_log[url].get(ser)
                if prev in ["ADDED", "ERROR_BLOCKED"]:
                    update_queue_status(row_id, f"[ATLANDI - {prev}]")
                    home_and_sleep(ser)
                    continue
                if d:
                    a_btn = d(textMatches="(?i)^add friend$|^arkadaş ekle$|^ekle$")
                    if not a_btn.exists:
                        a_btn = d(descriptionMatches="(?i).*add friend.*|.*arkadaş ekle.*")
                    if a_btn.exists:
                        ab = a_btn[0].info.get("bounds", {})
                        subprocess.run(f"adb -s {ser} shell input tap {(ab['left']+ab['right'])//2} {(ab['top']+ab['bottom'])//2}", shell=True, capture_output=True)
                        time.sleep(2.0)
                        if d(textMatches="(?i).*can't send.*|.*gönderilemiyor.*|.*hata.*|.*error.*").exists:
                            f_log[url][ser] = "ERROR_BLOCKED"
                            update_queue_status(row_id, "[HATA KORUMASI - Kara Listede]")
                        else:
                            f_log[url][ser] = "ADDED"
                            update_queue_status(row_id, "[ISTEK GONDERILDI]")
                    else:
                        f_log[url][ser] = "ERROR_BLOCKED"
                        update_queue_status(row_id, "[BUTON KAPALI / EKLI]")
                    save_json(FRIEND_LOG_FILE, f_log)

            # 4) DOGAL SIKAYET ETME (KISI / GRUP / SAYFA)
            elif "SIKAYET" in task_type:
                result = natural_report_target(d, ser, node_id, url, comment_txt, W, H)
                update_queue_status(row_id, result)

            # 5) SAYFA BEGEN & TAKIP ET / ETKILESIM
            elif "SAYFA" in task_type:
                followed = False
                if d:
                    f_btn = d(textMatches="(?i)^like$|^beğen$|^follow$|^takip et$")
                    if not f_btn.exists:
                        f_btn = d(descriptionMatches="(?i)^like$|^beğen$|^follow$|^takip et$")
                    if f_btn.exists:
                        fb_b = f_btn[0].info.get("bounds", {})
                        subprocess.run(f"adb -s {ser} shell input tap {(fb_b['left']+fb_b['right'])//2} {(fb_b['top']+fb_b['bottom'])//2}", shell=True, capture_output=True)
                        followed = True
                        time.sleep(2.0)
                # Sayfada biraz asagi kaydirip son gonderiyi begen
                subprocess.run(f"adb -s {ser} shell input swipe 360 1150 360 450 350", shell=True, capture_output=True)
                time.sleep(2.5)
                if d:
                    l_btn = d(descriptionMatches="(?i)^like$|^beğen$|.*like button.*")
                    if l_btn.exists:
                        lb = l_btn[0].info.get("bounds", {})
                        subprocess.run(f"adb -s {ser} shell input tap {(lb['left']+lb['right'])//2} {(lb['top']+lb['bottom'])//2}", shell=True, capture_output=True)
                update_queue_status(row_id, "[SAYFA TAKIP & BEGENI OK]" if followed else "[SAYFA INCELENDI]")

            time.sleep(1.5)
            # Islem bittigi an cihazin FB/TikTok uygulamasini kapat ve ekrani uyut
            home_and_sleep(ser)


        for s in used_serials:
            home_and_sleep(s)
        print("[KUYRUK BITTI] Gorev sonuclari kuyrukta; yorumun yayinlandigi varsayilmaz. Cihazlara kapatma ve uyku komutlari gonderildi.", flush=True)
    finally:
        for serial in used_serials:
            try:
                home_and_sleep(serial)
            except Exception as exc:
                print(f"[KAPATMA HATASI] {serial}: {exc}", flush=True)

if __name__ == "__main__":
    cmd_type = sys.argv[1] if len(sys.argv) > 1 else "warmup"
    if cmd_type == "warmup":
        dur = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        l_prob = int(sys.argv[3]) if len(sys.argv) > 3 else 15
        targets_arg = sys.argv[4] if len(sys.argv) > 4 else "ALL"
        subprocess.run("adb reconnect offline", shell=True, capture_output=True)
        out = subprocess.check_output("adb devices", shell=True, text=True).strip().splitlines()[1:]
        all_s = [l.split()[0] for l in out if len(l.split()) >= 2 and l.split()[1] == "device"]
        chosen = all_s if targets_arg == "ALL" else [s for s in all_s if s in targets_arg.split(",")]
        threads = [threading.Thread(target=worker_warmup, args=(i, s, dur, l_prob), daemon=True) for i, s in enumerate(chosen, 1)]
        for t in threads: t.start()
        for t in threads:
            while t.is_alive(): t.join(0.5)
    elif cmd_type == "run_queue":
        sw = (sys.argv[2] == "1") if len(sys.argv) > 2 else True
        code = sys.argv[3] if len(sys.argv) > 3 else None
        execute_queue_tasks(sandwich_enabled=sw, campaign_code=code)
