import sys
import os
import json
import sqlite3
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QTextEdit,
    QStackedWidget, QHeaderView, QLineEdit, QComboBox, QMessageBox,
    QFrame, QGridLayout, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import init_db
from manager_agent import ManagerAgent

DB_PATH = "autofarm.db"


class BotRunnerThread(QThread):
    log_signal = pyqtSignal(str)

    def run(self):
        self.log_signal.emit("[ENGINE] Paralel gorev ve simulasyon motoru baslatildi...")
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
        self.log_signal.emit("[ENGINE] Tum gorev dongusu tamamlandi.")


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
        self.lbl_value.setStyleSheet(f"color: #f4f4f5; font-size: 26px; font-weight: 800; border: none; background: transparent;")

        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet(f"color: {accent_color}; font-size: 11px; font-weight: 600; border: none; background: transparent;")

        layout.addWidget(lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(lbl_sub)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoFarm-30 // Enterprise Command Center")
        self.setGeometry(80, 60, 1480, 880)

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
                min-width: 250px;
                max-width: 250px;
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
            QPushButton#BtnEmerald {
                background-color: #059669;
                color: #ffffff;
                border: 1px solid #10b981;
            }
            QPushButton#BtnEmerald:hover { background-color: #10b981; }
            QPushButton#BtnIndigo {
                background-color: #4f46e5;
                color: #ffffff;
                border: 1px solid #6366f1;
            }
            QPushButton#BtnIndigo:hover { background-color: #6366f1; }
            QPushButton#BtnAmber {
                background-color: #d97706;
                color: #ffffff;
                border: 1px solid #f59e0b;
            }
            QPushButton#BtnAmber:hover { background-color: #f59e0b; }
            QPushButton#BtnRose {
                background-color: #e11d48;
                color: #ffffff;
                border: 1px solid #f43f5e;
            }
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

        init_db()
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
        sb_layout.setSpacing(10)

        brand = QFrame()
        brand.setObjectName("BrandBox")
        b_layout = QVBoxLayout(brand)
        b_layout.setContentsMargins(10, 8, 10, 8)
        b_title = QLabel("⚡ AUTOFARM-30")
        b_title.setStyleSheet("color: #38bdf8; font-size: 17px; font-weight: 900; background: transparent; border: none;")
        b_sub = QLabel("Enterprise Fleet Suite v3.0")
        b_sub.setStyleSheet("color: #71717a; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        b_layout.addWidget(b_title)
        b_layout.addWidget(b_sub)
        sb_layout.addWidget(brand)
        sb_layout.addSpacing(10)

        menu_items = [
            ("🏠  Genel Bakış (Dashboard)", 0),
            ("📱  Filo & Cihaz Yönetimi", 1),
            ("🌐  Proxy & Tünel İzolasyonu", 2),
            ("👥  Facebook Hesap CRM", 3),
            ("🎯  Hedefli Görev & Ajan", 4),
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
        st_lbl1 = QLabel("🟢 SİSTEM DURUMU: AKTİF")
        st_lbl1.setStyleSheet("color: #4ade80; font-weight: 800; font-size: 11px; background: transparent; border: none;")
        st_lbl2 = QLabel("Kapasite: 30 Fiziksel Node\nMimari: Yerel SQLite + ADB")
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

        # ÜST KPI KARTLARI (HER ZAMAN GÖRÜNÜR)
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(16)
        self.card_nodes = StatCard("Filo Kapasitesi", "30 Node", "Yerel Ag & ADB Hazir", "#38bdf8")
        self.card_accounts = StatCard("Kayitli FB Hesabi", "3 Aktif", "Coklu Profil Rotasyonu", "#a855f7")
        self.card_tasks = StatCard("Bekleyen Gorevler", "0 Gorev", "Otonom Kuyruk Aktif", "#10b981")
        self.card_health = StatCard("Tünel & Güvenlik", "%100", "Kill-Switch Korumali", "#f59e0b")

        kpi_layout.addWidget(self.card_nodes)
        kpi_layout.addWidget(self.card_accounts)
        kpi_layout.addWidget(self.card_tasks)
        kpi_layout.addWidget(self.card_health)
        main_v.addLayout(kpi_layout)

        # SAYFA YIĞINI
        self.stack = QStackedWidget()
        main_v.addWidget(self.stack)

        self.page_dash = QWidget()
        self.page_fleet = QWidget()
        self.page_proxy = QWidget()
        self.page_accounts = QWidget()
        self.page_agent = QWidget()

        self.init_dashboard_page()
        self.init_fleet_page()
        self.init_proxy_page()
        self.init_accounts_page()
        self.init_agent_page()

        self.stack.addWidget(self.page_dash)
        self.stack.addWidget(self.page_fleet)
        self.stack.addWidget(self.page_proxy)
        self.stack.addWidget(self.page_accounts)
        self.stack.addWidget(self.page_agent)

        root_layout.addWidget(main_area)
        self.refresh_kpis()

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setObjectName("NavBtnActive" if i == index else "NavBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.refresh_kpis()

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

        # Hızlı Aksiyon Barı
        action_card = QFrame()
        action_card.setObjectName("PanelCard")
        act_layout = QHBoxLayout(action_card)
        act_layout.setContentsMargins(16, 14, 16, 14)
        act_layout.setSpacing(12)

        lbl_act = QLabel("⚡ Hızlı Komuta:")
        lbl_act.setStyleSheet("font-weight: 800; color: #f4f4f5; background: transparent; border: none;")
        act_layout.addWidget(lbl_act)

        self.btn_start_bot = QPushButton("🚀 Otomasyonu / Simülasyonu Başlat")
        self.btn_start_bot.setObjectName("BtnEmerald")
        self.btn_start_bot.clicked.connect(self.start_bot_process)
        act_layout.addWidget(self.btn_start_bot)

        btn_grid = QPushButton("🎛️ Tüm Ekranları Aç (Scrcpy Grid)")
        btn_grid.setObjectName("BtnIndigo")
        btn_grid.clicked.connect(self.open_all_scrcpy)
        act_layout.addWidget(btn_grid)

        btn_tg = QPushButton("📲 Telegram Özeti Gönder")
        btn_tg.setObjectName("BtnAmber")
        btn_tg.clicked.connect(self.send_telegram_alert)
        act_layout.addWidget(btn_tg)

        btn_kill = QPushButton("🚨 Acil Kill-Switch")
        btn_kill.setObjectName("BtnRose")
        btn_kill.clicked.connect(self.trigger_kill_switch)
        act_layout.addWidget(btn_kill)

        act_layout.addStretch()
        layout.addWidget(action_card)

        # Alt İkili Görünüm: Sol Canlı Terminal + Sağ Yönetici Özeti
        split_layout = QHBoxLayout()
        split_layout.setSpacing(16)

        log_card = QFrame()
        log_card.setObjectName("PanelCard")
        log_v = QVBoxLayout(log_card)
        log_lbl = QLabel("🖥️ Canlı Operasyon & Telemetri Konsolu")
        log_lbl.setStyleSheet("font-weight: 700; color: #38bdf8; background: transparent; border: none;")
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.append("[SYSTEM] AutoFarm-30 Enterprise Dashboard basariyla yuklendi.")
        self.log_console.append("[READY] Gorev motoru ve yerel veritabani senkronize.")
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

    def init_fleet_page(self):
        layout = QVBoxLayout(self.page_fleet)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        lbl = QLabel("📱 Fiziksel Cihaz Filosu ve ADB Bağlantı Durumu")
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
        self.input_acc_device.setPlaceholderText("Cihaz ID (Örn: 1)")
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

    def init_agent_page(self):
        layout = QVBoxLayout(self.page_agent)
        layout.setContentsMargins(0, 0, 0, 0)

        form_card = QFrame()
        form_card.setObjectName("PanelCard")
        f_layout = QHBoxLayout(form_card)
        self.input_link = QLineEdit()
        self.input_link.setPlaceholderText("Hedef Gönderi Linki (https://...)")
        self.input_comment = QLineEdit()
        self.input_comment.setPlaceholderText("Yapılacak Yorum Metni...")
        btn_assign = QPushButton("🎯 Görevi Kuyruğa Ekle")
        btn_assign.setObjectName("BtnIndigo")
        btn_assign.clicked.connect(self.assign_task)

        f_layout.addWidget(self.input_link, 2)
        f_layout.addWidget(self.input_comment, 2)
        f_layout.addWidget(btn_assign)
        layout.addWidget(form_card)

        self.agent_console = QTextEdit()
        self.agent_console.setReadOnly(True)
        self.refresh_agent_report()
        layout.addWidget(self.agent_console)

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

    def assign_task(self):
        link = self.input_link.text().strip()
        comment = self.input_comment.text().strip()
        if not link:
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO targeted_tasks (device_id, post_link, action_type, comment_text, status) VALUES (1, ?, ?, ?, 'PENDING')",
            (link, "COMMENT" if comment else "LIKE", comment)
        )
        conn.commit()
        conn.close()
        self.input_link.clear()
        self.input_comment.clear()
        self.refresh_agent_report()
        self.refresh_kpis()
        self.log_console.append(f"[TASK] Yeni gorev kuyruga eklendi -> {link}")

    def refresh_agent_report(self):
        rep = ManagerAgent.get_fleet_report()
        self.agent_console.setPlainText(rep)
        if hasattr(self, "dash_agent_box"):
            self.dash_agent_box.setPlainText(rep)

    def start_bot_process(self):
        self.btn_start_bot.setEnabled(False)
        self.log_console.append("[INFO] Gorev motoru baslatiliyor...")
        self.bot_thread = BotRunnerThread()
        self.bot_thread.log_signal.connect(self.append_log)
        self.bot_thread.start()

    def append_log(self, text):
        self.log_console.append(text)
        if "tamamlandi" in text.lower():
            self.btn_start_bot.setEnabled(True)
            self.refresh_agent_report()
            self.refresh_kpis()

    def open_all_scrcpy(self):
        self.log_console.append("[SCRCPY] Bagli cihaz ekranlari aciliyor...")
        subprocess.Popen(["scrcpy", "--max-size", "600", "--max-fps", "25"])

    def send_telegram_alert(self):
        from telegram_alerts import TelegramAlerts
        TelegramAlerts.send_mission_report(45, 0)
        self.log_console.append("[TELEGRAM] Operasyon ozeti gonderildi.")

    def trigger_kill_switch(self):
        from kill_switch import KillSwitch
        KillSwitch.emergency_stop_device("NODE-01")
        self.log_console.append("[KILL-SWITCH] Acil ag izolasyonu devreye alindi!")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
