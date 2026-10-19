import json
import os
from adbutils import adb
from rich.console import Console
from rich.table import Table

console = Console()

class ProxyManager:
    def __init__(self, config_path="config/devices.json"):
        self.config_path = config_path

    def load_devices(self):
        if not os.path.exists(self.config_path):
            return []
        with open(self.config_path, "r") as f:
            return json.load(f).get("devices", [])

    def parse_proxy(self, proxy_str):
        try:
            if "://" not in proxy_str:
                return None
            protocol, rest = proxy_str.split("://", 1)
            auth, address = rest.rsplit("@", 1) if "@" in rest else (None, rest)
            user, password = auth.split(":", 1) if auth and ":" in auth else (None, None)
            host, port = address.split(":", 1)
            return {
                "protocol": protocol,
                "host": host,
                "port": int(port),
                "user": user,
                "password": password
            }
        except Exception:
            return None

    def display_proxy_table(self):
        devices = self.load_devices()
        table = Table(title="AutoFarm-20 Proxy ve Ag Yonetim Paneli")
        table.add_column("ID", justify="center", style="cyan")
        table.add_column("Node Adi", style="magenta")
        table.add_column("Yerel IP", style="white")
        table.add_column("Atanan Proxy", style="yellow")
        table.add_column("Durum", justify="center", style="bold green")

        for dev in devices:
            table.add_row(str(dev["id"]), dev["name"], dev["local_ip"], dev["proxy"], "Konfigure Edildi")
        console.print(table)

if __name__ == "__main__":
    pm = ProxyManager()
    pm.display_proxy_table()
