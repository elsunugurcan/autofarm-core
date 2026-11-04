import sys
import os
import json
import sqlite3
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QTextEdit,
    QStackedWidget, QHeaderView, QLineEdit, QComboBox, QMessageBox,
    QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import init_db
from manager_agent import ManagerAgent
from humanizer import Humanizer, Persona
from campaign_manager import CampaignDistributor

DB_PATH = "autofarm.db"


def ensure_30_nodes_config():
    os.makedirs("config", exist_ok=True)
    config_path = "config/devices.json"
    devices = []
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                devices = json.load(f).get("devices", [])
        except Exception:
            devices = []
    if len(devices) < 30:
        devices = []
        for i in range(1, 31):
            serial = "TKUW99U8QCNNJ7RC" if i == 1 else f"BEKLIYOR_NODE_{i:02d}"
            devices.append({
                "id": i,
                "name": f"node-{i:02d}",
                "serial": serial,
                "local_ip": f"192.168.1.{100+i}",
                "proxy": f"socks5://user:pass@127.0.0.1:{1080+i}"
            })
        with open(config_path, "w") as f:
            json.dump({"devices": devices}, f, indent=2)


class BotRunnerThread(QThread):
    log_signal = pyqtSignal(str)

    def run(self):
        self.log_signal.emit("[ENGINE] 🚀 Kampanya ve Biyometrik görev motoru başlatıldı...")
        process = subprocess.Popen(
            [sys.executable, "src/runner.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in iter(process.stdout.readline, ""):
            if line:
                self.log_signal.emit(line.strip())
        process.stdout.close()
        process.wait()
        self.log_signal.emit("[ENGINE] ✅ Tüm biyometrik görev döngüsü tamamlandı.")


class StatCard(QFrame):
    def __init__(self, title, value, subtitle, accent_color="#38bdf8"):
        super().__init__()
        self.setObjectName("StatCard")
        self.setStyleSheet(f"""
            QFrame#StatCard {{
                background-color: #121217;
                border: 1px solid #232329;
                border-top: 3px solid {accent_color};
                border-radius: 12px;
                padding: 14px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        lbl_title = QLabel(title.upper())
        lbl_title.setStyleSheet("color: #71717a; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; border: none; background: transparent;")

        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet("color: #f4f4f5; font-size: 24px; font-weight: 800; border: none; background: transparent;")

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet(f"color: {accent_color}; font-size: 11px; font-weight: 600; border: none; background: transparent;")

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_sub)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoFarm-30 // Enterprise Biometric Command Center")
        self.setGeometry(60, 40, 1520, 920)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #09090b;
                color: #e4e4e7;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 13px;
            }
            #Sidebar {
                background-color: #0e0e12;
                border-right: 1px solid #1f1f26;
                min-width: 255px;
                max-width: 255px;
            }
            #BrandBox {
                background-color: #14141b;
                border: 1px solid #262633;
                border-radius: 12px;
                padding: 12px;
            }
            QPushButton#NavBtn {
                background-color: transparent;
                color: #a1a1aa;
                border: 1px solid transparent;
                text-align: left;
                padding: 12px 16px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#NavBtn:hover {
                background-color: #16161e;
                color: #ffffff;
                border: 1px solid #272732;
            }
            QPushButton#NavBtnActive {
                background-color: #1d283a;
                color: #38bdf8;
                border: 1px solid #0284c7;
                text-align: left;
                padding: 12px 16px;
                border-radius: 10px;
                font-weight: 700;
                font-size: 13px;
            }
            QFrame#PanelCard {
                background-color: #121217;
                border: 1px solid #232329;
                border-radius: 12px;
            }
            QPushButton {
                background-color: #18181f;
                color: #f4f4f5;
                border: 1px solid #2e2e38;
                padding: 10px 18px;
                border-radius: 8px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #272733;
                border-color: #38bdf8;
            }
            QPushButton#BtnEmerald { background-color: #059669; color: #ffffff; border: 1px solid #10b981; }
            QPushButton#BtnEmerald:hover { background-color: #10b981; }
            QPushButton#BtnIndigo { background-color: #4f46e5; color: #ffffff; border: 1px solid #6366f1; }
            QPushButton#BtnIndigo:hover { background-color: #6366f1; }
            QPushButton#BtnAmber { background-color: #d97706; color: #ffffff; border: 1px solid #f59e0b; }
            QPushButton#BtnAmber:hover { background-color: #f59e0b; }
            QPushButton#BtnRose { background-color: #e11d48; color: #ffffff; border: 1px solid #f43f5e; }
            QPushButton#BtnRose:hover { background-color: #f43f5e; }
            QTableWidget {
                background-color: #0d0d11;
                gridline-color: #1e1e26;
                border: 1px solid #232329;
                border-radius: 10px;
                color: #e4e4e7;
                selection-background-color: #1d4ed8;
            }
            QHeaderView::section {
                background-color: #16161d;
                color: #9ca3af;
                padding: 10px;
                border: none;
                border-bottom: 1px solid #272730;
                font-weight: 700;
                font-size: 11px;
            }
            QTextEdit, QLineEdit, QComboBox {
                background-color: #0b0b0e;
                color: #34d399;
                border: 1px solid #252530;
                border-radius: 8px;
                font-family: "Menlo", "Monaco", "Courier New", monospace;
                padding: 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #38bdf8;
            }
        """)

        ensure_30_nodes_config()
        init_db()
        CampaignDistributor.ensure_schema()
        self.nav_buttons = []
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # SOL SIDEBAR
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 20, 16, 20)
        sb_layout.setSpacing(8)

        brand = QFrame()
        brand.setObjectName("BrandBox")
        b_layout = QVBoxLayout(brand)
        b_layout.setContentsMargins(10, 8, 10, 8)
        b_title = QLabel("⚡ AUTOFARM-30")
        b_title.setStyleSheet("color: #38bdf8; font-size: 17px; font-weight: 900; background: transparent; border: none;")
        b_sub = QLabel("Biometric Campaign Suite v4.0")
        b_sub.setStyleSheet("color: #71717a; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        b_layout.addWidget(b_title)
        b_layout.addWidget(b_sub)
        sb_layout.addWidget(brand)
        sb_layout.addSpacing(8)

        menu_items = [
            ("🏠  Genel Bakış (Dashboard)", 0),
            ("🎯  Kampanya Dağıtıcı (30 Node)", 1),
            ("🧬  Biyometrik Persona & DNA", 2),
            ("📱  Filo & Cihaz Yönetimi", 3),
            ("🌐  Proxy & Tünel İzolasyonu", 4),
            ("👥  Facebook Hesap CRM", 5),
        ]
        for text, idx in menu_items:
            btn = QPushButton(text)
            btn.setObjectName("NavBtnActive" if idx == 0 else "NavBtn")
            btn.clicked.connect(lambda checked, i=idx: self.switch_page(i))
            sb_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sb_layout.addStretch()

        status_box = QFrame()
        status_box.setObjectName("PanelCard")
        st_layout = QVBoxLayout(status_box)
        st_lbl1 = QLabel("🟢 DRIP-FEED MOTORU: AKTİF")
        st_lbl1.setStyleSheet("color: #4ade80; font-weight: 800; font-size: 11px; background: transparent; border: none;")
        st_lbl2 = QLabel("• Rastgele Node Sıralaması\n• Organik Sandviç Oturumu\n• Pil & Sıcaklık Kalkanı")
        st_lbl2.setStyleSheet("color: #a1a1aa; font-size: 11px; background: transparent; border: none;")
        st_layout.addWidget(st_lbl1)
        st_layout.addWidget(st_lbl2)
        sb_layout.addWidget(status_box)

        root_layout.addWidget(sidebar)

        # SAĞ ANA EKRAN
        main_area = QWidget()
        main_v = QVBoxLayout(main_area)
        main_v.setContentsMargins(24, 24, 24, 24)
        main_v.setSpacing(18)

        bio = Humanizer.get_circadian_status()
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(16)
        self.card_nodes = StatCard("Filo & Persona", "30 Node", "Her Cihazda Benzersiz DNA", "#38bdf8")
        self.card_accounts = StatCard("Kayıtlı FB Hesabı", "3 Aktif", "Çoklu Profil Rotasyonu", "#a855f7")
        self.card_tasks = StatCard("Kuyruktaki Görev", "0 Görev", "Drip-Feed Dalga Hazır", "#10b981")
        self.card_bio = StatCard("Biyolojik Saat Fazı", bio["phase"], f"Aktiflik: %{int(bio['activity_prob']*100)} | Yorgunluk: x{bio['fatigue_mult']}", "#f59e0b")

        kpi_layout.addWidget(self.card_nodes)
        kpi_layout.addWidget(self.card_accounts)
        kpi_layout.addWidget(self.card_tasks)
        kpi_layout.addWidget(self.card_bio)
        main_v.addLayout(kpi_layout)

        self.stack = QStackedWidget()
        main_v.addWidget(self.stack)

        self.page_dash = QWidget()
        self.page_agent = QWidget()
        self.page_persona = QWidget()
        self.page_fleet = QWidget()
        self.page_proxy = QWidget()
        self.page_accounts = QWidget()

        self.init_dashboard_page()
        self.init_agent_page()
        self.init_persona_page()
        self.init_fleet_page()
        self.init_proxy_page()
        self.init_accounts_page()

        self.stack.addWidget(self.page_dash)
        self.stack.addWidget(self.page_agent)
        self.stack.addWidget(self.page_persona)
        self.stack.addWidget(self.page_fleet)
        self.stack.addWidget(self.page_proxy)
        self.stack.addWidget(self.page_accounts)

        root_layout.addWidget(main_area)
        self.refresh_kpis()

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setObjectName("NavBtnActive" if i == index else "NavBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.refresh_kpis()
        if index == 1:
            self.load_campaign_queue_table()

    def refresh_kpis(self):
        if not os.path.exists(DB_PATH):
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM fb_accounts")
        acc_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM targeted_tasks WHERE status='PENDING'")
        pending_count = c.fetchone()[0]
        conn.close()
        self.card_accounts.lbl_value.setText(f"{acc_count} Hesap")
        self.card_tasks.lbl_value.setText(f"{pending_count} Görev")

    def init_dashboard_page(self):
        layout = QVBoxLayout(self.page_dash)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        action_card = QFrame()
        action_card.setObjectName("PanelCard")
        act_layout = QHBoxLayout(action_card)
        act_layout.setContentsMargins(16, 14, 16, 14)
        act_layout.setSpacing(12)

        lbl_act = QLabel("⚡ Hızlı Komuta:")
        lbl_act.setStyleSheet("font-weight: 800; color: #f4f4f5; background: transparent; border: none;")
        act_layout.addWidget(lbl_act)

        self.btn_start_bot = QPushButton("🚀 Kampanya & Biyometrik Motoru Başlat")
        self.btn_start_bot.setObjectName("BtnEmerald")
        self.btn_start_bot.clicked.connect(self.start_bot_process)
        act_layout.addWidget(self.btn_start_bot)

        btn_go_cmp = QPushButton("🎯 Yeni 30-Node Kampanya Oluştur")
        btn_go_cmp.setObjectName("BtnIndigo")
        btn_go_cmp.clicked.connect(lambda: self.switch_page(1))
        act_layout.addWidget(btn_go_cmp)

        btn_grid = QPushButton("🎛️ Tüm Ekranları Aç (Scrcpy)")
        btn_grid.clicked.connect(self.open_all_scrcpy)
        act_layout.addWidget(btn_grid)

        btn_tg = QPushButton("📲 Telegram Özeti")
        btn_tg.setObjectName("BtnAmber")
        btn_tg.clicked.connect(self.send_telegram_alert)
        act_layout.addWidget(btn_tg)

        btn_kill = QPushButton("🚨 Acil Kill-Switch")
        btn_kill.setObjectName("BtnRose")
        btn_kill.clicked.connect(self.trigger_kill_switch)
        act_layout.addWidget(btn_kill)

        act_layout.addStretch()
        layout.addWidget(action_card)

        split_layout = QHBoxLayout()
        split_layout.setSpacing(16)

        log_card = QFrame()
        log_card.setObjectName("PanelCard")
        log_v = QVBoxLayout(log_card)
        log_lbl = QLabel("🖥️ Canlı Kampanya, Sandviç Akışı & Telemetri Konsolu")
        log_lbl.setStyleSheet("font-weight: 700; color: #38bdf8; background: transparent; border: none;")
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.append("[SYSTEM] AutoFarm-30 Biometric Campaign Suite v4.0 yüklendi.")
        self.log_console.append("[DRIP-FEED] 30 Cihazlık Zaman Yayılımlı Kampanya Dağıtıcı hazır.")
        log_v.addWidget(log_lbl)
        log_v.addWidget(self.log_console)

        summary_card = QFrame()
        summary_card.setObjectName("PanelCard")
        sum_v = QVBoxLayout(summary_card)
        sum_lbl = QLabel("🤖 Yönetici Ajan Canlı Özeti")
        sum_lbl.setStyleSheet("font-weight: 700; color: #a855f7; background: transparent; border: none;")
        self.dash_agent_box = QTextEdit()
        self.dash_agent_box.setReadOnly(True)
        self.dash_agent_box.setStyleSheet("color: #e4e4e7;")
        self.dash_agent_box.setPlainText(ManagerAgent.get_fleet_report())
        sum_v.addWidget(sum_lbl)
        sum_v.addWidget(self.dash_agent_box)

        split_layout.addWidget(log_card, 3)
        split_layout.addWidget(summary_card, 2)
        layout.addLayout(split_layout)

    def init_agent_page(self):
        layout = QVBoxLayout(self.page_agent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        form_card = QFrame()
        form_card.setObjectName("PanelCard")
        f_v = QVBoxLayout(form_card)
        f_v.setContentsMargins(16, 14, 16, 14)
        f_v.setSpacing(10)

        lbl_head = QLabel("🚀 30-Cihaz Zaman Yayılımlı (Drip-Feed) Kampanya Dağıtıcı")
        lbl_head.setStyleSheet("color: #38bdf8; font-weight: 800; font-size: 14px; border: none; background: transparent;")
        f_v.addWidget(lbl_head)

        row1 = QHBoxLayout()
        self.input_link = QLineEdit()
        self.input_link.setPlaceholderText("Hedef Facebook Gönderi / Reels Linki (https://www.facebook.com/...)")
        self.input_comment = QLineEdit()
        self.input_comment.setPlaceholderText("Yorum Konsepti (Boş bırakırsanız her cihaz kendi Persona karakterine göre özgün üretir)")
        row1.addWidget(self.input_link, 2)
        row1.addWidget(self.input_comment, 2)
        f_v.addLayout(row1)

        row2 = QHBoxLayout()
        self.combo_node_count = QComboBox()
        self.combo_node_count.addItems([
            "5 Cihaz (Mini Dalga)",
            "10 Cihaz (Orta Dalga)",
            "20 Cihaz (Güçlü Dalga)",
            "30 Cihaz (Tam Filo Ordusu)"
        ])
        self.combo_node_count.setCurrentIndex(1)

        self.combo_mix_mode = QComboBox()
        self.combo_mix_mode.addItems([
            "Organik Karışım (%60 Beğeni + %40 Persona Yorum)",
            "Tam Etkileşim (%100 Beğeni + Persona Yorum)",
            "Sadece Beğeni (%100 Like Dalga)"
        ])

        self.combo_speed_mode = QComboBox()
        self.combo_speed_mode.addItems([
            "Hızlı Simülasyon (3-12 sn rastgele aralık)",
            "Doğal Dalga (25-95 sn rastgele aralık)",
            "Uzun Organik Yayılım (2-7 dk rastgele aralık)"
        ])

        btn_launch_cmp = QPushButton("🎯 Kampanyayı Filoya Dağıt")
        btn_launch_cmp.setObjectName("BtnEmerald")
        btn_launch_cmp.clicked.connect(self.launch_drip_campaign)

        btn_clear_cmp = QPushButton("🧹 Tamamlananları Temizle")
        btn_clear_cmp.clicked.connect(self.clear_completed_queue)

        row2.addWidget(self.combo_node_count, 1)
        row2.addWidget(self.combo_mix_mode, 2)
        row2.addWidget(self.combo_speed_mode, 2)
        row2.addWidget(btn_launch_cmp, 1)
        row2.addWidget(btn_clear_cmp, 1)
        f_v.addLayout(row2)
        layout.addWidget(form_card)

        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(7)
        self.queue_table.setHorizontalHeaderLabels([
            "GÖREV ID", "KAMPANYA", "ATANAN CİHAZ", "PERSONA DNA",
            "İŞLEM TİPİ", "ZAMANLAMA (DRIP-FEED)", "ÖZGÜN YORUM & DURUM"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.queue_table)
        self.load_campaign_queue_table()

    def launch_drip_campaign(self):
        link = self.input_link.text().strip()
        if not link:
            QMessageBox.warning(self, "Uyarı", "Lütfen hedef gönderi linkini girin!")
            return
        comment_hint = self.input_comment.text().strip()

        count_map = {0: 5, 1: 10, 2: 20, 3: 30}
        node_count = count_map.get(self.combo_node_count.currentIndex(), 10)

        mix_map = {0: "ORGANIC_MIX", 1: "ALL_COMMENT", 2: "ALL_LIKE"}
        mix_mode = mix_map.get(self.combo_mix_mode.currentIndex(), "ORGANIC_MIX")

        speed_map = {0: "FAST_SIM", 1: "NATURAL_WAVE", 2: "LONG_DRIP"}
        speed_mode = speed_map.get(self.combo_speed_mode.currentIndex(), "FAST_SIM")

        cmp_code, tasks = CampaignDistributor.create_campaign(
            post_link=link,
            node_count=node_count,
            mix_mode=mix_mode,
            speed_mode=speed_mode,
            base_comment=comment_hint
        )

        self.input_link.clear()
        self.input_comment.clear()
        self.load_campaign_queue_table()
        self.refresh_agent_report()
        self.refresh_kpis()
        self.log_console.append(
            f"[CAMPAIGN] 🚀 {cmp_code} oluşturuldu! {len(tasks)} cihaza rastgele sırayla ve zaman yayılımlı dağıtıldı."
        )

    def clear_completed_queue(self):
        CampaignDistributor.clear_completed_tasks()
        self.load_campaign_queue_table()
        self.refresh_agent_report()
        self.refresh_kpis()

    def load_campaign_queue_table(self):
        CampaignDistributor.ensure_schema()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """SELECT id, campaign_code, device_id, persona_name, action_type, delay_sec, comment_text, status
               FROM targeted_tasks
               ORDER BY status DESC, delay_sec ASC, id DESC"""
        )
        rows = c.fetchall()
        conn.close()

        self.queue_table.setRowCount(len(rows))
        for r_idx, (tid, cmp_code, dev_id, p_name, act, d_sec, c_txt, st) in enumerate(rows):
            self.queue_table.setItem(r_idx, 0, QTableWidgetItem(f"#{tid}"))
            self.queue_table.setItem(r_idx, 1, QTableWidgetItem(str(cmp_code or "SINGLE")))
            self.queue_table.setItem(r_idx, 2, QTableWidgetItem(f"node-{int(dev_id):02d}"))
            self.queue_table.setItem(r_idx, 3, QTableWidgetItem(str(p_name or "Standart")))
            self.queue_table.setItem(r_idx, 4, QTableWidgetItem("💬 YORUM + BEĞENİ" if act == "COMMENT" else "👍 SADECE BEĞENİ"))

            mins, secs = divmod(int(d_sec or 0), 60)
            time_str = f"T+{mins}dk {secs}sn" if mins > 0 else f"T+{secs}sn"
            self.queue_table.setItem(r_idx, 5, QTableWidgetItem(time_str))

            summary = f"[{st}] {c_txt}" if c_txt else f"[{st}] Organik Beğeni"
            item_st = QTableWidgetItem(summary)
            item_st.setForeground(QColor("#f59e0b" if st == "PENDING" else "#4ade80"))
            self.queue_table.setItem(r_idx, 6, item_st)

    def init_persona_page(self):
        layout = QVBoxLayout(self.page_persona)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        sim_card = QFrame()
        sim_card.setObjectName("PanelCard")
        sim_layout = QHBoxLayout(sim_card)
        sim_layout.setContentsMargins(14, 12, 14, 12)

        self.input_sim_text = QLineEdit()
        self.input_sim_text.setPlaceholderText("Canlı Klavye & Bézier Testi için örnek yorum yazın...")
        self.input_sim_text.setText("Harika bir paylasim olmus emeginize saglik!")
        btn_test_sim = QPushButton("🧬 Biyometrik Simülasyonu Test Et")
        btn_test_sim.setObjectName("BtnIndigo")
        btn_test_sim.clicked.connect(self.run_interactive_humanizer_test)

        sim_layout.addWidget(self.input_sim_text, 3)
        sim_layout.addWidget(btn_test_sim, 1)
        layout.addWidget(sim_card)

        self.lbl_sim_output = QLabel("💡 Yukarıdaki butona basarak klavye harf hatası (⌫) ve Bézier yay koordinatlarını canlı test edebilirsiniz.")
        self.lbl_sim_output.setStyleSheet("color: #34d399; font-family: Menlo, monospace; font-size: 12px; padding: 6px;")
        layout.addWidget(self.lbl_sim_output)

        self.persona_table = QTableWidget()
        self.persona_table.setColumnCount(7)
        self.persona_table.setHorizontalHeaderLabels([
            "NODE", "KARAKTER ARKETİPİ (PERSONA)", "BAŞPARMAK YÖNÜ",
            "HIZ ÇARPANI", "HARF HATASI (TYPO %)", "HIZLI GEÇİŞ (SKIP %)", "DOKUNMA SAPMASI (JITTER)"
        ])
        self.persona_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.persona_table)
        self.load_persona_table()

    def load_persona_table(self):
        self.persona_table.setRowCount(30)
        for i in range(1, 31):
            p = Persona.get_for_device(i)
            row = i - 1
            self.persona_table.setItem(row, 0, QTableWidgetItem(f"node-{i:02d}"))
            self.persona_table.setItem(row, 1, QTableWidgetItem(p["name"]))
            hand = "👉 SAĞLAK (RightArc)" if p["handedness"] == "RIGHT" else "👈 SOLAK (LeftArc)"
            self.persona_table.setItem(row, 2, QTableWidgetItem(hand))
            self.persona_table.setItem(row, 3, QTableWidgetItem(f"x{p['speed_mult']}"))
            self.persona_table.setItem(row, 4, QTableWidgetItem(f"%{int(p['typo_rate']*100)}"))
            self.persona_table.setItem(row, 5, QTableWidgetItem(f"%{int(p['skip_prob']*100)}"))
            self.persona_table.setItem(row, 6, QTableWidgetItem(f"±{p['jitter_px']} piksel"))

    def run_interactive_humanizer_test(self):
        sample = self.input_sim_text.text().strip() or "Harika paylasim!"
        seq = Humanizer.generate_typing_sequence(sample, typo_rate=0.16)
        stream = ""
        typos = 0
        for act, ch, _ in seq:
            if act == "TYPE_WRONG":
                stream += f"[{ch}?]"
                typos += 1
            elif act == "BACKSPACE":
                stream += "⌫"
            elif act == "TYPE_CHAR":
                stream += ch
        swp = Humanizer.swipe_up_feed(None, Persona.get_for_device(1))
        self.lbl_sim_output.setText(
            f"⌨️ Klavye Akışı ({typos} hata düzeltildi): {stream}   |   👆 Bézier Yay: {swp['start']} ➔ {swp['arc_midpoint']} ➔ {swp['end']} ({swp['duration_sec']}sn)"
        )

    def init_fleet_page(self):
        layout = QVBoxLayout(self.page_fleet)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        lbl = QLabel("📱 Fiziksel Cihaz Filosu (30 Node) ve ADB Bağlantı Durumu")
        lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #38bdf8;")
        btn_ref = QPushButton("🔄 Cihazları Yeniden Tara")
        btn_ref.clicked.connect(self.load_device_table)
        top.addWidget(lbl)
        top.addStretch()
        top.addWidget(btn_ref)
        layout.addLayout(top)

        self.device_table = QTableWidget()
        self.device_table.setColumnCount(5)
        self.device_table.setHorizontalHeaderLabels(["ID", "NODE ADI", "SERİ NO / IP", "ATANAN PROXY", "DURUM"])
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.device_table)
        self.load_device_table()

    def init_proxy_page(self):
        layout = QVBoxLayout(self.page_proxy)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("🌐 SOCKS5 Proxy Tüneli ve Ağ İzolasyon Tablosu")
        lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #38bdf8;")
        layout.addWidget(lbl)

        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(4)
        self.proxy_table.setHorizontalHeaderLabels(["ID", "NODE ADI", "YEREL IP", "SOCKS5 PROXY TÜNELİ"])
        self.proxy_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.proxy_table)
        self.load_proxy_table()

    def init_accounts_page(self):
        layout = QVBoxLayout(self.page_accounts)
        layout.setContentsMargins(0, 0, 0, 0)

        form_card = QFrame()
        form_card.setObjectName("PanelCard")
        form_layout = QHBoxLayout(form_card)
        self.input_acc_device = QLineEdit()
        self.input_acc_device.setPlaceholderText("Cihaz ID (1-30)")
        self.input_acc_name = QLineEdit()
        self.input_acc_name.setPlaceholderText("FB Kullanıcı Adı / Etiketi")
        self.combo_acc_pkg = QComboBox()
        self.combo_acc_pkg.addItems(["com.facebook.katana", "com.facebook.lite"])
        btn_add = QPushButton("➕ Yeni Hesap Ekle")
        btn_add.setObjectName("BtnEmerald")
        btn_add.clicked.connect(self.add_facebook_account)

        form_layout.addWidget(self.input_acc_device, 1)
        form_layout.addWidget(self.input_acc_name, 2)
        form_layout.addWidget(self.combo_acc_pkg, 1)
        form_layout.addWidget(btn_add)
        layout.addWidget(form_card)

        self.acc_table = QTableWidget()
        self.acc_table.setColumnCount(8)
        self.acc_table.setHorizontalHeaderLabels(["ID", "CİHAZ", "KULLANICI ADI", "PAKET", "PROFİL", "WARM-UP", "BEĞENİ", "DURUM"])
        self.acc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.acc_table)
        self.load_accounts_table()

    def load_device_table(self):
        config_path = "config/devices.json"
        if not os.path.exists(config_path):
            return
        with open(config_path, "r") as f:
            devices = json.load(f).get("devices", [])
        from adbutils import adb
        connected = [d.serial for d in adb.device_list()]
        self.device_table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            is_online = dev["serial"] in connected or f"{dev['local_ip']}:5555" in connected
            self.device_table.setItem(row, 0, QTableWidgetItem(str(dev["id"])))
            self.device_table.setItem(row, 1, QTableWidgetItem(dev["name"]))
            self.device_table.setItem(row, 2, QTableWidgetItem(dev["serial"]))
            self.device_table.setItem(row, 3, QTableWidgetItem(dev["proxy"]))
            st = QTableWidgetItem("● ONLINE" if is_online else "○ OFFLINE")
            st.setForeground(QColor("#4ade80" if is_online else "#f43f5e"))
            self.device_table.setItem(row, 4, st)

    def load_proxy_table(self):
        config_path = "config/devices.json"
        if not os.path.exists(config_path):
            return
        with open(config_path, "r") as f:
            devices = json.load(f).get("devices", [])
        self.proxy_table.setRowCount(len(devices))
        for row, dev in enumerate(devices):
            self.proxy_table.setItem(row, 0, QTableWidgetItem(str(dev["id"])))
            self.proxy_table.setItem(row, 1, QTableWidgetItem(dev["name"]))
            self.proxy_table.setItem(row, 2, QTableWidgetItem(dev["local_ip"]))
            self.proxy_table.setItem(row, 3, QTableWidgetItem(dev["proxy"]))

    def load_accounts_table(self):
        if not os.path.exists(DB_PATH):
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, device_id, fb_username, app_package, profile_slot, warmup_level, daily_likes, status FROM fb_accounts")
        rows = c.fetchall()
        conn.close()
        self.acc_table.setRowCount(len(rows))
        for r_idx, r in enumerate(rows):
            for c_idx, val in enumerate(r):
                self.acc_table.setItem(r_idx, c_idx, QTableWidgetItem(str(val)))

    def add_facebook_account(self):
        dev_id = self.input_acc_device.text().strip()
        username = self.input_acc_name.text().strip()
        pkg = self.combo_acc_pkg.currentText()
        if not dev_id or not username:
            QMessageBox.warning(self, "Uyarı", "Cihaz ID ve Kullanıcı Adı girin!")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO fb_accounts (device_id, fb_username, app_package, profile_slot, warmup_level, status) VALUES (?, ?, ?, 'MAIN', 1, 'ACTIVE')",
            (int(dev_id), username, pkg)
        )
        conn.commit()
        conn.close()
        self.input_acc_device.clear()
        self.input_acc_name.clear()
        self.load_accounts_table()
        self.refresh_kpis()
        self.log_console.append(f"[CRM] Yeni hesap eklendi: {username}")

    def refresh_agent_report(self):
        rep = ManagerAgent.get_fleet_report()
        if hasattr(self, "dash_agent_box"):
            self.dash_agent_box.setPlainText(rep)

    def start_bot_process(self):
        self.btn_start_bot.setEnabled(False)
        self.log_console.append("[INFO] Kampanya & Biyometrik görev motoru başlatılıyor...")
        self.bot_thread = BotRunnerThread()
        self.bot_thread.log_signal.connect(self.append_log)
        self.bot_thread.start()

    def append_log(self, text):
        self.log_console.append(text)
        if "tamamlandı" in text.lower() or "tamamlandi" in text.lower():
            self.btn_start_bot.setEnabled(True)
            self.refresh_agent_report()
            self.refresh_kpis()
            self.load_campaign_queue_table()

    def open_all_scrcpy(self):
        self.log_console.append("[SCRCPY] Bağlı cihaz ekranları açılıyor...")
        subprocess.Popen(["scrcpy", "--max-size", "600", "--max-fps", "25"])

    def send_telegram_alert(self):
        from telegram_alerts import TelegramAlerts
        TelegramAlerts.send_mission_report(45, 0)
        self.log_console.append("[TELEGRAM] Operasyon özeti gönderildi.")

    def trigger_kill_switch(self):
        from kill_switch import KillSwitch
        KillSwitch.emergency_stop_device("NODE-01")
        self.log_console.append("[KILL-SWITCH] Acil ağ izolasyonu devreye alındı!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
