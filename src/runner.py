import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from adbutils import adb
from device_driver import DeviceDriver

DB_PATH = "autofarm.db"

def process_pending_tasks(simulation_mode=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, device_id, post_link, action_type, comment_text FROM targeted_tasks WHERE status = 'PENDING'")
    tasks = c.fetchall()
    
    if not tasks:
        print("[RUNNER] Veritabaninda bekleyen hedefli gorev yok. 3 sanal dugumde rutin kontrol baslatiliyor...")
        for i in range(1, 4):
            drv = DeviceDriver(f"SIM-NODE-0{i}", simulation_mode=True)
            _, msg1 = drv.connect(app_package="com.facebook.katana")
            print(msg1, flush=True)
            _, msg2 = drv.execute_action("FEED_WARMUP", "facebook://feed")
            print(msg2, flush=True)
            drv.close()
        conn.close()
        return

    print(f"[RUNNER] Kuyrukta {len(tasks)} adet hedefli gorev bulundu, isleniyor...", flush=True)
    for t_id, dev_id, link, act_type, comment in tasks:
        serial = f"NODE-{dev_id:02d}"
        drv = DeviceDriver(serial, simulation_mode=simulation_mode)
        _, msg1 = drv.connect(app_package="com.facebook.katana")
        print(msg1, flush=True)
        _, msg2 = drv.execute_action(act_type, link, comment)
        print(msg2, flush=True)
        drv.close()
        c.execute("UPDATE targeted_tasks SET status = 'COMPLETED' WHERE id = ?", (t_id,))
        c.execute("UPDATE fb_accounts SET daily_likes = daily_likes + 1 WHERE device_id = ?", (dev_id,))
        conn.commit()
        print(f"[DB] Gorev #{t_id} COMPLETED olarak isaretlendi.", flush=True)
    conn.close()

if __name__ == "__main__":
    connected = [d.serial for d in adb.device_list()]
    sim_mode = len(connected) == 0
    if sim_mode:
        print("[MOD] Fiziksel cihaz bagli degil -> SIMULASYON MODU AKTIF", flush=True)
    else:
        print(f"[MOD] {len(connected)} fiziksel cihaz algilandi -> CANLI MOD AKTIF", flush=True)
    process_pending_tasks(simulation_mode=sim_mode)
