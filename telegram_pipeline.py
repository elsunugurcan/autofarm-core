import subprocess, time, random, json, os, sys
import uiautomator2 as u2
from core_engine import (
    PROF_FILE, load_json, save_json, lock_portrait_mode,
    wake_and_home, home_and_sleep, check_vpn_and_temp, type_text_3tier
)
from src.local_media import prepare_image
from src import operation_timing as timing
from src.photo_post import stage_image, attach_and_publish, post_evidence, adb as photo_adb
import xml.etree.ElementTree as ET
from pathlib import Path
import uuid, shlex
from src.share_history import remember_image, start_share, update_share
from urllib.parse import urlparse, parse_qs

WATCH_FILE = "config/watched_posts.json"

os.makedirs("downloads", exist_ok=True)
os.makedirs("config", exist_ok=True)

def is_post_url(value):
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (host == "facebook.com" or host.endswith(".facebook.com")):
        return False
    return any(part in parsed.path for part in ("/posts/", "/permalink/", "/videos/", "/reel/", "/share/p/")) or bool(set(parse_qs(parsed.query)) & {"story_fbid", "fbid"})


def share_on_fb_group_and_grab_link(ser, node_id, group_url, caption, media_path, on_sending=None, account_name="", timing_settings=None):
    """Indirilen gorseli, basligi ve linki secili Facebook grubunda post olarak paylasir"""
    lock_portrait_mode(ser)
    wake_and_home(ser)
    d = None
    W, H = 720, 1600
    try:
        d = u2.connect(ser)
        W, H = d.info.get("displayWidth", 720), d.info.get("displayHeight", 1600)
        if W > H: W, H = H, W
    except Exception:
        pass

    if d is None:
        home_and_sleep(ser)
        return {"status": "ERROR", "detail": "UIAutomator2 bağlantısı kurulamadı.", "post_url": ""}
    stage = "Görsel aktarımı"
    sending = False
    folder = Path("logs/image_layout") / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    def record(name, xml):
        (folder / f"{name}.xml").write_text(xml, encoding="utf-8")
    def mark_sending():
        nonlocal sending
        sending = True
        if on_sending:
            on_sending()
    try:
        if not media_path or not os.path.isfile(media_path):
            raise ValueError("Seçilen görsel dosyası bulunamadı.")
        image = stage_image(ser, media_path, time.sleep)
        print(f"[GALERİ HAZIR] [{node_id}] Albüm: {image['album']} | Dosya: {image['filename']}", flush=True)
        if timing_settings and timing_settings["prewarm_enabled"]:
            photo_adb(ser, "shell", "monkey", "-p", "com.facebook.katana", "-c", "android.intent.category.LAUNCHER", "1")
            time.sleep(1)
            timing.prewarm(d, timing_settings, time.sleep, lambda text: print(f"[{node_id}] {text}", flush=True))
        stage = "Hedef ve Gallery alanı"
        photo_adb(ser, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(group_url), "com.facebook.katana")
        time.sleep(7)
        stage = "Gallery seçimi ve görsel doğrulaması"
        outcome = attach_and_publish(d, image, caption, time.sleep, record, mark_sending, expected_author=account_name)
        if "onayı bekliyor" in outcome["detail"]:
            home_and_sleep(ser)
            return {"status": "UNVERIFIED", "detail": outcome["detail"], "post_url": ""}
        stage = "Paylaşım sonrası yeniden kontrol"
        photo_adb(ser, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(group_url), "com.facebook.katana")
        time.sleep(5)
        visible = False
        for check in range(3):
            xml = d.dump_hierarchy()
            record(f"post_recheck_{check}", xml)
            if post_evidence(ET.fromstring(xml), caption, account_name):
                visible = True
                break
            if check < 2:
                d.swipe_ext("up", scale=0.5)
                time.sleep(1)
        print(f"[GÖNDERİM DENENDİ] [{node_id}] Görsel eklendi; yayın sonucu henüz bağımsız doğrulanmadı.", flush=True)
    except Exception as exc:
        try:
            record("error", d.dump_hierarchy())
        except Exception:
            pass
        detail = f"{stage}: {exc}. Ekran kayıtları: {folder}"
        print(f"[GÖRSEL PAYLAŞIM HATASI] [{node_id}] {detail}", flush=True)
        home_and_sleep(ser)
        return {"status": "UNVERIFIED" if sending else "ERROR", "detail": detail, "post_url": ""}

    if not visible:
        home_and_sleep(ser)
        return {"status": "UNVERIFIED", "detail": "Gönderim denendi ancak hedef yeniden açıldığında hesap, görsel ve yazı birlikte doğrulanamadı; otomatik tekrar yok.", "post_url": ""}
    if d:
        grabbed_link = ""
        try:
            previous_clipboard = d.clipboard or ""
        except Exception:
            previous_clipboard = ""
        share_btn = d(descriptionMatches="(?i)^share$|^paylaş$|.*share button.*")
        if not share_btn.exists:
            share_btn = d(textMatches="(?i)^share$|^paylaş$")
        if share_btn.exists:
            sb = share_btn[0].info.get("bounds", {})
            subprocess.run(f"adb -s {ser} shell input tap {(sb['left']+sb['right'])//2} {(sb['top']+sb['bottom'])//2}", shell=True, capture_output=True)
            time.sleep(2.5)
            copy_btn = d(textMatches="(?i).*copy link.*|.*bağlantıyı kopyala.*|.*kopyala.*")
            if copy_btn.exists:
                cb = copy_btn[0].info.get("bounds", {})
                subprocess.run(f"adb -s {ser} shell input tap {(cb['left']+cb['right'])//2} {(cb['top']+cb['bottom'])//2}", shell=True, capture_output=True)
                time.sleep(1.5)
                try:
                    clip = d.clipboard
                    if clip and clip.strip() != previous_clipboard.strip() and is_post_url(clip):
                        grabbed_link = clip.strip()
                except Exception:
                    pass

        print(f"  -> [LINK ALINDI] Paylasim Linki: {grabbed_link}", flush=True)
        home_and_sleep(ser)
        return {"status": "VISIBLE" if visible else "LINK_CAPTURED" if grabbed_link else "UNVERIFIED",
                "detail": "Hedef yeniden açıldığında hesap, görsel ve yazı birlikte görüldü; bağımsız sunucu teyidi değildir." if visible else "Gönderim denendi ancak görsel ve yazı yeniden kontrolde birlikte doğrulanamadı; otomatik tekrar yok.", "post_url": grabbed_link}

    home_and_sleep(ser)
    return {"status": "ERROR", "detail": "Paylaşım arayüzüne erişilemedi.", "post_url": ""}

def run_step6_pipeline(image_path, groups_raw, prod_title, prod_link, selected_serials_str="ALL", auto_watch="1", metadata=None):
    # Validate and snapshot the image before touching any connected phone.
    try:
        media_path = prepare_image(image_path)
    except (ValueError, OSError) as exc:
        print(f"[!] Gorsel hazirlanamadi: {exc}", flush=True)
        return
    try:
        info = dict(metadata or {})
        info["image_name"] = os.path.basename(image_path)
        info["history_image"] = remember_image(media_path)
        _run_image_pipeline(media_path, groups_raw, prod_title, "", selected_serials_str, auto_watch, info)
    finally:
        if os.path.isfile(media_path):
            os.remove(media_path)


def _run_image_pipeline(media_path, groups_raw, prod_title, prod_link, selected_serials_str="ALL", auto_watch="1", metadata=None):
    watcher = None
    if auto_watch == "1":
        try:
            from keyword_watcher import run_16min_keyword_loop
            watcher = run_16min_keyword_loop
        except ModuleNotFoundError as exc:
            if exc.name != "keyword_watcher":
                raise
            print("[UYARI] keyword_watcher.py bulunamadi. Gorsel paylasimi yapilacak; yorum nobetcisi baslatilmayacak.", flush=True)
    subprocess.run("adb reconnect offline", shell=True, capture_output=True)
    out = subprocess.check_output("adb devices", shell=True, text=True).strip().splitlines()[1:]
    online_serials = [l.split()[0] for l in out if len(l.split()) >= 2 and l.split()[1] == "device"]
    if selected_serials_str != "ALL":
        allowed = set(selected_serials_str.split(","))
        online_serials = [s for s in online_serials if s in allowed]

    if not online_serials:
        print("[!] Bagli ONLINE cihaz bulunamadi!", flush=True)
        return

    info = metadata or {}
    timing_settings = timing.validate(info["timing"]) if "timing" in info else None
    caption = prod_title.strip()

    group_list = [g.strip() for g in groups_raw.split(",") if g.strip()]
    new_post_links = []

    print(f"[*] Secilen {len(group_list)} Facebook grubuna sirayla gonderiliyor...", flush=True)
    if info.get("publication_plan_id"):
        from src.publication_queue import run as run_plan
        new_post_links = run_plan(sys.modules[__name__], info["publication_plan_id"], media_path)
    else:
        for idx, g_url in enumerate(group_list):
            if idx:
                seconds = timing.delay(timing_settings) if timing_settings else random.uniform(4.0, 7.5)
                print(f"[CİHAZ ARALIĞI] Sonraki görev için {seconds} saniye bekleniyor.", flush=True)
                time.sleep(seconds)
            pub_ser = online_serials[idx % len(online_serials)]
            device = info.get("devices", {}).get(pub_ser, {})
            node_id = device.get("node_id", "Bilinmiyor")
            row_id = start_share(node_id, pub_ser, device.get("fb_name", "Kayıtlı ad yok"),
                                 info.get("targets", {}).get(g_url, g_url), g_url, caption,
                                 info.get("image_name", os.path.basename(media_path)),
                                 info.get("history_image", media_path))
            try:
                vpn_ok, _, _ = check_vpn_and_temp(pub_ser)
                if not vpn_ok:
                    update_share(row_id, "SKIPPED", "VPN kapalı; paylaşım yapılmadı.")
                    print(f"[!] [{node_id}] VPN kapali oldugu icin atlandi!", flush=True)
                    continue
                result = share_on_fb_group_and_grab_link(
                    pub_ser, node_id, g_url, caption, media_path,
                    on_sending=lambda: update_share(row_id, "SENDING"), account_name=device.get("fb_name", ""), timing_settings=timing_settings)
                update_share(row_id, result["status"], result["detail"], result["post_url"])
                if result["post_url"]:
                    new_post_links.append(result["post_url"])
            except Exception as exc:
                update_share(row_id, "ERROR", str(exc))
                print(f"[HATA] [{node_id}] {exc}", flush=True)
            finally:
                home_and_sleep(pub_ser)


    cfg = load_json(WATCH_FILE, {})
    existing_posts = cfg.get("posts", [])
    for pl in new_post_links:
        if pl not in existing_posts:
            existing_posts.insert(0, pl)
    cfg["posts"] = existing_posts
    cfg.setdefault("keywords", "fiyat, link, bilgi")
    cfg.setdefault("reply_template", caption)
    save_json(WATCH_FILE, cfg)

    print("=" * 70, flush=True)
    print(f"[TAMAMLANDI] {len(group_list)} hedefin islenmesi bitti; {len(new_post_links)} gonderi baglantisi alindi. Sonuclar Paylasim Gecmisinde.", flush=True)
    print("=" * 70, flush=True)

    if watcher is not None and new_post_links and len(online_serials) > 0:
        other_serials = online_serials[1:] if len(online_serials) > 1 else online_serials
        try:
            watcher(",".join(other_serials), metadata=info)
        finally:
            for s in online_serials:
                home_and_sleep(s)
    else:
        if watcher is not None and not new_post_links:
            print("[NÖBETÇİ BAŞLATILMADI] Yeni gönderi bağlantısı alınmadı; eski gönderiler için izleme başlatılmadı.", flush=True)
        for s in online_serials:
            home_and_sleep(s)
        print("[UYKU MODU] Hicbir islem kalmadi; tum cihazlarda Facebook/TikTok kapatildi ve ekranlar kapatildi.", flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Kullanim: telegram_pipeline.py GORSEL_DOSYASI HEDEFLER BASLIK URUN_LINKI [CIHAZLAR] [NOBETCI]", flush=True)
        sys.exit(2)
    image_path = sys.argv[1]
    grp_u = sys.argv[2]
    p_title = sys.argv[3]
    p_link = sys.argv[4]
    sels = sys.argv[5] if len(sys.argv) > 5 else "ALL"
    aw = sys.argv[6] if len(sys.argv) > 6 else "1"
    metadata = json.loads(sys.argv[7]) if len(sys.argv) > 7 else {}
    run_step6_pipeline(image_path, grp_u, p_title, "", sels, aw, metadata)
