import subprocess, time, random, json, os, sys, re, urllib.request
import uiautomator2 as u2
from core_engine import (
    PROF_FILE, load_json, save_json, lock_portrait_mode,
    wake_and_home, home_and_sleep, check_vpn_and_temp, type_text_3tier
)
from keyword_watcher import WATCH_FILE, run_16min_keyword_loop

os.makedirs("downloads", exist_ok=True)
os.makedirs("config", exist_ok=True)

def fetch_from_telegram(tg_url):
    """Telegram gonderisinden urun gorselini indirir, basligi ve icindeki linki alir"""
    print(f"[TELEGRAM] Gonderi ayrıştırılıyor: {tg_url}", flush=True)
    embed_url = tg_url.split("?")[0].rstrip("/") + "?embed=1"
    caption = ""
    extracted_link = ""
    media_local_path = None

    try:
        req = urllib.request.Request(embed_url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", errors="ignore")

        # Basligi ve icindeki href linklerini ayikla
        txt_match = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if txt_match:
            raw_html = txt_match.group(1)
            href_matches = re.findall(r'href="(https?://[^"]+)"', raw_html)
            for hm in href_matches:
                if "t.me/" not in hm:
                    extracted_link = hm
                    break
            raw_html = re.sub(r'<br\s*/?>', '\n', raw_html)
            caption = re.sub(r'<[^>]+>', '', raw_html).strip()

        # Gorsel veya Video indir
        img_match = re.search(r"background-image:url\('(https://[^']+\.jpg)'\)", html)
        vid_match = re.search(r'<video[^>]+src="(https://[^"]+\.mp4)"', html)

        if vid_match:
            m_url = vid_match.group(1)
            media_local_path = os.path.abspath("downloads/tg_post.mp4")
            urllib.request.urlretrieve(m_url, media_local_path)
            print(f"  -> [GORSEL/VIDEO INDIRILDI] {media_local_path}", flush=True)
        elif img_match:
            m_url = img_match.group(1)
            media_local_path = os.path.abspath("downloads/tg_post.jpg")
            urllib.request.urlretrieve(m_url, media_local_path)
            print(f"  -> [URUN GORSELI INDIRILDI] {media_local_path}", flush=True)
    except Exception as e:
        print(f"  -> [!] Telegram ayristirma uyarisi: {str(e)[:40]}", flush=True)

    if extracted_link and extracted_link not in caption:
        caption = f"{caption}\n{extracted_link}".strip()

    if not caption:
        caption = "Firsat urunu stoklarda!"
    print(f"  -> [BASLIK & LINK HAZIR] '{caption[:70]}...'", flush=True)
    return caption, extracted_link, media_local_path

def share_on_fb_group_and_grab_link(ser, node_id, group_url, caption, media_path):
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

    remote_media = None
    if media_path and os.path.exists(media_path):
        ext = os.path.splitext(media_path)[1]
        remote_media = f"/sdcard/DCIM/Camera/autofarm_tg_{int(time.time())}{ext}"
        subprocess.run(f'adb -s {ser} push "{media_path}" "{remote_media}"', shell=True, capture_output=True)
        subprocess.run(f'adb -s {ser} shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://{remote_media}"', shell=True, capture_output=True)
        print(f"  -> [GALERIYE AKTARILDI] [{node_id}] Urun gorseli telefona yuklendi.", flush=True)
        time.sleep(1.5)

    print(f"[GRUP POST PAYLASIMI] [{node_id}] Secili grup aciliyor: {group_url[:48]}...", flush=True)
    subprocess.run(f'adb -s {ser} shell am start -a android.intent.action.VIEW -d "{group_url}" com.facebook.katana', shell=True, capture_output=True)
    time.sleep(random.uniform(6.5, 9.0))

    if d:
        write_box = d(textMatches="(?i).*write something.*|.*bir şeyler yaz.*|.*tartışma başlat.*|.*create a public post.*")
        if not write_box.exists:
            write_box = d(descriptionMatches="(?i).*write something.*|.*bir şeyler yaz.*|.*fotoğraf.*|.*photo.*")

        if write_box.exists:
            wb = write_box[0].info.get("bounds", {})
            subprocess.run(f"adb -s {ser} shell input tap {(wb['left']+wb['right'])//2} {(wb['top']+wb['bottom'])//2}", shell=True, capture_output=True)
            time.sleep(3.0)
        else:
            subprocess.run(f"adb -s {ser} shell input tap {int(W*0.45)} {int(H*0.52)}", shell=True, capture_output=True)
            time.sleep(3.0)

        if remote_media:
            photo_btn = d(textMatches="(?i).*photo/video.*|.*fotoğraf/video.*|.*fotoğraf.*")
            if not photo_btn.exists:
                photo_btn = d(descriptionMatches="(?i).*photo/video.*|.*fotoğraf/video.*")
            if photo_btn.exists:
                pb = photo_btn[0].info.get("bounds", {})
                subprocess.run(f"adb -s {ser} shell input tap {(pb['left']+pb['right'])//2} {(pb['top']+pb['bottom'])//2}", shell=True, capture_output=True)
                time.sleep(2.5)
                subprocess.run(f"adb -s {ser} shell input tap {int(W*0.18)} {int(H*0.28)}", shell=True, capture_output=True)
                time.sleep(1.5)
                next_btn = d(textMatches="(?i)^done$|^bitti$|^next$|^ileri$")
                if next_btn.exists:
                    nb = next_btn[0].info.get("bounds", {})
                    subprocess.run(f"adb -s {ser} shell input tap {(nb['left']+nb['right'])//2} {(nb['top']+nb['bottom'])//2}", shell=True, capture_output=True)
                    time.sleep(2.0)

        edit = d(className="android.widget.EditText")
        if edit.exists:
            eb = edit[0].info.get("bounds", {})
            subprocess.run(f"adb -s {ser} shell input tap {(eb['left']+eb['right'])//2} {(eb['top']+eb['bottom'])//2}", shell=True, capture_output=True)
            time.sleep(1.0)

        type_text_3tier(d, ser, caption)
        time.sleep(1.5)

        post_btn = d(textMatches="(?i)^post$|^paylaş$|^publish$|^yayınla$")
        if not post_btn.exists:
            post_btn = d(descriptionMatches="(?i)^post$|^paylaş$")
        if post_btn.exists:
            p_b = post_btn[0].info.get("bounds", {})
            subprocess.run(f"adb -s {ser} shell input tap {(p_b['left']+p_b['right'])//2} {(p_b['top']+p_b['bottom'])//2}", shell=True, capture_output=True)
        else:
            subprocess.run(f"adb -s {ser} shell input tap {int(W*0.90)} {int(H*0.08)}", shell=True, capture_output=True)

        print(f"  -> [PAYLASILDI] [{node_id}] Urun gorseli ve baslik grupta paylasildi (8 sn bekleniyor)...", flush=True)
        time.sleep(8.0)

        grabbed_link = group_url
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
                    if clip and "facebook.com" in clip:
                        grabbed_link = clip.strip()
                except Exception:
                    pass

        print(f"  -> [LINK ALINDI] Paylasim Linki: {grabbed_link}", flush=True)
        home_and_sleep(ser)
        return grabbed_link

    home_and_sleep(ser)
    return group_url

def run_step6_pipeline(tg_url, groups_raw, prod_title, prod_link, selected_serials_str="ALL", auto_watch="1"):
    subprocess.run("adb reconnect offline", shell=True, capture_output=True)
    out = subprocess.check_output("adb devices", shell=True, text=True).strip().splitlines()[1:]
    online_serials = [l.split()[0] for l in out if len(l.split()) >= 2 and l.split()[1] == "device"]
    if selected_serials_str != "ALL":
        allowed = set(selected_serials_str.split(","))
        online_serials = [s for s in online_serials if s in allowed]

    if not online_serials:
        print("[!] Bagli ONLINE cihaz bulunamadi!", flush=True)
        return

    caption, tg_extracted_link, media_path = fetch_from_telegram(tg_url)
    final_prod_link = prod_link.strip() if prod_link.strip() and "urun-linki.com" not in prod_link else (tg_extracted_link or prod_link)
    if final_prod_link and final_prod_link not in caption:
        caption = f"{caption}\n\n{prod_title}: {final_prod_link}".strip()

    group_list = [g.strip() for g in groups_raw.split(",") if g.strip()]
    new_post_links = []

    print(f"[*] Secilen {len(group_list)} Facebook grubuna sirayla gonderiliyor...", flush=True)
    for idx, g_url in enumerate(group_list):
        pub_ser = online_serials[idx % len(online_serials)]
        node_id = f"NODE-{(idx % len(online_serials)) + 1:02d}"
        vpn_ok, _, _ = check_vpn_and_temp(pub_ser)
        if not vpn_ok:
            print(f"[!] [{node_id}] VPN kapali oldugu icin atlandi!", flush=True)
            home_and_sleep(pub_ser)
            continue

        post_link = share_on_fb_group_and_grab_link(pub_ser, node_id, g_url, caption, media_path)
        new_post_links.append(post_link)
        time.sleep(random.uniform(4.0, 7.5))

    cfg = load_json(WATCH_FILE, {})
    existing_posts = cfg.get("posts", [])
    for pl in new_post_links:
        if pl not in existing_posts:
            existing_posts.insert(0, pl)
    cfg["posts"] = existing_posts
    cfg["keywords"] = "*"
    cfg["reply_template"] = f"{prod_title} -> {final_prod_link}".strip()
    save_json(WATCH_FILE, cfg)

    print("=" * 70, flush=True)
    print(f"[TAMAMLANDI] {len(new_post_links)} gruba post paylasimi yapildi ve linkler panele eklendi!", flush=True)
    print("=" * 70, flush=True)

    if auto_watch == "1" and len(online_serials) > 0:
        other_serials = online_serials[1:] if len(online_serials) > 1 else online_serials
        run_16min_keyword_loop(",".join(other_serials))
    else:
        for s in online_serials:
            home_and_sleep(s)
        print("[UYKU MODU] Hicbir islem kalmadi; tum cihazlarda Facebook/TikTok kapatildi ve ekranlar kapatildi.", flush=True)

if __name__ == "__main__":
    tg_u = sys.argv[1]
    grp_u = sys.argv[2]
    p_title = sys.argv[3]
    p_link = sys.argv[4]
    sels = sys.argv[5] if len(sys.argv) > 5 else "ALL"
    aw = sys.argv[6] if len(sys.argv) > 6 else "1"
    run_step6_pipeline(tg_u, grp_u, p_title, p_link, sels, aw)
