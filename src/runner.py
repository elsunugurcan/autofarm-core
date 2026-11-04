import os
import sys
import time
import sqlite3
from adbutils import adb

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from device_driver import DeviceDriver
from humanizer import Humanizer, Persona
from organic_brain import ThermalGuard, PersonaCommentBrain, OrganicSessionPlanner
from campaign_manager import CampaignDistributor

DB_PATH = "autofarm.db"


def run_biometric_warmup(dev_id: int, simulation_mode: bool = True):
    serial = f"NODE-{dev_id:02d}"
    persona = Persona.get_for_device(dev_id)
    bio = Humanizer.get_circadian_status()
    health = ThermalGuard.check_device_health(serial, simulation_mode=simulation_mode)

    print(
        f"[{serial}] 🌡️ Donanim: {health['temp_c']}°C | 🔋 Pil: %{health['battery_pct']} ({health['status']}) | 🧬 Persona: {persona['name']}",
        flush=True
    )
    if not health["safe"]:
        print(f"[{serial}] ⚠️ Cihaz sicakligi yuksek ({health['temp_c']}°C)! Soguma molasina alindi.", flush=True)
        return

    drv = DeviceDriver(serial, simulation_mode=simulation_mode)
    _, msg_conn = drv.connect(app_package="com.facebook.katana")
    print(msg_conn, flush=True)

    for step in range(1, 3):
        att = Humanizer.simulate_content_attention(persona)
        swp = Humanizer.swipe_up_feed(None, persona)
        wait_demo = min(att["watch_sec"], 1.2) if simulation_mode else att["watch_sec"]
        time.sleep(wait_demo * bio["fatigue_mult"] * 0.4)

        print(
            f"[{serial}] 👆 Adim {step}/2: {swp['action']} {swp['start']}->Yay{swp['arc_midpoint']}->{swp['end']} ({swp['duration_sec']}sn) | 👀 {att['behavior']}",
            flush=True
        )

    drv.close()


def process_pending_tasks(simulation_mode=True):
    CampaignDistributor.ensure_schema()
    bio = Humanizer.get_circadian_status()
    print(f"[BIYOLOJIK SAAT] 🌙 Faz: {bio['phase']} | Aktiflik: %{int(bio['activity_prob']*100)} | Yorgunluk: x{bio['fatigue_mult']}", flush=True)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT id, device_id, post_link, action_type, comment_text, campaign_code, delay_sec
           FROM targeted_tasks
           WHERE status = 'PENDING'
           ORDER BY delay_sec ASC, id ASC"""
    )
    tasks = c.fetchall()

    if not tasks:
        print("[RUNNER] Bekleyen kampanya gorevi yok. Ilk 3 dugumde Organik & Biyometrik Isindirma baslatiliyor...", flush=True)
        for i in range(1, 4):
            run_biometric_warmup(i, simulation_mode=simulation_mode)
        conn.close()
        return

    print(f"[KAMPANYA MOTORU] 🚀 Kuyrukta {len(tasks)} adet zaman ayarli (Drip-Feed) gorev bulundu! Dalga baslatiliyor...", flush=True)
    prev_delay = 0

    for idx, (t_id, dev_id, link, act_type, comment, cmp_code, delay_sec) in enumerate(tasks, 1):
        serial = f"NODE-{dev_id:02d}"
        persona = Persona.get_for_device(dev_id)
        health = ThermalGuard.check_device_health(serial, simulation_mode=simulation_mode)

        step_wait = max(0, delay_sec - prev_delay)
        prev_delay = delay_sec
        actual_sleep = min(step_wait * 0.15, 1.5) if simulation_mode else step_wait
        if step_wait > 0:
            print(f"\n⏳ [DRIP-FEED ZAMANLAYICI] Siradaki dugum ({serial}) icin +{step_wait}sn organik dalga gecikmesi bekleniyor...", flush=True)
            time.sleep(actual_sleep)

        print(
            f"[{cmp_code} | {idx}/{len(tasks)}] 📱 {serial} (T+{delay_sec}sn) | 🌡️ {health['temp_c']}°C | 🧬 Persona: {persona['name']}",
            flush=True
        )
        if not health["safe"]:
            print(f"[{serial}] 🚨 Sicaklik siniri asildi, gorev ertelendi.", flush=True)
            continue

        drv = DeviceDriver(serial, simulation_mode=simulation_mode)
        _, msg1 = drv.connect(app_package="com.facebook.katana")
        print(msg1, flush=True)

        plan = OrganicSessionPlanner.build_sandwich_plan(act_type, link)
        for step_info in plan:
            print(f"[{serial}] 🥪 [{step_info['stage']}] {step_info['desc']}", flush=True)
            time.sleep(0.35)

            if step_info["stage"] == "2_TARGET_EXEC":
                swp = Humanizer.swipe_up_feed(None, persona)
                print(f"[{serial}] 👆 Bezier Odaklanma: {swp['start']} -> {swp['arc_midpoint']} -> {swp['end']}", flush=True)

                if act_type == "COMMENT":
                    final_comment = comment or PersonaCommentBrain.craft_comment(dev_id, "")
                    seq = Humanizer.generate_typing_sequence(final_comment, typo_rate=persona["typo_rate"])
                    typos = sum(1 for a, _, _ in seq if a == "TYPE_WRONG")
                    total_type_sec = round(sum(d for _, _, d in seq), 2)
                    time.sleep(min(total_type_sec, 0.8))
                    print(
                        f"[{serial}] 🧠 Yorum: '{final_comment}' | ⌨️ Sure: {total_type_sec}sn | Silinen Harf Hatasi (⌫): {typos}",
                        flush=True
                    )

                _, msg2 = drv.execute_action(act_type, link, comment)
                print(msg2, flush=True)

        drv.close()
        c.execute("UPDATE targeted_tasks SET status = 'COMPLETED' WHERE id = ?", (t_id,))
        c.execute("UPDATE fb_accounts SET daily_likes = daily_likes + 1 WHERE device_id = ?", (dev_id,))
        conn.commit()
        print(f"[DB] ✅ Gorev #{t_id} ({serial}) COMPLETED olarak islendi.", flush=True)

    conn.close()


if __name__ == "__main__":
    connected = [d.serial for d in adb.device_list()]
    sim_mode = len(connected) == 0
    if sim_mode:
        print("[MOD] 🛠️  Fiziksel cihaz bagli degil -> KAMPANYA DRIP-FEED SIMULASYON MODU AKTIF", flush=True)
    else:
        print(f"[MOD] 📱 {len(connected)} fiziksel cihaz algilandi -> CANLI KAMPANYA MODU AKTIF", flush=True)
    process_pending_tasks(simulation_mode=sim_mode)
