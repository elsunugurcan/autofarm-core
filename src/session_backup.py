import os
from rich.console import Console

console = Console()

class SessionManager:
    @staticmethod
    def backup_session(device_serial, app_package="com.facebook.katana"):
        backup_dir = f"backups/{device_serial}"
        os.makedirs(backup_dir, exist_ok=True)
        
        # ADB backup veya veri çekme simülasyonu
        console.print(f"[bold green][BACKUP] {device_serial} ({app_package}) oturum verileri yedeklendi -> {backup_dir}[/bold green]")

    @staticmethod
    def restore_session(device_serial, app_package="com.facebook.katana"):
        console.print(f"[bold yellow][RESTORE] {device_serial} için yedeklenen oturum verileri geri yükleniyor...[/bold yellow]")

if __name__ == "__main__":
    SessionManager.backup_session("NODE_01_TEST")
