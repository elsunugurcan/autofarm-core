import sqlite3
import random
import uuid
from humanizer import Persona
from organic_brain import PersonaCommentBrain

DB_PATH = "autofarm.db"


class CampaignDistributor:
    @staticmethod
    def ensure_schema():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS targeted_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER,
            post_link TEXT,
            action_type TEXT,
            comment_text TEXT,
            status TEXT DEFAULT 'PENDING'
        )""")
        # Yeni kampanya sutunlarini guvenli sekilde ekle
        for col_def in [
            "ALTER TABLE targeted_tasks ADD COLUMN campaign_code TEXT DEFAULT 'SINGLE'",
            "ALTER TABLE targeted_tasks ADD COLUMN delay_sec INTEGER DEFAULT 0",
            "ALTER TABLE targeted_tasks ADD COLUMN persona_name TEXT DEFAULT ''"
        ]:
            try:
                c.execute(col_def)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    @staticmethod
    def create_campaign(
        post_link: str,
        node_count: int = 30,
        mix_mode: str = "ORGANIC_MIX",
        speed_mode: str = "FAST_SIM",
        base_comment: str = ""
    ):
        CampaignDistributor.ensure_schema()
        campaign_code = f"CMP-{uuid.uuid4().hex[:5].upper()}"

        # 1..30 arasindan rastgele cihaz sec ve siralamayi tamamen karistir
        all_nodes = list(range(1, 31))
        selected_nodes = random.sample(all_nodes, min(node_count, 30))

        # Zaman yayilim araligi (min_gap, max_gap saniye)
        if speed_mode == "FAST_SIM":
            gap_range = (3, 12)
        elif speed_mode == "NATURAL_WAVE":
            gap_range = (25, 95)
        else:
            gap_range = (120, 420)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        cumulative_delay = 0
        created_tasks = []

        for idx, dev_id in enumerate(selected_nodes):
            if idx > 0:
                cumulative_delay += random.randint(gap_range[0], gap_range[1])

            persona = Persona.get_for_device(dev_id)

            # Etkilesim tipini belirle
            if mix_mode == "ALL_COMMENT":
                act_type = "COMMENT"
            elif mix_mode == "ALL_LIKE":
                act_type = "LIKE"
            else:
                # Organik Karisim: %40 Yorum+Begeni, %60 Sadece Begeni
                act_type = "COMMENT" if random.random() < 0.40 else "LIKE"

            comment_txt = ""
            if act_type == "COMMENT":
                comment_txt = PersonaCommentBrain.craft_comment(dev_id, base_comment)

            c.execute(
                """INSERT INTO targeted_tasks
                   (device_id, post_link, action_type, comment_text, status, campaign_code, delay_sec, persona_name)
                   VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?)""",
                (dev_id, post_link, act_type, comment_txt, campaign_code, cumulative_delay, persona["name"])
            )
            created_tasks.append((dev_id, act_type, cumulative_delay, persona["name"], comment_txt))

        conn.commit()
        conn.close()
        return campaign_code, created_tasks

    @staticmethod
    def clear_completed_tasks():
        CampaignDistributor.ensure_schema()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM targeted_tasks WHERE status = 'COMPLETED'")
        conn.commit()
        conn.close()
