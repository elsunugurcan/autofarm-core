import random
from rich.console import Console

console = Console()

class AICommenter:
    # Genişletilebilir özgün yorum havuzu ve yapay zeka jeneratör simülasyonu
    COMMENT_TEMPLATES = [
        "Harika bir paylaşım olmuş, tebrikler! 🚀",
        "Çok başarılı buldum, ellerine sağlık 👏",
        "Bu konuya tamamen katılıyorum, harika!",
        "Kesinlikle çok doğru bir yaklaşım ✨",
        "Başarılarının devamını dilerim, süper! 🔥"
    ]

    @staticmethod
    def generate_comment(context="general"):
        # İleride buraya OpenAI / Claude API entegrasyonu bağlanabilir
        comment = random.choice(AICommenter.COMMENT_TEMPLATES)
        return comment

if __name__ == "__main__":
    console.print(f"[bold cyan][AI COMMENTER] Üretilen Özgün Yorum:[/bold cyan] {AICommenter.generate_comment()}")
