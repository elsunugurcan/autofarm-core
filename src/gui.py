import sys
import os
import subprocess
import sqlite3
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QTextEdit,
    QTabWidget, QHeaderView, QLineEdit, QComboBox, QMessageBox, QFrame
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
        self.log_signal.emit("[BOT] 🚀 Facebook paralel ısınma/simülasyon motoru başlatıldı...")
        process = subprocess.Popen(["python3", "src/runner.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(process.stdout.readline, ""):
            if line:
                self.log_signal.emit(line.strip())
        process.stdout.close()
        process.wait()
        self.log_signal.emit("[BOT] ✅ Otomasyon görevi başarıyla tamamlandı.")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoFarm-30 | Kurumsal Komuta Merkezi & Filo Yönetimi")
        self.setGeometry(100, 100, 1350, 800)
        self.setStyleSheet("""
            QMainWindow { background-color: #0f111a; color: #a9b1d6; }
            QWidget { background-color: #0f111a; color: #a9b1d6; font-family: sans-serif; font-size: 13px; }
            QTabWidget::pane { border: 1px solid #1f2335; background: #1a1b26; border-radius: 8px; }
            QTabBar::tab { background: #1f2335; color: #787c99; padding: 10px 22px; margin-right: 4px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-weight: 600; }
            QTabBar::tab:selected { background: #7aa2f7; color: #1a1b26; font-weight: bold; }
            QPushButton { background-color: #7aa2f7; color: #1a1b26; border: none; padding: 9px 18px; border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #89b4fa; }
            QTableWidget { background-color: #1a1b26; gridline-color: #292e42; border: 1px solid #1f2335; border-radius: 8px; color: #c0caf5; }
            QHeaderView::section { background-color: #1f2335; color: #7aa2f7; padding: 8px; border: none; font-weight: bold; font-size: 12px; }
            QTextEdit, QLineEdit, QComboBox { background-color: #1a1b26; color: #9ece6a; border: 1px solid #292e42; border-radius: 6px; font-family: monospace; padding: 8px; font-size: 12px; }
        """)
        init_db()
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        title_label = QLabel("⚡ AutoFarm-30 Kurumsal Komuta Merkezi")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #7aa2f7; margin-bottom: 5px;")
        main_layout.addWidget(title_label)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.tab_logs = QWidget()
        self.init_logs_tab()
        self.tabs.addTab(self.tab_logs, "📝 Canlı İşlem Logları")

        self.tab_fleet = QWidget()
        self.init_fleet_tab()
        self.tabs.addTab(self.tab_fleet, "🚀 Filo & Cihazlar")

        self.tab_proxy = QWidget()
        self.init_proxy_tab()
        self.tabs.addTab(self.tab_proxy, "🌐 Proxy & Ağ")

        self.tab_accounts = QWidget()
        self.init_accounts_tab()
        self.tabs.addTab(self.tab_accounts, "📊 Facebook Hesapları")

        self.tab_agent = QWidget()
        self.init_agent_tab()
        self.tabs.addTab(self.tab_agent, "🎯 Hedefli Görev & Ajan")

    def init_logs_tab(self):
        layout = QVBoxLayout(self.tab_logs)
        btn_layout = QHBoxLayout()
        self.btn_start_bot = QPushButton("🚀 Otomasyonu Başlat")
        self.btn_start_bot.clicked.connect(self.start_bot_process)
        btn_layout.addWidget(self.btn_start_bot)
        
        self.btn_all_screens = QPushButton("🎛️ Tüm Ekranları Aç (Grid)")
        self.btn_all_screens.clicked.connect(self.open_all_scrcpy)
        btn_layout.addWidget(self.btn_all_screens)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.append("[SYSTEM] ⚡ Arayüz başarıyla yüklendi.")
        layout.addWidget(self.log_console)

    def init_accounts_tab(self):
        layout = QVBoxLayout(self.tab_accounts)
        self.acc_table = QTableWidget()
        self.acc_table.setColumnCount(8)
        self.acc_table.setHorizontalHeaderLabels(["ID", "Cihaz ID", "Kullanıcı Adı", "Paket", "Profil", "Warm-Up", "Beğeni", "Durum"])
        layout.addWidget(self.acc_table)
        self.load_accounts_table()

    def load_accounts_table(self):
        if not os.path.exists(DB_PATH): return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, device_id, fb_username, app_package, profile_slot, warmup_level, daily_likes, status FROM fb_accounts")
        rows = c.fetchall()
        conn.close()
        self.acc_table.setRowCount(len(rows))
        for row, r in enumerate(rows):
            for col, val in enumerate(r):
                self.acc_table.setItem(row, col, QTableWidgetItem(str(val)))

    def init_agent_tab(self):
        layout = QVBoxLayout(self.tab_agent)
        self.agent_console = QTextEdit()
        self.agent_console.setReadOnly(True)
        self.agent_console.setPlainText(ManagerAgent.get_fleet_report())
        layout.addWidget(self.agent_console)

    def open_all_scrcpy(self):
        subprocess.Popen(["scrcpy", "--max-size", "600", "--max-fps", "25"])

    def start_bot_process(self):
        self.btn_start_bot.setEnabled(False)
        self.bot_thread = BotRunnerThread()
        self.bot_thread.log_signal.connect(self.log_console.append)
        self.bot_thread.start()

    def init_fleet_tab(self):
        layout = QVBoxLayout(self.tab_fleet)
        self.device_table = QTableWidget()
        self.device_table.setColumnCount(5)
        self.device_table.setHorizontalHeaderLabels(["ID", "Node", "Seri No", "Proxy", "Durum"])
        layout.addWidget(self.device_table)

    def init_proxy_tab(self):
        layout = QVBoxLayout(self.tab_proxy)
        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(4)
        self.proxy_table.setHorizontalHeaderLabels(["ID", "Node", "IP", "Proxy"])
        layout.addWidget(self.proxy_table)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())