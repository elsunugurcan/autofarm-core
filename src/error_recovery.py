import sqlite3
from rich.console import Console

console = Console()
DB_PATH = "autofarm.db"

class ErrorRecovery:
    @staticmethod
    def handle_account_restriction(account_id, error_message="Action Block Detected"):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Hesabın durumunu RESTRICTED olarak güncelle
        c.execute("UPDATE fb_accounts SET status = 'RESTRICTED' WHERE id = ?", (account_id,))
        
        # Log kaydı düş
        c.execute("INSERT INTO action_logs (account_id, action_type, details) VALUES (?, ?, ?)", 
                  (account_id, 'ERROR_RECOVERY', error_message))
        
        conn.commit()
        conn.close()
        
        console.print(f"[bold red][ERROR RECOVERY] Hesap ID {account_id} kısıtlandı! Güvenli moda alındı ve karantinaya eklendi: {error_message}[/bold red]")

if __name__ == "__main__":
    console.print("[bold green][+] Error Recovery modülü aktif ve devrede![/bold green]")
