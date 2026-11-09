import os

center_func_code = '''def smart_scroll_and_center(d, ser, W=720, H=1600):
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
'''

# 1. core_engine.py dosyasina smart_scroll_and_center ekle ve eski kor kaydirmalari degistir
with open("core_engine.py", "r", encoding="utf-8") as f:
    core_code = f.read()

if "def smart_scroll_and_center" not in core_code:
    core_code = core_code.replace(
        "def organic_sandwich_scroll(",
        center_func_code + "\ndef organic_sandwich_scroll("
    )

# Sandvic oturumu icindeki kaydirmayi akilli ortalama ile degistir
old_sandwich_loop = '''    while time.time() < end_t:
        x1, y1 = random.randint(280, 440), random.randint(1100, 1300)
        x2, y2 = x1 + random.randint(-30, 30), random.randint(320, 480)
        subprocess.run(f"adb -s {ser} shell input swipe {x1} {y1} {x2} {y2} {random.randint(280, 480)}", shell=True, capture_output=True)
        time.sleep(random.uniform(3.0, 5.5))'''

new_sandwich_loop = '''    while time.time() < end_t:
        smart_scroll_and_center(d, ser, 720, 1600)
        time.sleep(random.uniform(3.0, 5.5))'''

core_code = core_code.replace(old_sandwich_loop, new_sandwich_loop)

# Isitma (worker_warmup) icindeki kaydirmayi akilli ortalama ile degistir
old_warmup_swipe = '''            x1, y1 = random.randint(int(W*0.38), int(W*0.62)), random.randint(int(H*0.70), int(H*0.82))
            x2, y2 = x1 + random.randint(-35, 35), random.randint(int(H*0.20), int(H*0.32))
            subprocess.run(f"adb -s {ser} shell input swipe {x1} {y1} {x2} {y2} {random.randint(260, 520)}", shell=True, capture_output=True)'''

new_warmup_swipe = '''            smart_scroll_and_center(d, ser, W, H)'''

core_code = core_code.replace(old_warmup_swipe, new_warmup_swipe)

with open("core_engine.py", "w", encoding="utf-8") as f:
    f.write(core_code)
print("[OK] core_engine.py -> Miknatisli Gonderi Ortalama (smart_scroll_and_center) eklendi!")

# 2. stres_testi_5saat.py dosyasini da akilli ortalama kullanacak sekilde guncelle
if os.path.exists("stres_testi_5saat.py"):
    with open("stres_testi_5saat.py", "r", encoding="utf-8") as f:
        st_code = f.read()

    st_code = st_code.replace(
        "wake_and_home, home_and_sleep, check_vpn_and_temp, force_restart_fb",
        "wake_and_home, home_and_sleep, check_vpn_and_temp, force_restart_fb, smart_scroll_and_center"
    )
    st_code = st_code.replace(old_warmup_swipe, new_warmup_swipe)

    with open("stres_testi_5saat.py", "w", encoding="utf-8") as f:
        f.write(st_code)
    print("[OK] stres_testi_5saat.py -> 5 saatlik test motoruna da Gonderi Ortalama entegre edildi!")
