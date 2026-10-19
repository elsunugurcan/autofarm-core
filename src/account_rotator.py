import sqlite3
from rich.console import Console

console = Console()
DB_PATH = "autofarm.db"

class AccountRotator:
    @staticmethod
    def get_next_active_account(device_id):
        """
        Belirtilen cihazda sıradaki aktif Facebook hesabını seçer ve döndürür (Account Rotation).
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Cihaza ait ACTIVE durumdaki hesapları getir
        c.execute("SELECT id, fb_username, app_package, profile_slot, warmup_level FROM fb_accounts WHERE device_id = ? AND status = 'ACTIVE' ORDER BY id ASC", (device_id,))
        accounts = c.fetchall()
        conn.close()
        
        if not accounts:
            console.print(f"[bold yellow][ROTATOR] Cihaz ID {device_id} için aktif hesap bulunamadı![/bold yellow]")
            return None
            
        # Basit bir döngü mantığı (İleride son kullanılan hesaba göre sıradakini seçer)
        selected_account = accounts[0]
        console.print(f"[bold green][ROTATOR] Cihaz ID {device_id} için hesap yüklendi: {selected_account[1]} ({selected_account[3]})[/bold green]")
        return {
            "account_id": selected_account[0],
            "username": selected_account[1],
            "app_package": selected_account[2],
            "profile_slot": selected_account[3],
            "warmup_level": selected_account[4]
        }

if __name__ == "__main__":
    console.print("[bold cyan][+] Account Rotator modülü aktif![/bold cyan]")
    AccountRotator.get_next_active_account(1)
