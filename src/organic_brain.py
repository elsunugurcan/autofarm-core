import os
import random
import subprocess
from humanizer import Persona


class ThermalGuard:
    """Cihazlarin batarya sicakligini ve sarj seviyesini denetler (7/24 Fiziksel Filo Korumasi)."""
    @staticmethod
    def check_device_health(serial: str, simulation_mode: bool = True):
        if simulation_mode:
            temp_c = round(random.uniform(31.5, 38.5), 1)
            level = random.randint(45, 85)
            return {
                "temp_c": temp_c,
                "battery_pct": level,
                "safe": temp_c < 42.0,
                "status": "NORMAL" if temp_c < 40.0 else "WARM"
            }

        try:
            out = subprocess.check_output(["adb", "-s", serial, "shell", "dumpsys", "battery"], text=True)
            temp_c = 35.0
            level = 80
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("temperature:"):
                    temp_c = int(line.split(":")[1].strip()) / 10.0
                elif line.startswith("level:"):
                    level = int(line.split(":")[1].strip())
            return {
                "temp_c": temp_c,
                "battery_pct": level,
                "safe": temp_c < 42.0,
                "status": "NORMAL" if temp_c < 42.0 else "OVERHEAT_COOLDOWN"
            }
        except Exception:
            return {"temp_c": 36.0, "battery_pct": 75, "safe": True, "status": "UNKNOWN"}


class PersonaCommentBrain:
    """Cihazin Persona karakterine uygun uslup ve kelime secimiyle ozgun yorum uretir."""
    STYLES = {
        "Sabirsiz_Genclik": [
            "Cok iyi olmus ya 🔥",
            "Harika valla tebrikler 👏",
            "Efsane paylasim 🚀",
            "Bayildim buna super!",
            "Tam isabet olmus 💯"
        ],
        "Dikkatli_Okuyucu": [
            "Paylasilan detaylar gercekten cok faydali, emeginize saglik.",
            "Konuyu cok guzel ozetlemissiniz, basarilarinizin devamini dilerim.",
            "Oldukca bilgilendirici ve kaliteli bir icerik olmus, tesekkurler.",
            "Bu bakis acisi kesinlikle cok degerli, tebrik ederim."
        ],
        "Gece_Kusu_Analist": [
            "Detaylara dikkat edilmis, gayet basarili bir calisma 👍",
            "Kaliteli icerik, paylasim icin tesekkurler.",
            "Cok yerinde bir tespit olmus, katiliyorum ✨",
            "Akici ve guzel bir paylasim, elinize saglik."
        ],
        "Yavas_Geleneksel": [
            "Hayirli ve guzel paylasimlar dilerim, emeginize saglik.",
            "Cok guzel olmus, basarilar dilerim.",
            "Tesekkurler, cok faydali bir paylasim.",
            "Elinize emeginize saglik, cok begendim."
        ]
    }

    @staticmethod
    def craft_comment(device_id: int, base_hint: str = ""):
        persona = Persona.get_for_device(device_id)
        archetype = persona["name"]
        pool = PersonaCommentBrain.STYLES.get(archetype, PersonaCommentBrain.STYLES["Dikkatli_Okuyucu"])
        chosen = random.choice(pool)

        if base_hint and len(base_hint.strip()) > 3:
            # Kullanici ozel bir yorum girdiyse, Persona karakterine gore sonuna dogal varyasyon ekler
            if archetype == "Sabirsiz_Genclik" and "🔥" not in base_hint:
                return f"{base_hint.strip()} 🔥"
            elif archetype == "Dikkatli_Okuyucu" and not base_hint.strip().endswith("."):
                return f"{base_hint.strip()}."
            return base_hint.strip()
        return chosen


class OrganicSessionPlanner:
    """Vur-Kac (Hit & Run) bot davranisini onleyen 3 asamali Sandvic Oturum Kurgulayici."""
    @staticmethod
    def build_sandwich_plan(action_type: str, target_link: str):
        pre_scrolls = random.randint(2, 4)
        post_scrolls = random.randint(1, 3)
        check_notif = random.random() < 0.45

        steps = [
            {"stage": "1_PRE_WARMUP", "desc": f"Ana akista {pre_scrolls} gonderi dogal kaydirma (On Isinma)"},
        ]
        if check_notif:
            steps.append({"stage": "1B_MICRO_ACTION", "desc": "Bildirim sekmesine kisa goz atma (1.8sn)"})

        steps.append({
            "stage": "2_TARGET_EXEC",
            "desc": f"Hedef gonderiye gecis ve {action_type} islemi -> {target_link[:35]}"
        })
        steps.append({
            "stage": "3_COOLDOWN",
            "desc": f"Ana akisa donus, {post_scrolls} Reels/Gonderi izleme ve dogal cikis"
        })
        return steps
