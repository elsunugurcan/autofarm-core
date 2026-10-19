import sqlite3
from rich.console import Console
from rich.panel import Panel

console = Console()
DB_PATH = "autofarm.db"

class LogAnalytics:
    @staticmethod
    def analyze_system_logs():
        if not sqlite3.connect(DB_PATH):
            return "Veritabanı bulunamadı."
            
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Toplam işlem sayısı ve hata analizi
        c.execute("SELECT COUNT(*) FROM targeted_tasks")
        total_tasks = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM targeted_tasks WHERE status = 'FAILED'")
        failed_tasks = c.fetchone()[0]
        
        # Son hata logları
        c.execute("SELECT action_type, details, created_at FROM action_logs ORDER BY id DESC LIMIT 5")
        recent_logs = c.fetchall()
        
        conn.close()
        
        error_rate = (failed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0
        
        report = f"""
📈 [bold cyan]SİSTEM LOG ANALİTİĞİ VE ANOMALİ RAPORU[/bold cyan]
--------------------------------------------------
🔹 Toplam İşlenen Görev   : {total_tasks}
🔹 Başarısız Görev Sayısı : {failed_tasks}
🔹 Genel Hata Oranı       : {error_rate:.2f}%
--------------------------------------------------
🔍 [bold yellow]Son Kritik Loglar:[/bold yellow]
        """
        for log in recent_logs:
            report += f"\n  • [{log[2]}] {log[0]}: {log[1]}"
            
        if error_rate > 15.0:
            report += "\n\n🚨 [bold red]ANOMALİ TESPİT EDİLDİ: Hata oranı yüksek! Proxy veya hesap durumlarını kontrol edin.[/bold red]"
        else:
            report += "\n\n✅ [bold green]Anomali Yok: Filo kararlı ve sağlıklı çalışıyor.[/bold green]"
            
        return report

if __name__ == "__main__":
    console.print(Panel.fit(LogAnalytics.analyze_system_logs(), border_style="cyan"))
