import time
import uiautomator2 as u2
from rich.console import Console
from humanizer import Humanizer

console = Console()

class FacebookBot:
    def __init__(self, serial, app_package="com.facebook.katana"):
        self.serial = serial
        self.app_package = app_package
        self.d = None

    def connect_device(self):
        try:
            console.print(f"[cyan]Cihaza baglaniliyor:[/cyan] {self.serial}")
            self.d = u2.connect(self.serial)
            self.d.screen_on()
            return True
        except Exception as e:
            console.print(f"[bold red]Baglanti Hatasi ({self.serial}):[/bold red] {e}")
            return False

    def warmup_session(self, loops=3):
        if not self.connect_device():
            return

        console.print(f"[green]Facebook Uygulamasi Aciliyor:[/green] {self.app_package}")
        self.d.app_start(self.app_package)
        Humanizer.wait(4.0, 6.0)

        console.print("[yellow]Akis uzerinde insansi gezinti baslatiliyor...[/yellow]")
        for i in range(1, loops + 1):
            wait_time = Humanizer.wait(3.0, 5.0)
            Humanizer.swipe_up_feed(self.d)
            console.print(f"[magenta][FB Bot - {self.serial}][/magenta] Islem {i}/{loops} yapildi (Bekleme: {wait_time}sn)")

        console.print(f"[bold green][+] Facebook warmup oturumu bitti: {self.serial}[/bold green]")

if __name__ == "__main__":
    console.print("[bold blue]src/fb_bot.py modulu yuklendi ve kullanima hazir![/bold blue]")
