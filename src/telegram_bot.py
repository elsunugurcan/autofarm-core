import sqlite3
from rich.console import Console

console = Console()
DB_PATH = "autofarm.db"

class TelegramNotifier:
    @staticmethod
    def send_alert(message):
        # Gerçek ortamda buraya Telegram Bot Token ve Chat ID ile istek atılır
        console.print(f"[bold magenta][TELEGRAM BİLDİRİMİ] 📲 {message}[/bold magenta]")

    @staticmethod
    def get_quick_status():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM devices")
        devices = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM fb_accounts")
        accounts = c.fetchone()[0]
        conn.close()
        return f"🤖 AutoFarm-20 Durum:\n- Toplam Cihaz: {devices}\n- Kayıtlı Hesap: {accounts}\n- Durum: Aktif ve Çalışıyor ✅"

if __name__ == "__main__":
    console.print(TelegramNotifier.get_quick_status())
