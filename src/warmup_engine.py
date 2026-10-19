import sqlite3
from rich.console import Console

console = Console()
DB_PATH = "autofarm.db"

class WarmupEngine:
    @staticmethod
    def get_account_policy(account_id):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT warmup_level, daily_likes FROM fb_accounts WHERE id = ?", (account_id,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            return {"level": 1, "can_comment": False, "max_likes": 5}
            
        level, likes = row
        if level == 1:
            return {"level": 1, "can_comment": False, "max_likes": 10, "mode": "Ghost Mode (Sadece Gezinti)"}
        elif level == 2:
            return {"level": 2, "can_comment": True, "max_likes": 25, "mode": "Interaction Mode (Sinirli Yorum)"}
        else:
            return {"level": 3, "can_comment": True, "max_likes": 60, "mode": "Full Power (Tam Otomasyon)"}

if __name__ == "__main__":
    console.print("[bold cyan][+] Warmup Engine modülü aktif![/bold cyan]")
