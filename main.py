import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from rich.console import Console
from rich.panel import Panel
from fleet_manager import check_fleet_status
from database import init_db, show_accounts
from proxy_manager import ProxyManager
import runner

console = Console()

def show_menu():
    console.print(Panel.fit("[bold cyan]🤖 AutoFarm-20 Ana Komuta Merkezi (Facebook Mimarisi)[/bold cyan]", border_style="green"))
    console.print("[1] 🚀 Filo Cihaz Durumunu Kontrol Et (Online/Offline)")
    console.print("[2] 📊 SQLite Veritabani ve Facebook Hesaplarini Listele")
    console.print("[3] 🌐 Proxy ve Ag Yonetim Panolini Goruntule")
    console.print("[4] 🤖 Facebook Paralel Isinma Botunu Calistir (Runner)")
    console.print("[5] 🚪 Cikis\n")

def main():
    init_db()
    while True:
        show_menu()
        choice = console.input("[bold yellow]Seciminiz (1-5): [/bold yellow]")
        
        if choice == "1":
            console.print("\n--- FİLO DURUMU ---")
            check_fleet_status()
        elif choice == "2":
            console.print("\n--- VERİTABANI VE HESAPLAR ---")
            show_accounts()
        elif choice == "3":
            console.print("\n--- PROXY YÖNETİMİ ---")
            pm = ProxyManager()
            pm.display_proxy_table()
        elif choice == "4":
            console.print("\n--- FACEBOOK OTOMASYON MOTORU ---")
            runner.start_fleet_job()
        elif choice == "5":
            console.print("[bold red]Sistemden cikiliyor. Gorusmek uzere![/bold red]")
            sys.exit(0)
        else:
            console.print("[bold red]Gecersiz secim, lutfen 1-5 arasi bir deger girin.[/bold red]")
        
        console.input("\nDevam etmek icin [bold cyan]Enter[/bold cyan] tusuna basin...")

if __name__ == "__main__":
    main()
