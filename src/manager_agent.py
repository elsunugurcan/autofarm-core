import sqlite3
from rich.console import Console
from rich.panel import Panel

console = Console()
DB_PATH = "autofarm.db"

class ManagerAgent:
    @staticmethod
    def get_fleet_report():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM devices")
        total_devices = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM fb_accounts")
        total_accounts = c.fetchone()[0]
        
        c.execute("SELECT status, COUNT(*) FROM targeted_tasks GROUP BY status")
        task_stats = dict(c.fetchall())
        
        conn.close()
        
        report_text = f"""
📊 [bold cyan]YÖNETİCİ AJAN - FİLO DURUM RAPORU[/bold cyan]
--------------------------------------------------
🔹 Toplam Donanım Kapasitesi : {total_devices} Cihaz
🔹 Kayıtlı Facebook Hesabı   : {total_accounts} Adet
🔹 Bekleyen Hedefli Görev   : {task_stats.get('PENDING', 0)}
🔹 Tamamlanan Görevler      : {task_stats.get('COMPLETED', 0)}
🔹 Başarısız / Hata Alan    : {task_stats.get('FAILED', 0)}
--------------------------------------------------
🤖 [green]Ajan Durumu: Filo kararlı çalışıyor. Görev ataması bekleniyor.[/green]
        """
        return report_text

if __name__ == "__main__":
    console.print(Panel.fit(ManagerAgent.get_fleet_report(), border_style="cyan"))
