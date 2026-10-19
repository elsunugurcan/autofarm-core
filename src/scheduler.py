import time
import schedule
from rich.console import Console
from runner import start_fleet_job

console = Console()

def scheduled_facebook_job():
    console.print("[bold magenta][ZAMANLAYICI] Otomatik Facebook Isinma Gorevi Tetiklendi![/bold magenta]")
    try:
        start_fleet_job()
        console.print("[bold green][ZAMANLAYICI] Gorev basariyla tamamlandi ve dinlenmeye gecildi.[/bold green]")
    except Exception as e:
        console.print(f"[bold red][ZAMANLAYICI HATA] {e}[/bold red]")

def run_scheduler_loop():
    console.print("[bold cyan]🤖 AutoFarm-20 Akıllı Zamanlayıcı (Scheduler) Aktif Edildi...[/bold cyan]")
    # Örnek: Her 30 dakikada bir otomatik ısındırma döngüsü tetikler
    schedule.every(30).minutes.do(scheduled_facebook_job)
    
    # Test için günlük belirli saat örneği (İsteğe göre ayarlanabilir)
    # schedule.every().day.at("09:00").do(scheduled_facebook_job)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    run_scheduler_loop()
