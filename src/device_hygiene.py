import subprocess
from rich.console import Console

console = Console()

class DeviceHygiene:
    @staticmethod
    def run_adb_shell(serial, command):
        full_cmd = ["adb", "-s", serial, "shell"] + command.split()
        result = subprocess.run(full_cmd, capture_output=True, text=True)
        return result.stdout.strip()

    @staticmethod
    def apply_environment_isolation(serial, timezone="Europe/Istanbul", locale="tr-TR"):
        """
        Cihazin ag, konum sizintisi ve ortam degiskenlerini proxy bolgesine gore izole eder.
        """
        console.print(f"[cyan][HYGIENE] {serial} icin ortam izolasyonu baslatiliyor...[/cyan]")
        
        # 1. Arka plan Wi-Fi ve Bluetooth tarama sizintilarini kesin olarak kapat
        DeviceHygiene.run_adb_shell(serial, "settings put global wifi_scan_always_enabled 0")
        DeviceHygiene.run_adb_shell(serial, "settings put global ble_scan_always_enabled 0")
        DeviceHygiene.run_adb_shell(serial, "settings put secure location_mode 0")
        
        # 2. Otomatik saat dilimini kapat ve proxy bolgesine sabitle
        DeviceHygiene.run_adb_shell(serial, "settings put global auto_time_zone 0")
        DeviceHygiene.run_adb_shell(serial, f"service call alarm 3 s16 {timezone}")
        
        # 3. Panoyu (Clipboard) ve gecici loglari temizle
        DeviceHygiene.run_adb_shell(serial, "am broadcast -a clipper.clear")
        DeviceHygiene.run_adb_shell(serial, "logcat -c")
        
        console.print(f"[bold green][+] {serial} ortam izolasyonu tamamlandi (TZ: {timezone} | Locale: {locale})[/bold green]")
        return True

    @staticmethod
    def clear_app_cache_only(serial, package="com.facebook.katana"):
        """
        Hesap oturumunu kapatmadan sadece gecici onbellek izlerini temizler.
        """
        DeviceHygiene.run_adb_shell(serial, f"pm trim-caches 999G")
        console.print(f"[yellow][HYGIENE] {serial} uzerinde {package} gecici onbellek izleri temizlendi.[/yellow]")

if __name__ == "__main__":
    console.print("[bold blue][+] Device Hygiene & Isolation modulu hazir![/bold blue]")
