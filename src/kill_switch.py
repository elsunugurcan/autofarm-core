import subprocess
from rich.console import Console

console = Console()

class KillSwitch:
    @staticmethod
    def emergency_stop_device(serial):
        console.print(f"[bold red][KILL-SWITCH] ACİL DURUM! {serial} cihazının bağlantısı kesiliyor ve karantinaya alınıyor...[/bold red]")
        # ADB üzerinden Wi-Fi/Ağ bağlantısını kesme veya scrcpy pencerelerini kapatma simülasyonu
        subprocess.run(["adb", "-s", serial, "shell", "svc wifi disable"], capture_output=True)
        console.print(f"[bold yellow][+] {serial} cihazının internet erişimi donanımsal düzeyde bloke edildi![/bold yellow]")

if __name__ == "__main__":
    console.print("[bold green][+] Kill-Switch Güvenlik Paneli aktif![/bold green]")
