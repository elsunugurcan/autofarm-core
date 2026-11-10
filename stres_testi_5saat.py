import subprocess, threading, time, random, json, os, sys
from datetime import datetime
from src.recovery_policy import FREEZE_STEP_LIMIT, FreezeTracker
import uiautomator2 as u2
from PIL import Image, ImageStat, ImageChops

from core_engine import (
    PROF_FILE, load_json, mute_device_audio,
    wake_and_home, home_and_sleep, check_vpn_and_temp, force_restart_fb
)

SURE_DAKIKA = 300  # 5 Saat (300 Dakika)
RAPOR_DOSYASI = "TEST_VE_IYILESTIRME_RAPORU.md"
LOG_DOSYASI = "5saat_test_detay.log"
HATA_KLASORU = "hata_ekranlari"
os.makedirs(HATA_KLASORU, exist_ok=True)

lock = threading.Lock()
baslangic_ts = time.time()
baslangic_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

stats = {}
inceleme_kayitlari = []
iyilestirme_notlari = set()

def log_yaz(mesaj, seviye="INFO"):
    zaman = datetime.now().strftime("%H:%M:%S")
    satir = f"[{zaman}] [{seviye}] {mesaj}"
    print(satir, flush=True)
    with lock:
        with open(LOG_DOSYASI, "a", encoding="utf-8") as f:
            f.write(satir + "\n")

def ekran_goruntusu_al_ve_incele(d, ser, node_id, sebep_etiketi, onceki_gorsel_yolu=None):
    """
    Takilma/hata aninda ekran goruntusu alir, goruntuyu piksel ve XML duzeyinde inceler,
    teshis koyar ve rapora kanit olarak ekler.
    """
    zaman_damgasi = datetime.now().strftime("%H%M%S")
    temiz_etiket = "".join(c if c.isalnum() else "_" for c in sebep_etiketi)[:25]
    dosya_yolu = f"{HATA_KLASORU}/{node_id}_{ser}_{zaman_damgasi}_{temiz_etiket}.png"

    # 1. Ekran goruntusunu cek (Once u2, basarisiz olursa dogrudan ADB screencap)
    cekildi = False
    if d:
        try:
            d.screenshot(dosya_yolu)
            cekildi = os.path.exists(dosya_yolu)
        except Exception:
            cekildi = False

    if not cekildi:
        subprocess.run(f'adb -s {ser} exec-out screencap -p > "{dosya_yolu}"', shell=True, capture_output=True)
        cekildi = os.path.exists(dosya_yolu) and os.path.getsize(dosya_yolu) > 1000

    # 2. Goruntu Piksel Incelemesi (Siyah ekran / Beyaz yukleme ekrani / Donmus kare tespiti)
    gorsel_teshis = "Standart UI Görünümü"
    benzerlik_orani = 0.0

    if cekildi:
        try:
            img = Image.open(dosya_yolu).convert("RGB")
            stat = ImageStat.Stat(img)
            ort_parlaklik = sum(stat.mean) / 3.0
            std_sapma = sum(stat.stddev) / 3.0

            if ort_parlaklik < 15.0:
                gorsel_teshis = "SİYAH EKRAN (Ekran uyanmamış veya Facebook siyah ekranda çakılmış)"
                with lock:
                    iyilestirme_notlari.add(f"{node_id}: Siyah ekran takılması tespit edildi; WAKEUP (224) komutu sonrası 0.8 sn ek bekleme ve grafik önbellek temizliği önerilir.")
            elif ort_parlaklik > 240.0 and std_sapma < 12.0:
                gorsel_teshis = "BEYAZ EKRAN TAKILMASI (Sayfa yüklenemiyor / Proxy yavaşlığı)"
                with lock:
                    iyilestirme_notlari.add(f"{node_id}: Beyaz yükleme ekranında takılma görüldü; cihazın SOCKS5 proxy yanıt süresi kontrol edilmeli.")
            elif std_sapma < 8.0:
                gorsel_teshis = "TEK RENK / BOŞ EKRAN ASILI KALMASI"

            # Onceki ekran goruntusu ile piksel karsilastirmasi yap
            if onceki_gorsel_yolu and os.path.exists(onceki_gorsel_yolu):
                prev_img = Image.open(onceki_gorsel_yolu).convert("RGB").resize(img.size)
                diff = ImageChops.difference(img, prev_img)
                diff_stat = ImageStat.Stat(diff)
                fark_ort = sum(diff_stat.mean) / 3.0
                if fark_ort < 2.0:
                    gorsel_teshis = f"GÖRSEL DONMA (Önceki kare ile %99.5 aynı - Kaydırma işlemiyor)"
        except Exception as e:
            gorsel_teshis = f"Görsel okuma uyarısı ({str(e)[:25]})"

    # 3. Ekrandaki Metinleri (XML) Oku ve Sorunu Teshis Et
    ekran_yazilari = []
    xml_teshis = "Genel Akış Takılması"
    if d:
        try:
            for tv in d(className="android.widget.TextView"):
                t = (tv.info.get("text") or "").strip()
                if len(t) > 2 and len(ekran_yazilari) < 8:
                    ekran_yazilari.append(t[:40])
        except Exception:
            pass

    birlesik_metin = " | ".join(ekran_yazilari).lower()
    if any(k in birlesik_metin for k in ["no internet", "bağlantı yok", "connection", "tekrar dene", "try again"]):
        xml_teshis = "İNTERNET / PROXY KOPMASI (Uygulama veri çekemiyor)"
    elif any(k in birlesik_metin for k in ["responding", "yanıt vermiyor", "close app", "uygulamayı kapat"]):
        xml_teshis = "ANDROID ANR (Facebook arayüzü kilitlendi)"
    elif any(k in birlesik_metin for k in ["log in", "giriş yap", "session expired", "oturum", "checkpoint", "confirm"]):
        xml_teshis = "OTURUM / CHECKPOINT UYARISI (Hesap doğrulama veya yeniden giriş istiyor)"
        with lock:
            iyilestirme_notlari.add(f"KRİTİK - {node_id} ({ser}): Ekranda Oturum/Giriş/Checkpoint uyarısı yakalandı! '{dosya_yolu}' görüntüsünü kontrol edin.")
    elif any(k in birlesik_metin for k in ["allow", "izin ver", "not now", "şimdi değil", "save", "kaydet"]):
        xml_teshis = "POPUP / İZİN PENCERESİ (Akışın üstünü kapatan diyalog kutusu)"

    kayit = {
        "zaman": datetime.now().strftime("%H:%M:%S"),
        "node": node_id,
        "serial": ser,
        "sebep": sebep_etiketi,
        "gorsel_teshis": gorsel_teshis,
        "xml_teshis": xml_teshis,
        "ekran_metinleri": ", ".join(ekran_yazilari[:5]) if ekran_yazilari else "Metin okunamadı",
        "dosya": dosya_yolu
    }

    with lock:
        inceleme_kayitlari.append(kayit)

    log_yaz(
        f"[{node_id}] EKRAN İNCELENDİ -> Sebep: {sebep_etiketi} | Görsel: {gorsel_teshis} | Teşhis: {xml_teshis} | Kanıt: {dosya_yolu}",
        "İNCELEME"
    )
    return dosya_yolu

def raporu_guncelle():
    gecen_dk = int((time.time() - baslangic_ts) / 60)
    simdi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with lock:
        md = [
            "# 🔬 AutoFarm-30 // 5 Saatlik Görsel İncelemeli Stres & Hata Raporu",
            f"- **Test Başlangıç:** `{baslangic_str}`",
            f"- **Son Güncelleme:** `{simdi}` (Geçen Süre: **{gecen_dk} / {SURE_DAKIKA} dk**)",
            f"- **Aktif İzlenen Cihaz Sayısı:** `{len(stats)} adet`",
            f"- **Yakalanan Ekran Görüntüsü Klasörü:** `~/Desktop/autofarm-core/{HATA_KLASORU}/`",
            "",
            "## 1. Cihaz Bazlı Performans, Pil, Sıcaklık ve Takılma Tablosu",
            "| Node | Seri No | Durum | Kaydırma | Beğeni | Pil Değişimi | Max Isı | Donma/Kurtarma | Görsel İnceleme | USB Kopma |",
            "|---|---|---|---|---|---|---|---|---|---|"
        ]

        for node_id in sorted(stats.keys()):
            s = stats[node_id]
            pil_fark = s["cur_batt"] - s["start_batt"]
            pil_str = f"%{s['start_batt']} -> %{s['cur_batt']} ({pil_fark:+d}%)"
            md.append(
                f"| **{node_id}** | `{s['serial']}` | {s['status']} | {s['swipes']} | {s['likes']} | "
                f"{pil_str} | {s['max_temp']}°C | {s['freezes']} kez | {s['screenshots']} adet | {s['usb_drops']} kez |"
            )

        md.extend([
            "",
            "## 2. 📸 Ekran Görüntüsü Alınarak İncelenen Takılma ve Hatalar (Son 40 İnceleme)",
            "| Saat | Cihaz | Olay / Sebep | Görsel Piksel Analizi | UI / XML Teşhisi | Ekranda Yakalanan Metinler | Kanıt Görüntüsü |",
            "|---|---|---|---|---|---|---|"
        ])

        if not inceleme_kayitlari:
            md.append("| - | - | Şu ana kadar takılma yaşanmadı | - | - | - | - |")
        else:
            for k in inceleme_kayitlari[-40:]:
                md.append(
                    f"| `{k['zaman']}` | **{k['node']}** | {k['sebep']} | {k['gorsel_teshis']} | "
                    f"**{k['xml_teshis']}** | `{k['ekran_metinleri']}` | `{k['dosya']}` |"
                )

        md.extend([
            "",
            "## 3. 💡 Otomatik Teşhis ve İyileştirme Önerileri"
        ])
        if not iyilestirme_notlari:
            md.append("- Tüm cihazlar stabil sınırlar içinde çalışıyor; şu ana kadar ek müdahale gerektiren bir darboğaz oluşmadı.")
        else:
            for oneri in sorted(iyilestirme_notlari):
                md.append(f"- 🔧 **{oneri}**")

        with open(RAPOR_DOSYASI, "w", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")

def dusuk_guc_optimize_et(ser):
    subprocess.run(f"adb -s {ser} shell settings put system screen_brightness_mode 0", shell=True, capture_output=True)
    subprocess.run(f"adb -s {ser} shell settings put system screen_brightness 15", shell=True, capture_output=True)
    mute_device_audio(ser)

def cihaz_5saat_test_iscisi(idx, ser):
    node_id = f"NODE-{idx:02d}"
    time.sleep((idx - 1) * 1.2)

    vpn_ok, level, temp = check_vpn_and_temp(ser)
    with lock:
        stats[node_id] = {
            "serial": ser,
            "status": "HAZIRLANIYOR",
            "swipes": 0,
            "likes": 0,
            "start_batt": level,
            "cur_batt": level,
            "max_temp": temp,
            "freezes": 0,
            "screenshots": 0,
            "usb_drops": 0
        }

    wake_and_home(ser)
    dusuk_guc_optimize_et(ser)

    d = None
    W, H = 720, 1600
    try:
        d = u2.connect(ser)
        W, H = d.info.get("displayWidth", 720), d.info.get("displayHeight", 1600)
        if W > H: W, H = H, W
    except Exception as e:
        log_yaz(f"[{node_id} | {ser}] UIAutomator2 bağlantı uyarısı: {str(e)[:40]}", "UYARI")

    if not vpn_ok:
        ekran_goruntusu_al_ve_incele(d, ser, node_id, "VPN_Kapali_Uyarisi")
        with lock:
            stats[node_id]["screenshots"] += 1
            stats[node_id]["status"] = "VPN KAPALI ❌"
            iyilestirme_notlari.add(f"{node_id} ({ser}): Başlangıçta VPN (tun0) kapalı bulundu.")
        home_and_sleep(ser)
        raporu_guncelle()
        return

    log_yaz(f"[{node_id} | {ser}] Görsel Denetimli 5 Saatlik Isıtma Başladı | Pil: %{level} | Isı: {temp}C", "INFO")
    subprocess.run(f"adb -s {ser} shell monkey -p com.facebook.katana -c android.intent.category.LAUNCHER 1", shell=True, capture_output=True)
    time.sleep(random.uniform(6.0, 9.0))

    with lock:
        stats[node_id]["status"] = "AKTİF TESTTE 🟢"
    raporu_guncelle()

    bitis_zamani = baslangic_ts + (SURE_DAKIKA * 60)
    freeze_tracker = FreezeTracker()
    son_kontrol_gorseli = f"{HATA_KLASORU}/last_{node_id}.png"
    adim = 0

    while time.time() < bitis_zamani:
        adim += 1
        try:
            # 1. USB / ADB Kopma Kontrolu
            adb_out = subprocess.check_output("adb devices", shell=True, text=True)
            if f"{ser}\tdevice" not in adb_out:
                with lock:
                    stats[node_id]["usb_drops"] += 1
                    stats[node_id]["status"] = "USB KOPTU ⚠️"
                    iyilestirme_notlari.add(f"{node_id} ({ser}): USB Hub portundan anlık düştü ve 'adb reconnect' ile geri bağlandı.")
                log_yaz(f"[{node_id}] USB bağlantısı koptu! Reconnect uygulanıyor...", "SORUN")
                subprocess.run("adb reconnect offline", shell=True, capture_output=True)
                time.sleep(8.0)
                continue

            # 2. Periyodik Pil & Sicaklik & VPN Kontrolu
            if adim % 5 == 0:
                vpn_ok, level, temp = check_vpn_and_temp(ser)
                with lock:
                    stats[node_id]["cur_batt"] = level
                    if temp > stats[node_id]["max_temp"]:
                        stats[node_id]["max_temp"] = temp
                    if (stats[node_id]["start_batt"] - level) >= 15:
                        iyilestirme_notlari.add(f"{node_id} ({ser}): Pil %{stats[node_id]['start_batt']} -> %{level} seviyesine geriledi. Hub portunun şarj akımı düşük.")

                if not vpn_ok:
                    ekran_goruntusu_al_ve_incele(d, ser, node_id, "VPN_Koptu")
                    subprocess.run(f"adb -s {ser} shell am force-stop com.facebook.katana", shell=True, capture_output=True)
                    with lock:
                        stats[node_id]["screenshots"] += 1
                        stats[node_id]["status"] = "VPN KOPTU ❌"
                    break

                if temp >= 42.5:
                    log_yaz(f"[{node_id}] Sıcaklık {temp}C sınırını aştı! 10 dk soğumaya alınıyor...", "UYARI")
                    with lock:
                        stats[node_id]["status"] = f"SOĞUMA ({temp}C) ❄️"
                    home_and_sleep(ser)
                    time.sleep(600)
                    wake_and_home(ser)
                    dusuk_guc_optimize_et(ser)
                    subprocess.run(f"adb -s {ser} shell monkey -p com.facebook.katana -c android.intent.category.LAUNCHER 1", shell=True, capture_output=True)
                    time.sleep(6.0)
                    continue

            # 3. Facebook On Planda mi Kontrolu
            win_out = subprocess.run(f"adb -s {ser} shell dumpsys window displays", shell=True, capture_output=True, text=True).stdout
            if "com.facebook.katana" not in win_out:
                ekran_goruntusu_al_ve_incele(d, ser, node_id, "FB_Kapandi_ArkaPlana_Dustu", son_kontrol_gorseli)
                with lock:
                    stats[node_id]["freezes"] += 1
                    stats[node_id]["screenshots"] += 1
                freeze_tracker.reset()
                force_restart_fb(ser, node_id, "Facebook kapandı veya arka plana düştü")
                continue

            # 4. UI / XML ve Gorsel Takilma Denetimi
            if d:
                # Popup veya Izin Penceresi Yakalama
                dismiss_btn = d(textMatches="(?i)^not now$|^şimdi değil$|^hayır$|^iptal$|^cancel$|^deny$|^reddet$|^kapat$")
                if dismiss_btn.exists:
                    ekran_goruntusu_al_ve_incele(d, ser, node_id, "Popup_Diyalog_Yakalandi")
                    b = dismiss_btn[0].info.get("bounds", {})
                    if b:
                        subprocess.run(f"adb -s {ser} shell input tap {(b['left']+b['right'])//2} {(b['top']+b['bottom'])//2}", shell=True, capture_output=True)
                    with lock:
                        stats[node_id]["screenshots"] += 1

                # Internet Yok / ANR / Yanit Vermiyor Yakalama
                if d(textMatches="(?i).*no internet.*|.*connection lost.*|.*bağlantı yok.*|.*tekrar dene.*|.*try again.*|.*isn't responding.*|.*yanıt vermiyor.*").exists:
                    ekran_goruntusu_al_ve_incele(d, ser, node_id, "Internet_Yok_veya_ANR")
                    with lock:
                        stats[node_id]["freezes"] += 1
                        stats[node_id]["screenshots"] += 1
                    freeze_tracker.reset()
                    force_restart_fb(ser, node_id, "İnternet Çekmeme / ANR Uyarısı")
                    continue

                # XML Donma ve Gecikme Suresi Olcumu
                t0 = time.time()
                cur_xml = d.dump_hierarchy()
                dump_sure = round(time.time() - t0, 2)

                if dump_sure > 4.5:
                    ekran_goruntusu_al_ve_incele(d, ser, node_id, f"Agir_UI_Kasmasi_{dump_sure}sn")
                    with lock:
                        stats[node_id]["screenshots"] += 1
                        iyilestirme_notlari.add(f"{node_id} ({ser}): UI yanıt süresi {dump_sure} sn sürdü (Ağır kasma tespit edildi ve görüntüsü alındı).")

                if freeze_tracker.observe(cur_xml):
                    ekran_goruntusu_al_ve_incele(d, ser, node_id, f"{FREEZE_STEP_LIMIT}_Adim_Akis_Donmasi", son_kontrol_gorseli)
                    with lock:
                        stats[node_id]["freezes"] += 1
                        stats[node_id]["screenshots"] += 1
                    freeze_tracker.reset()
                    force_restart_fb(ser, node_id, f"{FREEZE_STEP_LIMIT} Adım Ekran Donması")
                    continue

                # Referans karsilastirma icin her 8 adimda bir gecici kare kaydet
                if adim % 8 == 0:
                    try: d.screenshot(son_kontrol_gorseli)
                    except Exception: pass

            # 5. Biyometrik Izleme, Begeni ve Kaydirma
            bekleme = round(random.uniform(3.2, 6.0), 1) if random.random() < 0.3 else round(random.uniform(6.5, 14.5), 1)
            time.sleep(bekleme)

            if d and bekleme > 6.0 and random.random() < 0.14:
                like_btn = d(descriptionMatches="(?i)^like$|^beğen$|.*like button.*|.*beğen düğmesi.*")
                if like_btn.exists:
                    b = like_btn[0].info.get("bounds", {})
                    if b and int(H * 0.18) < b.get("top", 0) < int(H * 0.85):
                        subprocess.run(f"adb -s {ser} shell input tap {(b['left']+b['right'])//2} {(b['top']+b['bottom'])//2}", shell=True, capture_output=True)
                        with lock:
                            stats[node_id]["likes"] += 1
                        time.sleep(1.4)

            x1, y1 = random.randint(int(W*0.38), int(W*0.62)), random.randint(int(H*0.70), int(H*0.82))
            x2, y2 = x1 + random.randint(-35, 35), random.randint(int(H*0.20), int(H*0.32))
            subprocess.run(f"adb -s {ser} shell input swipe {x1} {y1} {x2} {y2} {random.randint(260, 520)}", shell=True, capture_output=True)

            with lock:
                stats[node_id]["swipes"] += 1
                stats[node_id]["status"] = "AKTİF TESTTE 🟢"

            if adim % 8 == 0:
                raporu_guncelle()

        except Exception as e:
            ekran_goruntusu_al_ve_incele(d, ser, node_id, "Beklenmeyen_Calisma_Hatasi")
            with lock:
                stats[node_id]["freezes"] += 1
                stats[node_id]["screenshots"] += 1
            freeze_tracker.reset()
            force_restart_fb(ser, node_id, f"Hata Kurtarma ({str(e)[:25]})")

    home_and_sleep(ser)
    with lock:
        stats[node_id]["status"] = "TAMAMLANDI ✅"
    raporu_guncelle()

if __name__ == "__main__":
    subprocess.run("adb reconnect offline", shell=True, capture_output=True)
    out = subprocess.check_output("adb devices", shell=True, text=True).strip().splitlines()[1:]
    serials = [l.split()[0] for l in out if len(l.split()) >= 2 and l.split()[1] == "device"]

    print("=" * 78, flush=True)
    print(f"[*] GÖRSEL İNCELEMELİ 5 SAATLİK STRES & TAKILMA ANALİZ MOTORU BAŞLATILDI", flush=True)
    print(f"[*] Cihaz Sayısı: {len(serials)} | Rapor: {RAPOR_DOSYASI} | Görüntüler: {HATA_KLASORU}/", flush=True)
    print("=" * 78, flush=True)

    threads = [threading.Thread(target=cihaz_5saat_test_iscisi, args=(i, s), daemon=True) for i, s in enumerate(serials, 1)]
    for t in threads:
        t.start()

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(25)
            raporu_guncelle()
    except KeyboardInterrupt:
        log_yaz("Test kullanıcı tarafından durduruldu, son rapor kaydediliyor...", "UYARI")
        raporu_guncelle()
