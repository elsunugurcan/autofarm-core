import json, os
from adbutils import adb
from rich.console import Console
from rich.table import Table

console = Console()

def check_fleet_status():
    with open("config/devices.json", "r") as f:
        data = json.load(f)

    connected_serials = [d.serial for d in adb.device_list()]

    table = Table(title="AutoFarm-20 Filo Durum Paneli")
    table.add_column("ID", justify="center", style="cyan")
    table.add_column("Node Adi", style="magenta")
    table.add_column("Seri No / IP", style="white")
    table.add_column("Proxy", style="yellow")
    table.add_column("Durum", justify="center")

    online_count = 0
    for dev in data.get("devices", []):
        is_online = dev["serial"] in connected_serials or f"{dev["local_ip"]}:5555" in connected_serials
        if is_online:
            online_count += 1
            status = "[bold green]ONLINE[/bold green]"
        else:
            status = "[dim red]OFFLINE[/dim red]"
        table.add_row(str(dev["id"]), dev["name"], dev["serial"], dev["proxy"], status)

    console.print(table)
    console.print(f"\n[bold cyan]Toplam Aktif Cihaz:[/bold cyan] {online_count} / {len(data.get("devices", []))}\n")

if __name__ == "__main__":
    check_fleet_status()
