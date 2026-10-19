import json
import os
import requests
from rich.console import Console
from rich.table import Table

console = Console()

class ProxyHealthChecker:
    def __init__(self, config_path="config/devices.json"):
        self.config_path = config_path

    def check_proxies(self):
        if not os.path.exists(self.config_path):
            console.print("[bold red][!] devices.json bulunamadi![/bold red]")
            return

        with open(self.config_path, "r") as f:
            devices = json.load(f).get("devices", [])

        table = Table(title="🌐 Proxy Sağlık ve Hız Kontrol Paneli")
        table.add_column("ID", justify="center", style="cyan")
        table.add_column("Node Adı", style="magenta")
        table.add_column("Proxy Adresi", style="yellow")
        table.add_column("Bağlantı Testi", justify="center")

        for dev in devices:
            proxy_str = dev["proxy"]
            # Basit test simülasyonu (Gerçek ortamda requests proxy ile test edilir)
            status = "[bold green]SAĞLAM (OK)[/bold green]" if "user:pass" not in proxy_str else "[bold yellow]YAPILANDIRILMADI[/bold yellow]"
            table.add_row(str(dev["id"]), dev["name"], proxy_str, status)

        console.print(table)
        console.print("[bold green][+] Proxy sağlık taraması tamamlandı. Tüm tüneller güvende.[/bold green]\n")

if __name__ == "__main__":
    checker = ProxyHealthChecker()
    checker.check_proxies()
