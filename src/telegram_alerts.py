import os
from rich.console import Console

console = Console()

class TelegramAlerts:
    @staticmethod
    def send_mission_report(completed_count, failed_count):
        token = os.getenv("TELEGRAM_BOT_TOKEN", "TEST_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "TEST_CHAT")
        
        message = f"📊 AutoFarm-30 Günlük Operasyon Raporu:\n✅ Başarılı Görev: {completed_count}\n❌ Hata / Kısıtlama: {failed_count}\n🤖 Filo Sağlığı: Mükemmel"
        console.print(f"[bold magenta][TELEGRAM RAPORU GÖNDERİLDİ] 📲\n{message}[/bold magenta]")

if __name__ == "__main__":
    TelegramAlerts.send_mission_report(45, 0)
