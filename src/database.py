import sqlite3
import json
from rich.console import Console
from rich.table import Table

console = Console()
DB_PATH = "autofarm.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY,
        name TEXT,
        serial TEXT,
        local_ip TEXT,
        proxy TEXT,
        status TEXT DEFAULT 'OFFLINE'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS fb_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER,
        fb_username TEXT,
        app_package TEXT DEFAULT 'com.facebook.katana',
        profile_slot TEXT DEFAULT 'MAIN',
        warmup_level INTEGER DEFAULT 1,
        daily_likes INTEGER DEFAULT 0,
        daily_group_joins INTEGER DEFAULT 0,
        daily_shares INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ACTIVE'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS action_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER,
        action_type TEXT,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    with open("config/devices.json", "r") as f:
        devices = json.load(f).get("devices", [])
    for dev in devices:
        c.execute("INSERT OR REPLACE INTO devices (id, name, serial, local_ip, proxy) VALUES (?, ?, ?, ?, ?)",
                  (dev["id"], dev["name"], dev["serial"], dev["local_ip"], dev["proxy"]))
    c.execute("SELECT COUNT(*) FROM fb_accounts")
    if c.fetchone()[0] == 0:
        sample_fb = [
            (1, "fb_node01_ana_hesap", "com.facebook.katana", "MAIN", 1),
            (1, "fb_node01_lite_hesap", "com.facebook.lite", "MAIN", 1),
            (1, "fb_node01_is_profili", "com.facebook.katana", "WORK", 1)
        ]
        c.executemany("INSERT INTO fb_accounts (device_id, fb_username, app_package, profile_slot, warmup_level) VALUES (?, ?, ?, ?, ?)", sample_fb)
    conn.commit()
    conn.close()

def show_accounts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT a.id, d.name, a.fb_username, a.app_package, a.profile_slot, a.warmup_level, a.daily_likes, a.daily_group_joins, a.status FROM fb_accounts a JOIN devices d ON a.device_id = d.id")
    rows = c.fetchall()
    conn.close()
    table = Table(title="AutoFarm-20 Facebook Hesap ve Warm-Up Tablosu")
    table.add_column("ID", justify="center", style="cyan")
    table.add_column("Cihaz", style="magenta")
    table.add_column("FB Hesabi", style="white")
    table.add_column("Uygulama Paketi", style="yellow")
    table.add_column("Profil", justify="center", style="blue")
    table.add_column("Warm-Up", justify="center", style="green")
    table.add_column("Begeni / Grup", justify="center")
    table.add_column("Durum", justify="center", style="bold green")
    for r in rows:
        table.add_row(str(r[0]), r[1], r[2], r[3], r[4], f"Seviye {r[5]}", f"{r[6]} / {r[7]}", r[8])
    console.print(table)

if __name__ == "__main__":
    init_db()
    console.print("[bold blue][+] Veritabani %100 Facebook mimarisine gore sifirlandi ve kuruldu![/bold blue]\n")
    show_accounts()
import sqlite3
import json
from rich.console import Console

console = Console()
DB_PATH = "autofarm.db"

def init_task_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS targeted_tasks (
        id INTEGER INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id INTEGER,
        post_link TEXT,
        action_type TEXT, -- LIKE, COMMENT, REELS_WATCH
        comment_text TEXT,
        status TEXT DEFAULT 'PENDING' -- PENDING, COMPLETED, FAILED
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS agent_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_summary TEXT,
        successful_actions INTEGER,
        failed_actions INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()
    console.print("[bold green][+] Hedefli Gorevler ve Yonetici Ajan tablolari basariyla olusturuldu![/bold green]")

if __name__ == "__main__":
    init_task_tables()
