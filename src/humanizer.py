import random
import time
import math
from datetime import datetime
from rich.console import Console

console = Console()

QWERTY_NEIGHBORS = {
    'a': 'sqzw', 'b': 'vghn', 'c': 'xdfv', 'd': 'serfcx', 'e': 'wsdr',
    'f': 'drtgvc', 'g': 'ftyhbv', 'h': 'gyujnb', 'i': 'ujko', 'j': 'huikmn',
    'k': 'jiolm', 'l': 'kop', 'm': 'njk', 'n': 'bhjm', 'o': 'iklp',
    'p': 'ol', 'r': 'edft', 's': 'awedxz', 't': 'rfgy', 'u': 'yhji',
    'v': 'cfgb', 'w': 'qase', 'x': 'zsdc', 'y': 'tghu', 'z': 'asx'
}


class Persona:
    """Her cihaza (Node) benzersiz bir insan karakteri ve parmak aliskanligi atar."""
    ARCHETYPES = [
        {"name": "Sabirsiz_Genclik", "speed_mult": 0.75, "typo_rate": 0.08, "skip_prob": 0.65, "handedness": "RIGHT"},
        {"name": "Dikkatli_Okuyucu", "speed_mult": 1.25, "typo_rate": 0.03, "skip_prob": 0.35, "handedness": "RIGHT"},
        {"name": "Gece_Kusu_Analist", "speed_mult": 1.00, "typo_rate": 0.05, "skip_prob": 0.50, "handedness": "LEFT"},
        {"name": "Yavas_Geleneksel", "speed_mult": 1.45, "typo_rate": 0.04, "skip_prob": 0.25, "handedness": "RIGHT"},
    ]

    @staticmethod
    def get_for_device(device_id: int):
        rng = random.Random(device_id * 997)
        base = rng.choice(Persona.ARCHETYPES).copy()
        base["jitter_px"] = rng.randint(12, 26)
        return base


class Humanizer:
    @staticmethod
    def wait(min_sec=1.5, max_sec=4.0, speed_mult=1.0, fatigue_factor=1.0):
        """Log-normal dagilimli, oturum yorgunluguna duyarli insansi bekleme."""
        mean = ((min_sec + max_sec) / 2.0) * speed_mult * fatigue_factor
        sigma = (max_sec - min_sec) / 4.0
        delay = max(min_sec * 0.6, random.gauss(mean, sigma))
        time.sleep(delay)
        return round(delay, 2)

    @staticmethod
    def calculate_bezier_arc(start_x, start_y, end_x, end_y, handedness="RIGHT", steps=12):
        """Basparmak eklem kavisine uygun Quadratic Bezier egrisi noktalari uretir."""
        curve_offset = random.randint(35, 85) * (1 if handedness == "RIGHT" else -1)
        ctrl_x = int((start_x + end_x) / 2) + curve_offset
        ctrl_y = int((start_y + end_y) / 2) + random.randint(-30, 30)

        points = []
        for i in range(steps + 1):
            t = i / steps
            bx = int((1 - t)**2 * start_x + 2 * (1 - t) * t * ctrl_x + t**2 * end_x)
            by = int((1 - t)**2 * start_y + 2 * (1 - t) * t * ctrl_y + t**2 * end_y)
            points.append((bx, by))
        return points

    @staticmethod
    def swipe_up_feed(d=None, persona=None, screen_size=(1080, 2400)):
        """Kavisli basparmak hareketiyle akis kaydirma (Gercek cihaz ve Simulasyon uyumlu)."""
        persona = persona or Persona.get_for_device(1)
        w, h = d.window_size() if d else screen_size

        bias = 0.58 if persona["handedness"] == "RIGHT" else 0.42
        start_x = int(w * random.uniform(bias - 0.08, bias + 0.08))
        start_y = int(h * random.uniform(0.70, 0.85))
        end_x = start_x + random.randint(-65, 65)
        end_y = int(h * random.uniform(0.16, 0.28))

        arc_points = Humanizer.calculate_bezier_arc(start_x, start_y, end_x, end_y, persona["handedness"])
        duration = round(random.uniform(0.18, 0.45) * persona["speed_mult"], 3)

        if d:
            d.swipe(start_x, start_y, end_x, end_y, duration=duration)
        return {
            "action": "BEZIER_SWIPE_UP",
            "start": (start_x, start_y),
            "end": (end_x, end_y),
            "arc_midpoint": arc_points[len(arc_points) // 2],
            "duration_sec": duration
        }

    @staticmethod
    def swipe_back_slightly(d=None, screen_size=(1080, 2400)):
        """Insanlarin az once gectigi gonderiye/yoruma tekrar bakmak icin yaptigi ufak geri kaydirma."""
        w, h = d.window_size() if d else screen_size
        sx = int(w * random.uniform(0.45, 0.55))
        sy = int(h * 0.35)
        ey = int(h * 0.58)
        dur = round(random.uniform(0.22, 0.38), 3)
        if d:
            d.swipe(sx, sy, sx + random.randint(-20, 20), ey, duration=dur)
        return {"action": "MICRO_SCROLL_BACK", "duration_sec": dur}

    @staticmethod
    def simulate_content_attention(persona=None):
        """Gonderi izleme davranisi: Hizli gecis (%50+), normal izleme veya geri donup okuma."""
        persona = persona or Persona.get_for_device(1)
        roll = random.random()

        if roll < persona["skip_prob"]:
            watch_sec = round(random.uniform(0.7, 1.6), 2)
            behavior = "FAST_SKIP (Ilgi cekmedi, hizli gecildi)"
        elif roll < 0.88:
            watch_sec = round(random.uniform(3.5, 8.5) * persona["speed_mult"], 2)
            behavior = "NORMAL_WATCH (Normal izleme)"
        else:
            watch_sec = round(random.uniform(9.0, 16.0) * persona["speed_mult"], 2)
            behavior = "DEEP_FOCUS (Derin odaklanma + Tekrar okuma)"

        return {"behavior": behavior, "watch_sec": watch_sec}

    @staticmethod
    def generate_typing_sequence(text: str, typo_rate=0.06):
        """
        Metni harf harf yazarken gercekci klavye gecikmeleri ve yanlis tusa basip
        Backspace ile duzeltme (Typo + Correction) adimlari uretir.
        """
        events = []
        for ch in text:
            lower_ch = ch.lower()
            if lower_ch in QWERTY_NEIGHBORS and random.random() < typo_rate:
                wrong_char = random.choice(QWERTY_NEIGHBORS[lower_ch])
                events.append(("TYPE_WRONG", wrong_char, round(random.uniform(0.06, 0.14), 3)))
                events.append(("REALIZE_PAUSE", "", round(random.uniform(0.22, 0.45), 3)))
                events.append(("BACKSPACE", "⌫", round(random.uniform(0.08, 0.15), 3)))

            delay = round(random.uniform(0.05, 0.16), 3)
            if ch in " .,!?:":
                delay += round(random.uniform(0.15, 0.35), 3)
            events.append(("TYPE_CHAR", ch, delay))
        return events

    @staticmethod
    def get_circadian_status():
        """Gunun saatine gore biyolojik aktivite katsayisini dondurur."""
        hour = datetime.now().hour
        if 2 <= hour < 7:
            return {"phase": "DERIN_UYKU", "activity_prob": 0.05, "fatigue_mult": 1.6}
        elif 7 <= hour < 11:
            return {"phase": "SABAH_KAHVESI", "activity_prob": 0.75, "fatigue_mult": 1.0}
        elif 11 <= hour < 18:
            return {"phase": "GUN_ICI_AKTIF", "activity_prob": 0.85, "fatigue_mult": 0.95}
        elif 18 <= hour <= 23:
            return {"phase": "PRIME_TIME (Zirve)", "activity_prob": 0.98, "fatigue_mult": 0.90}
        else:
            return {"phase": "GECE_YORGUNLUGU", "activity_prob": 0.40, "fatigue_mult": 1.35}


if __name__ == "__main__":
    console.print("\n[bold cyan]🧬 AutoFarm-30 Biyometrik İnsansı Davranış Motoru (v2.0) Testi[/bold cyan]\n")
    for dev_id in [1, 2]:
        p = Persona.get_for_device(dev_id)
        att = Humanizer.simulate_content_attention(p)
        swp = Humanizer.swipe_up_feed(None, p)
        console.print(f"[bold magenta]Node-{dev_id:02d} Persona:[/bold magenta] {p['name']} (Başparmak: {p['handedness']} | Hız: x{p['speed_mult']})")
        console.print(f"  👀 [yellow]Odaklanma:[/yellow] {att['behavior']} -> {att['watch_sec']} sn")
        console.print(f"  👆 [green]Bézier Yay Kaydırma:[/green] Başlangıç {swp['start']} -> Tepe Noktası {swp['arc_midpoint']} -> Bitiş {swp['end']} ({swp['duration_sec']} sn)\n")

    sample_comment = "Harika paylasim olmus tebrikler!"
    typing_sim = Humanizer.generate_typing_sequence(sample_comment, typo_rate=0.18)
    visual_stream = ""
    for action, char, dly in typing_sim:
        if action == "TYPE_WRONG":
            visual_stream += f"[bold red]{char}[/bold red]"
        elif action == "BACKSPACE":
            visual_stream += f"[bold yellow]{char}[/bold yellow]"
        elif action == "TYPE_CHAR":
            visual_stream += char

    console.print(f"[bold cyan]⌨️  İnsansı Klavye Simülasyonu (Hatalı basım + Silme dahil):[/bold cyan]")
    console.print(f"   Çıktı Akışı: {visual_stream}")
    bio = Humanizer.get_circadian_status()
    console.print(f"\n[bold blue]🌙 Biyolojik Saat Durumu:[/bold blue] {bio['phase']} | Aktiflik İhtimali: %{int(bio['activity_prob']*100)}\n")
