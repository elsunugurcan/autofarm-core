from contextlib import closing
import sys, os, json, subprocess, threading, time, random, sqlite3
import uuid
import queue
from datetime import datetime
try:
    if os.environ.get("AUTOFARM_SKIP_AUTO_UPDATE") != "1":
        subprocess.run("git pull --rebase --autostash origin main", shell=True, capture_output=True, timeout=10)
except Exception:
    pass
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath("."))

import tkinter as tk
from tkinter import ttk, filedialog
import customtkinter as ctk
from local_media import validate_image
from share_history import list_shares, get_share, interrupt_process, remember_image, LABELS
from PIL import Image
import watcher_history as watcher_store
import fleet_controls
from ui_workspace import Workspace
from operation_controls import PhonePicker, engagement_plan
from src import operation_timing as timing
from src import sequential_jobs, publication_queue
from src.task_cleanup import task_serials, close_devices
from recovery_policy import FREEZE_STEP_LIMIT

from core_engine import (
    PROF_FILE, DB_FILE, GROUPS_FILE, PAGES_FILE, PERSONAS,
    load_json, save_json, lock_portrait_mode,
    mute_device_audio, wake_and_home, home_and_sleep, check_vpn_and_temp
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def get_profiles():
    default = {
        f"NODE-{i:02d}": {
            "fb_name": f"FB Hesap {i:02d}",
            "proxy": f"socks5://user:pass@127.0.0.1:{1080+i}",
            "persona": PERSONAS[(i - 1) % len(PERSONAS)]
        } for i in range(1, 31)
    }
    data = load_json(PROF_FILE, default)
    for i in range(1, 31):
        k = f"NODE-{i:02d}"
        if k not in data:
            data[k] = default[k]
        elif "persona" not in data[k]:
            data[k]["persona"] = PERSONAS[(i - 1) % len(PERSONAS)]
    return data

class AutoFarmModernCommandCenter(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AutoFarm-30 • Komuta Merkezi v7.5")
        scale = self._get_window_scaling()
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        width = max(800, min(1480, int((screen_width - 70) / scale)))
        height = max(560, min(920, int((screen_height - 100) / scale)))
        self.geometry(f"{width}x{height}+30+30")
        self.minsize(min(width, 980), min(height, 620))
        self.configure(fg_color="#080f1d")

        self.profiles = get_profiles()
        self.saved_groups = load_json(GROUPS_FILE, [
            {"name": "Örnek Grup 1", "url": "https://www.facebook.com/groups/ornek1", "selected": True}
        ])
        self.saved_pages = load_json(PAGES_FILE, [
            {"name": "Ana Sayfamız", "url": "https://www.facebook.com/ornek_sayfa", "selected": True}
        ])

        self.scrcpy_procs = {}
        self.active_proc = None
        self.process_lock = threading.RLock()
        self.watcher_proc = None
        self.watcher_run_id = None
        self.watcher_window = None
        self.watcher_log_queue = queue.Queue()
        self.ui_events = queue.Queue()
        self.ui_thread = threading.get_ident()
        self.device_scan_running = False
        self.last_scan_text = "Henüz taranmadı"
        self.quick_tools_expanded = False
        self.fleet_view_busy = False
        self.fleet_sleep_busy = False
        self.row_widgets = {}
        self.timing_widgets = {}
        self.group_btn_vars = []
        self.page_btn_vars = []
        self.comment_counter = 1
        self.sidebar_expanded = True
        self.console_expanded = False

        self.setup_treeview_style()
        self.build_layout()
        if "--no-device-scan" not in sys.argv:
            self.refresh_devices()
        self.refresh_queue_table()
        self.refresh_watched_list_ui()

        self.protocol("WM_DELETE_WINDOW", self.close_command_center)

        self.after(1000, self.poll_watcher_monitor)
        self.after(4000, self.periodic_ui_sync)
        # Startup is read-only: every task requires an explicit Start/Resume click.

    def setup_treeview_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background="#111827",
            foreground="#e2e8f0",
            fieldbackground="#111827",
            rowheight=28,
            borderwidth=0,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Treeview.Heading",
            background="#24354d",
            foreground="#38bdf8",
            borderwidth=0,
            font=("Segoe UI", 9, "bold")
        )
        style.map("Treeview", background=[("selected", "#3b82f6")])

    def build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=228, corner_radius=16, fg_color="#0e192b", border_width=1, border_color="#24354d")
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        self.sidebar.grid_propagate(False)
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=12, pady=(18, 8))
        ctk.CTkButton(brand, text="☰", width=32, height=32, fg_color="#1c304c", command=self.toggle_sidebar).pack(side="left")
        self.lbl_brand_title = ctk.CTkLabel(brand, text="AUTOFARM", font=("Segoe UI", 19, "bold"), text_color="#f1f5f9")
        self.lbl_brand_title.pack(side="left", padx=10)
        self.lbl_brand_sub = ctk.CTkLabel(self.sidebar, text="Komuta Merkezi  /  v7.5", font=("Segoe UI", 11), text_color="#8193ae")
        self.lbl_brand_sub.pack(anchor="w", padx=18, pady=(0, 22))
        self.nav_buttons = {}
        nav_items = [("tab_fleet", "01   Filo Cihaz Yönetimi"), ("tab_campaign", "02   Kampanya Dağıtıcı"),
                     ("tab_telegram", "03   Grup & Sayfa Merkezi"),
                     ("tab_report", "04   Şikayet Merkezi"), ("tab_watcher", "05   Grup & Kelime Nöbetçisi"),
                     ("tab_warmup", "06   Hesap Isıtma Merkezi")]
        for key, label in nav_items:
            button = ctk.CTkButton(self.sidebar, text=label, anchor="w", height=39, corner_radius=9,
                font=("Segoe UI", 11, "bold"), fg_color="transparent", text_color="#9babc2",
                hover_color="#1b2c46", command=lambda k=key: self.select_tab(k))
            button.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = (button, label)
        self.btn_tools = ctk.CTkButton(self.sidebar, text="Cihaz Araçları  ▾", anchor="w", height=34,
            fg_color="#17263c", hover_color="#203650", command=self.toggle_quick_tools)
        self.btn_tools.pack(fill="x", padx=12, pady=(18, 5))
        self.quick_frame = ctk.CTkFrame(self.sidebar, fg_color="#101f33", corner_radius=10)
        tools = [("Seçili Telefonları Uyut", self.sleep_all_connected, "#9f2444"),
                 ("Seçili Telefonları Dikey Kilitle", self.lock_all_portrait, "#1b5970"),
                 ("Seçili Ekranları PC'de Aç", self.open_selected_screens, "#245b99"),
                 ("PC İzleme Pencerelerini Kapat", self.close_all_screens, "#263850"),
                 ("Seçili Telefonları Sessize Al", self.mute_all_connected, "#263850")]
        for text, command, color in tools:
            ctk.CTkButton(self.quick_frame, text=text, command=command, height=29, font=("Segoe UI", 10),
                          fg_color=color, hover_color="#334b68").pack(fill="x", padx=8, pady=3)
        self.status_badge = ctk.CTkFrame(self.sidebar, fg_color="#0b1525", corner_radius=10)
        self.status_badge.pack(side="bottom", fill="x", padx=12, pady=12)
        self.lbl_side_state = ctk.CTkLabel(self.status_badge, text="● HAZIR", text_color="#5eead4", font=("Segoe UI", 11, "bold"))
        self.lbl_side_state.pack(anchor="w", padx=12, pady=(10, 2))
        self.lbl_last_scan = ctk.CTkLabel(self.status_badge, text="Son tarama: —", text_color="#8193ae", font=("Segoe UI", 10))
        self.lbl_last_scan.pack(anchor="w", padx=12, pady=(0, 10))
        self.main_area = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=16, pady=12)
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(2, weight=1)
        page_header = ctk.CTkFrame(self.main_area, fg_color="transparent")
        page_header.grid(row=0, column=0, sticky="ew", pady=(2, 12))
        page_header.grid_columnconfigure(0, weight=1)
        self.lbl_page_title = ctk.CTkLabel(page_header, text="Filo Cihaz Yönetimi", font=("Segoe UI", 22, "bold"), anchor="w")
        self.lbl_page_title.grid(row=0, column=0, sticky="w")
        self.lbl_page_sub = ctk.CTkLabel(page_header, text="", font=("Segoe UI", 11), text_color="#8193ae", anchor="w")
        self.lbl_page_sub.grid(row=1, column=0, sticky="w")
        self.lbl_live_state = ctk.CTkLabel(page_header, text="● Hazır", fg_color="#123431", text_color="#5eead4", corner_radius=8, width=120)
        self.lbl_live_state.grid(row=0, column=1, padx=12)
        ctk.CTkButton(page_header, text="Nöbetçi Takibi ↗", width=145, height=34, fg_color="#1a3657", hover_color="#24507f", command=self.open_watcher_monitor).grid(row=0, column=2)
        kpi_row = ctk.CTkFrame(self.main_area, fg_color="transparent")
        kpi_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for column in range(4):
            kpi_row.grid_columnconfigure(column, weight=1, uniform="kpi")
        self.lbl_kpi_nodes = self.create_kpi_card(kpi_row, 0, "BAĞLI TELEFON", "— / 25", "Tarama bekleniyor", "#60a5fa")
        self.lbl_kpi_acc = self.create_kpi_card(kpi_row, 1, "GRUP & SAYFA", f"{len(self.saved_groups)} Grup | {len(self.saved_pages)} Sayfa", "Kayıtlı hedefler", "#a5b4fc")
        self.lbl_kpi_queue = self.create_kpi_card(kpi_row, 2, "BEKLEYEN GÖREV", "0 Görev", "Ortak görev kuyruğu", "#5eead4")
        self.lbl_kpi_bio = self.create_kpi_card(kpi_row, 3, "DONMA KURTARMA", f"{FREEZE_STEP_LIMIT} kontrol", "Değişmeyen akış eşiği", "#fbbf24")
        self.notebook_container = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.notebook_container.grid(row=2, column=0, sticky="nsew")
        self.notebook_container.grid_columnconfigure(0, weight=1)
        self.notebook_container.grid_rowconfigure(0, weight=1)
        self.operation_pickers = {}
        self.tabs, self.tab_surfaces = {}, {}
        for key, _ in nav_items:
            surface = Workspace(self.notebook_container, minimum_width=1420 if key == "tab_fleet" else 1050)
            surface.grid(row=0, column=0, sticky="nsew")
            self.tab_surfaces[key], self.tabs[key] = surface, surface.body
        self.build_tab_fleet(self.tabs["tab_fleet"])
        self.build_tab_campaign(self.tabs["tab_campaign"])
        self.build_tab_publish(self.tabs["tab_telegram"])
        self.build_tab_report(self.tabs["tab_report"])
        self.build_tab_watcher(self.tabs["tab_watcher"])
        self.build_tab_warmup(self.tabs["tab_warmup"])
        self.build_share_history()
        self.console_wrapper = ctk.CTkFrame(self.main_area, fg_color="#0e192b", corner_radius=10, border_width=1, border_color="#24354d")
        self.console_wrapper.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        console_header = ctk.CTkFrame(self.console_wrapper, fg_color="transparent")
        console_header.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(console_header, text="Canlı Operasyon", font=("Segoe UI", 11, "bold"), text_color="#cbd5e1").pack(side="left", padx=(2, 12))
        self.btn_toggle_con = ctk.CTkButton(console_header, text="Konsolu Aç", width=100, height=26, fg_color="#213651", command=self.toggle_console)
        self.btn_toggle_con.pack(side="right", padx=3)
        ctk.CTkButton(console_header, text="Görevi Durdur", width=115, height=26, fg_color="#9f2444", hover_color="#be3456", command=self.stop_active_proc).pack(side="right", padx=5)
        self.lbl_log_preview = ctk.CTkLabel(console_header, text="", anchor="w", text_color="#8193ae", font=("Segoe UI", 10))
        self.lbl_log_preview.pack(side="left", fill="x", expand=True)
        self.txt_log = ctk.CTkTextbox(self.console_wrapper, height=120, fg_color="#080f1d", text_color="#a7f3d0", font=("Consolas", 11), corner_radius=8)
        self.log(f"[SİSTEM] Komuta merkezi hazır. Akış donma eşiği: {FREEZE_STEP_LIMIT} değişmeyen kontrol.")
        self.select_tab("tab_fleet")

    def build_share_history(self):
        self.history_wrapper = ctk.CTkFrame(self.main_area, fg_color="#0e192b", corner_radius=10)
        self.history_wrapper.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        header = ctk.CTkFrame(self.history_wrapper, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=4)
        self.lbl_history = ctk.CTkLabel(header, text="Paylaşım Geçmişi", text_color="#38bdf8", font=("Segoe UI", 12, "bold"))
        self.lbl_history.pack(side="left")
        self.btn_history = ctk.CTkButton(header, text="Geçmişi Göster", width=115, height=26, command=self.toggle_share_history)
        self.btn_history.pack(side="right", padx=4)
        self.history_limit = 200
        ctk.CTkButton(header, text="Daha Eski Kayıtlar", width=130, height=26, command=self.more_share_history).pack(side="right", padx=4)
        ctk.CTkButton(header, text="Seçili Kaydın Ayrıntıları", width=160, height=26, command=self.show_share_detail).pack(side="right", padx=4)
        self.history_body = ctk.CTkFrame(self.history_wrapper, fg_color="transparent")
        columns = ("time", "phone", "account", "target", "title", "status")
        self.history_tree = ttk.Treeview(self.history_body, columns=columns, show="tree headings", height=3)
        self.history_tree.heading("#0", text="Görsel")
        self.history_tree.column("#0", width=65, stretch=False)
        for key, title, width in zip(columns, ("Tarih / Saat", "Telefon / Seri", "Facebook Hesabı", "Grup / Sayfa", "Başlık", "Durum"), (150, 180, 140, 170, 190, 240)):
            self.history_tree.heading(key, text=title)
            self.history_tree.column(key, width=width, minwidth=70)
        style = ttk.Style()
        style.configure("History.Treeview", rowheight=42)
        self.history_tree.configure(style="History.Treeview")
        self.history_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.history_body, orient="vertical", command=self.history_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        self.history_tree.bind("<Double-1>", self.show_share_detail)
        self.history_images = {}
        self.history_signature = None
        self.refresh_share_history()

    def toggle_share_history(self):
        if self.history_body.winfo_manager():
            self.history_body.pack_forget()
            self.btn_history.configure(text="Geçmişi Göster")
        else:
            if self.console_expanded:
                self.toggle_console()
            self.history_body.pack(fill="both", expand=True, padx=8, pady=(0, 6))
            self.btn_history.configure(text="Geçmişi Gizle")

    def refresh_share_history(self):
        from PIL import ImageTk
        rows = list_shares(self.history_limit)
        signature = [(r["id"], r["updated_at"], r["status"]) for r in rows]
        if signature == self.history_signature:
            return
        self.history_signature = signature
        selected = self.history_tree.selection()
        self.history_tree.delete(*self.history_tree.get_children())
        self.history_images = {}
        for row in rows:
            image = None
            try:
                with Image.open(row["image_path"]) as original:
                    original.thumbnail((48, 36))
                    image = ImageTk.PhotoImage(original.copy(), master=self)
                self.history_images[row["id"]] = image
            except (OSError, ValueError):
                pass
            options = {"image": image} if image else {"text": "—"}
            self.history_tree.insert("", "end", iid=str(row["id"]), values=(
                row["created_at"][:19].replace("T", " "), f'{row["node_id"]} / {row["serial"]}',
                row["fb_name"], row["target_name"] or row["target_url"], row["title"], LABELS.get(row["status"], row["status"])), **options)
        if selected and self.history_tree.exists(selected[0]):
            self.history_tree.selection_set(selected[0])
        self.lbl_history.configure(text=f"Paylaşım Geçmişi  •  {len(rows)} kayıt" if rows else "Paylaşım Geçmişi  •  Henüz kayıt yok")

    def show_share_detail(self, event=None):
        selected = self.history_tree.selection()
        if not selected:
            return
        row = get_share(int(selected[0]))
        if not row:
            return
        window = ctk.CTkToplevel(self)
        window.title("Paylaşım Ayrıntıları")
        window.geometry("760x620")
        window.transient(self)
        try:
            with Image.open(row["image_path"]) as original:
                original.thumbnail((650, 250))
                window.preview_image = ctk.CTkImage(original.copy(), size=original.size)
            ctk.CTkLabel(window, image=window.preview_image, text="").pack(pady=10)
        except (OSError, ValueError):
            pass
        details = ctk.CTkTextbox(window, wrap="word")
        details.pack(fill="both", expand=True, padx=15, pady=10)
        fields = [("Tarih", "created_at"), ("Son Güncelleme", "updated_at"), ("Telefon", "node_id"),
                  ("Seri No", "serial"), ("Kayıtlı Facebook Hesabı", "fb_name"), ("Hedef", "target_name"),
                  ("Hedef Bağlantısı", "target_url"), ("Başlık", "title"), ("Görsel Dosyası", "image_name"),
                  ("Gönderi Bağlantısı", "post_url"), ("Açıklama", "detail")]
        details.insert("end", f'Durum: {LABELS.get(row["status"], row["status"])}\n\n')
        for label, key in fields:
            details.insert("end", f"{label}: {row[key] or '—'}\n\n")
        details.configure(state="disabled")

    def more_share_history(self):
        self.history_limit += 200
        self.history_signature = None
        self.refresh_share_history()

    def create_kpi_card(self, parent, col, title, main_val, sub_val, accent_color):
        card = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=12, border_width=1, border_color="#24354d")
        card.grid(row=0, column=col, sticky="ew", padx=6)

        top_line = ctk.CTkFrame(card, height=4, corner_radius=2, fg_color=accent_color)
        top_line.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(card, text=title, font=("Segoe UI", 10, "bold"), text_color="#94a3b8").pack(anchor="w", padx=16)
        lbl_val = ctk.CTkLabel(card, text=main_val, font=("Segoe UI", 18, "bold"), text_color="#f8fafc")
        lbl_val.pack(anchor="w", padx=16, pady=(2, 2))
        ctk.CTkLabel(card, text=sub_val, font=("Segoe UI", 10), text_color=accent_color).pack(anchor="w", padx=16, pady=(0, 8))
        return lbl_val

    def toggle_quick_tools(self):
        self.quick_tools_expanded = not self.quick_tools_expanded
        if self.quick_tools_expanded and self.sidebar_expanded:
            self.quick_frame.pack(fill="x", padx=12, pady=5, after=self.btn_tools)
            self.btn_tools.configure(text="Cihaz Araçları  ▴")
        else:
            self.quick_frame.pack_forget()
            self.btn_tools.configure(text="Cihaz Araçları  ▾")

    def toggle_sidebar(self):
        if self.sidebar_expanded:
            self.sidebar.configure(width=64)
            self.lbl_brand_title.pack_forget()
            self.lbl_brand_sub.pack_forget()
            self.quick_frame.pack_forget()
            self.status_badge.pack_forget()
            self.btn_tools.pack_forget()
            for key, (btn, full_txt) in self.nav_buttons.items():
                icon = full_txt.split()[0]
                btn.configure(text=icon, width=40, anchor="center")
            self.sidebar_expanded = False
        else:
            self.sidebar.configure(width=228)
            self.lbl_brand_title.pack(side="left", padx=10)
            self.lbl_brand_sub.pack(anchor="w", padx=18, pady=(0, 10))
            for key, (btn, full_txt) in self.nav_buttons.items():
                btn.configure(text=full_txt, anchor="w")
            if self.quick_tools_expanded:
                self.quick_frame.pack(fill="x", padx=12, pady=5)
            self.status_badge.pack(side="bottom", fill="x", padx=12, pady=10)
            self.btn_tools.pack(fill="x", padx=12, pady=(18, 5))
            self.sidebar_expanded = True

    def toggle_console(self):
        if self.console_expanded:
            self.txt_log.pack_forget()
            self.btn_toggle_con.configure(text="Konsolu Aç")
            self.console_expanded = False
        else:
            if self.history_body.winfo_manager():
                self.toggle_share_history()
            self.txt_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            self.btn_toggle_con.configure(text="Konsolu Gizle")
            self.console_expanded = True

    def select_tab(self, tab_key):
        if tab_key == "tab_pages":
            tab_key = "tab_telegram"
            self.publish_targets.set("Sayfalar")
        for k, frame in self.tabs.items():
            if k == tab_key:
                self.tab_surfaces[k].tkraise()
        self.current_tab = tab_key
        titles = {"tab_fleet": ("Filo Cihaz Yönetimi", "Telefon bağlantıları, hesaplar ve cihaz kontrolleri"),
                  "tab_campaign": ("Kampanya Dağıtıcı", "Görev oluşturun, telefonları seçin ve kuyruğu takip edin"),
                  "tab_telegram": ("Grup & Sayfa Merkezi", "Ortak görsel ve başlık • kayıtlı hedefler • işlem bazında telefon seçimi"),
                  "tab_pages": ("Sayfalar", "Kayıtlı Facebook sayfalarını yönetin"),
                  "tab_report": ("Şikayet Merkezi", "Hedef ve işlem ayarları"),
                  "tab_watcher": ("Grup & Kelime Nöbetçisi", "Anahtar kelime izleme ve seçili telefondan yanıt"),
                  "tab_warmup": ("Hesap Isıtma Merkezi", "Oturum ayarları ve donma kurtarma kontrolleri")}
        title, description = titles[tab_key]
        self.lbl_page_title.configure(text=title)
        self.lbl_page_sub.configure(text=description)
        for k, (btn, _) in self.nav_buttons.items():
            if k == tab_key:
                btn.configure(fg_color="#1d4ed8", text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color="#cbd5e1")

    # ==========================================================================
    # SEKME 1: FILO CIHAZ YONETIMI (+ CIHAZ EKRAN KAPATMA BUTONU)
    # ==========================================================================
    def build_tab_fleet(self, parent):
        top_bar = ctk.CTkFrame(parent, fg_color="#16253c", corner_radius=10)
        top_bar.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            top_bar, text="📱 25 Telefon • Filo Kontrolü",
            font=("Segoe UI", 14, "bold"), text_color="#38bdf8"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        actions = ctk.CTkFrame(top_bar, fg_color="transparent")
        actions.pack(fill="x", padx=8, pady=(0, 5))
        ctk.CTkButton(actions, text="Tüm ONLINE Ekranları Aç", height=32, width=210,
            fg_color="#2563eb", hover_color="#1d4ed8", font=("Segoe UI", 11, "bold"),
            command=self.open_all_online_screens).pack(side="left", padx=4, pady=4)

        ctk.CTkButton(
            actions, text="💾 İsim, Proxy & DNA Kaydet", height=32, corner_radius=8,
            fg_color="#7c3aed", hover_color="#6d28d9", font=("Segoe UI", 11, "bold"),
            command=self.save_all_profiles
        ).pack(side="left", padx=8, pady=8)

        ctk.CTkButton(
            actions, text="📴 Tüm Cihaz Ekranlarını & FB/TT Kapat", height=32, corner_radius=8,
            fg_color="#e11d48", hover_color="#be123c", font=("Segoe UI", 11, "bold"),
            command=self.sleep_every_online_device
        ).pack(side="left", padx=4, pady=8)

        ctk.CTkButton(
            actions, text="🔄 Cihazları Tara", height=32, corner_radius=8,
            fg_color="#3b82f6", hover_color="#1d4ed8", font=("Segoe UI", 11, "bold"),
            command=self.refresh_devices
        ).pack(side="left", padx=4, pady=8)

        ctk.CTkButton(
            actions, text="🟢 Sadece ONLINE Seç", height=32, corner_radius=8,
            fg_color="#059669", hover_color="#047857", font=("Segoe UI", 11, "bold"),
            command=self.select_only_online
        ).pack(side="left", padx=4, pady=8)

        hdr = ctk.CTkFrame(parent, fg_color="#24354d", corner_radius=8, height=34)
        hdr.pack(fill="x", pady=(0, 4))
        cols = [
            ("SEÇ", 40), ("NODE", 70), ("SERİ NO", 145),
            ("DURUM / VPN / ISI", 145), ("FACEBOOK İSİM SOYİSİM", 175),
            ("ATANAN PROXY TÜNELİ", 205), ("PERSONA DNA", 150), ("TEKİL EKRAN & CİHAZ KONTROLÜ", 265)
        ]
        for text, w in cols:
            ctk.CTkLabel(hdr, text=text, width=w, anchor="w", font=("Segoe UI", 10, "bold"), text_color="#94a3b8").pack(side="left", padx=4, pady=5)

        scroll = ctk.CTkScrollableFrame(parent, fg_color="#0b0f19", corner_radius=10)
        scroll.pack(fill="both", expand=True)

        for i in range(1, 26):
            node_id = f"NODE-{i:02d}"
            row_bg = "#131c2e" if i % 2 == 0 else "#0d1322"
            row = ctk.CTkFrame(scroll, fg_color=row_bg, corner_radius=6, height=38)
            row.pack(fill="x", pady=2, padx=2)

            chk_var = tk.BooleanVar(value=True)
            chk = ctk.CTkCheckBox(row, text="", variable=chk_var, width=24, checkbox_width=18, checkbox_height=18, corner_radius=4)
            chk.pack(side="left", padx=(8, 4))

            ctk.CTkLabel(row, text=node_id, width=65, anchor="w", font=("Consolas", 12, "bold"), text_color="#38bdf8").pack(side="left", padx=4)
            lbl_ser = ctk.CTkLabel(row, text="BEKLIYOR...", width=145, anchor="w", font=("Consolas", 11), text_color="#64748b")
            lbl_ser.pack(side="left", padx=4)

            lbl_st = ctk.CTkLabel(row, text="○ OFFLINE", width=145, anchor="w", font=("Segoe UI", 11, "bold"), text_color="#f87171")
            lbl_st.pack(side="left", padx=4)

            ent_name = ctk.CTkEntry(row, width=170, height=28, corner_radius=6, fg_color="#24354d", border_color="#334155", font=("Segoe UI", 11))
            ent_name.insert(0, self.profiles[node_id].get("fb_name", f"FB Hesap {i:02d}"))
            ent_name.pack(side="left", padx=4)

            ent_proxy = ctk.CTkEntry(row, width=200, height=28, corner_radius=6, fg_color="#24354d", border_color="#334155", font=("Consolas", 10))
            ent_proxy.insert(0, self.profiles[node_id].get("proxy", f"socks5://127.0.0.1:{1080+i}"))
            ent_proxy.pack(side="left", padx=4)

            cmb_persona = ctk.CTkComboBox(row, values=PERSONAS, width=145, height=28, corner_radius=6, fg_color="#24354d", border_color="#334155", font=("Segoe UI", 10))
            cmb_persona.set(self.profiles[node_id].get("persona", PERSONAS[(i-1)%len(PERSONAS)]))
            cmb_persona.pack(side="left", padx=4)

            act_box = ctk.CTkFrame(row, fg_color="transparent")
            act_box.pack(side="left", padx=4)

            ctk.CTkButton(act_box, text="📲 İzle", width=50, height=26, corner_radius=6, fg_color="#0284c7", hover_color="#0369a1", font=("Segoe UI", 10, "bold"), command=lambda idx=i: self.open_single_screen(idx)).pack(side="left", padx=2)
            ctk.CTkButton(act_box, text="❌ P.Kapat", width=62, height=26, corner_radius=6, fg_color="#475569", hover_color="#334155", font=("Segoe UI", 10), command=lambda idx=i: self.close_single_screen(idx)).pack(side="left", padx=2)
            ctk.CTkButton(act_box, text="📴 Ekran Kapat", width=85, height=26, corner_radius=6, fg_color="#e11d48", hover_color="#be123c", font=("Segoe UI", 10, "bold"), command=lambda idx=i: self.sleep_single_device(idx)).pack(side="left", padx=2)
            ctk.CTkButton(act_box, text="🔥 Isıt", width=48, height=26, corner_radius=6, fg_color="#16a34a", hover_color="#15803d", font=("Segoe UI", 10, "bold"), command=lambda idx=i: self.start_single_warmup(idx)).pack(side="left", padx=2)

            self.row_widgets[i] = {
                "chk": chk_var, "ser": lbl_ser, "st": lbl_st,
                "name": ent_name, "proxy": ent_proxy, "persona": cmb_persona,
                "serial_val": None
            }

    # ==========================================================================
    # SEKME 2: KAMPANYA DAGITICI + KUYRUK TABLOSU
    # ==========================================================================
    def build_comment_phone_picker(self, parent):
        self.comment_phone_serials = set()
        self.comment_phone_widgets = {}
        box = ctk.CTkFrame(parent, fg_color="#0b1322", corner_radius=8)
        box.grid(row=1, column=0, columnspan=4, sticky="ew", pady=5)
        header = ctk.CTkFrame(box, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=4)
        self.lbl_comment_phones = ctk.CTkLabel(header, text="Yorum + Beğeni Telefonları: 0 seçili", text_color="#38bdf8", font=("Segoe UI", 11, "bold"))
        self.lbl_comment_phones.pack(side="left")
        ctk.CTkButton(header, text="Cihazları Yenile", height=24, width=110, command=self.refresh_devices).pack(side="right", padx=3)
        ctk.CTkButton(header, text="Seçimi Temizle", height=24, width=110, command=lambda: self.select_comment_phones(False)).pack(side="right", padx=3)
        ctk.CTkButton(header, text="Tüm ONLINE Telefonları Seç", height=24, width=180, command=lambda: self.select_comment_phones(True)).pack(side="right", padx=3)
        listing = ctk.CTkScrollableFrame(box, height=64, fg_color="transparent")
        listing.pack(fill="x", padx=6, pady=(0, 5))
        listing.grid_columnconfigure((0, 1), weight=1)
        for index in self.row_widgets:
            variable = tk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(listing, text="", variable=variable, height=24,
                font=("Segoe UI", 11), command=lambda i=index: self.toggle_comment_phone(i))
            checkbox.grid(row=(index-1)//2, column=(index-1)%2, sticky="w", padx=6, pady=3)
            self.comment_phone_widgets[index] = (variable, checkbox)
        self.refresh_comment_phones()

    def toggle_comment_phone(self, index):
        serial = self.row_widgets[index]["serial_val"]
        if serial:
            if self.comment_phone_widgets[index][0].get():
                self.comment_phone_serials.add(serial)
            else:
                self.comment_phone_serials.discard(serial)
        self.refresh_comment_phones()

    def select_comment_phones(self, select_all):
        self.comment_phone_serials = {w["serial_val"] for w in self.row_widgets.values() if w["serial_val"]} if select_all else set()
        self.refresh_comment_phones()

    def get_comment_phone_nodes(self):
        return [(i, f"NODE-{i:02d}", w["serial_val"], w["name"].get().strip(), w["persona"].get().strip())
                for i, w in self.row_widgets.items() if w["serial_val"] and w["serial_val"] in self.comment_phone_serials]

    def refresh_comment_phones(self):
        for index, (variable, checkbox) in self.comment_phone_widgets.items():
            w = self.row_widgets[index]
            serial = w["serial_val"]
            name = w["name"].get().strip()
            if len(name) > 30:
                name = name[:27] + "…"
            variable.set(bool(serial and serial in self.comment_phone_serials))
            checkbox.configure(text=f"NODE-{index:02d} | {name} | {'ONLINE' if serial else 'OFFLINE'}",
                               state="normal" if serial else "disabled",
                               text_color="#e2e8f0" if serial else "#64748b")
        count = len(self.get_comment_phone_nodes())
        self.lbl_comment_phones.configure(text=f"Yorum + Beğeni Telefonları: {count} ONLINE seçili (yalnızca bu işlem için)")
        if hasattr(self, "lbl_engagement_preview"):
            self.refresh_engagement_preview()

    def build_tab_campaign(self, parent):
        top_card = ctk.CTkFrame(parent, fg_color="#121f34", corner_radius=12, border_width=1, border_color="#24354d")
        top_card.pack(fill="x", pady=(0, 10))

        hdr_row = ctk.CTkFrame(top_card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkLabel(hdr_row, text="Kampanya Ayarları", font=("Segoe UI", 14, "bold"), text_color="#38bdf8").pack(side="left")

        self.var_rand_order = tk.BooleanVar(value=True)
        ctk.CTkSwitch(hdr_row, text="Rastgele Cihaz Sırası", variable=self.var_rand_order, font=("Segoe UI", 11, "bold")).pack(side="right", padx=10)

        self.build_timing_box(top_card, "campaign")

        grid_f = ctk.CTkFrame(top_card, fg_color="transparent")
        grid_f.pack(fill="x", padx=16, pady=(4, 12))
        grid_f.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(grid_f, text="💬 Hedef Gönderi & Sayılı Yorum:", font=("Segoe UI", 11, "bold"), text_color="#38bdf8").grid(row=0, column=0, sticky="w", pady=5, padx=(0, 10))
        self.ent_post_url = ctk.CTkEntry(grid_f, height=34, corner_radius=8)
        self.ent_post_url.insert(0, "https://www.facebook.com/...")
        self.ent_post_url.grid(row=0, column=1, sticky="ew", pady=5, padx=4)

        self.ent_comm_title = ctk.CTkEntry(grid_f, width=240, height=34, corner_radius=8)
        self.ent_comm_title.insert(0, "Harika paylaşım")
        self.ent_comm_title.grid(row=0, column=2, pady=5, padx=4)

        ctk.CTkButton(grid_f, text="🎯 Yorum + Beğeni Dağıt", width=190, height=34, corner_radius=8, fg_color="#3b82f6", hover_color="#1d4ed8", font=("Segoe UI", 11, "bold"), command=lambda: self.queue_and_run("YORUM+BEGENI")).grid(row=0, column=3, pady=5, padx=(4, 0))

        self.build_comment_phone_picker(grid_f)
        rates = ctk.CTkFrame(top_card, fg_color="#0b1526", corner_radius=9)
        rates.pack(fill="x", padx=16, pady=(0, 12))
        prefs = load_json("config/panel_preferences.json", {})
        for attr, label, value in [("ent_campaign_like", "Beğeni (%)", prefs.get("like_percent", 100)),
                                   ("ent_campaign_comment", "Yorum (%)", prefs.get("comment_percent", 100))]:
            ctk.CTkLabel(rates, text=label).pack(side="left", padx=(12, 6), pady=10)
            entry = ctk.CTkEntry(rates, width=65, height=30, justify="center")
            entry.insert(0, str(value))
            entry.pack(side="left")
            entry.bind("<KeyRelease>", lambda event: self.refresh_engagement_preview())
            setattr(self, attr, entry)
        self.lbl_engagement_preview = ctk.CTkLabel(rates, text="", text_color="#94a3b8")
        self.lbl_engagement_preview.pack(side="left", padx=16)

        for key, title, attr, hint, mode, action in [
            ("campaign_join", "Gruba Katılma", "ent_grp_url", "https://www.facebook.com/groups/...", "GRUP_KATIL", "Seçili Telefonlarla Katıl"),
            ("friend", "Arkadaş Ekleme", "ent_frd_url", "https://www.facebook.com/profile.php?id=...", "KISI_EKLE", "Kişiyi Ekle (Korumalı)")]:
            section = ctk.CTkFrame(top_card, fg_color="#0e192b", corner_radius=9)
            section.pack(fill="x", padx=16, pady=(0, 12))
            row = ctk.CTkFrame(section, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=10)
            ctk.CTkLabel(row, text=title, width=155, anchor="w", font=("Segoe UI", 12, "bold")).pack(side="left")
            entry = ctk.CTkEntry(row, height=34, placeholder_text=hint)
            entry.pack(side="left", fill="x", expand=True, padx=8)
            setattr(self, attr, entry)
            ctk.CTkButton(row, text=action, width=190, height=34,
                command=lambda task=mode: self.queue_and_run(task)).pack(side="right")
            self.build_operation_picker(section, key, title)

        q_card = ctk.CTkFrame(parent, fg_color="#121f34", corner_radius=12, border_width=1, border_color="#24354d")
        q_card.pack(fill="both", expand=True)

        q_bar = ctk.CTkFrame(q_card, fg_color="transparent")
        q_bar.pack(fill="x", padx=14, pady=8)
        ctk.CTkLabel(q_bar, text="Görev Kuyruğu", font=("Segoe UI", 13, "bold"), text_color="#f8fafc").pack(side="left")

        ctk.CTkButton(q_bar, text="🧹 Tamamlananları Temizle", width=170, height=30, corner_radius=8, fg_color="#334155", hover_color="#475569", font=("Segoe UI", 11, "bold"), command=self.clear_queue_table).pack(side="right", padx=4)
        ctk.CTkButton(q_bar, text="▶️ Bekleyen Kuyruğu Başlat", width=180, height=30, corner_radius=8, fg_color="#059669", hover_color="#047857", font=("Segoe UI", 11, "bold"), command=self.run_queue_worker).pack(side="right", padx=4)

        q_cols = ("id", "node", "fb_name", "persona", "type", "delay", "status")
        self.tree_q = ttk.Treeview(q_card, columns=q_cols, show="headings")
        headers = [
            ("id", "GÖREV ID", 70), ("node", "ATANAN CİHAZ", 100), ("fb_name", "FB HESAP İSMİ", 150),
            ("persona", "PERSONA DNA", 150), ("type", "İŞLEM TİPİ", 130),
            ("delay", "ZAMANLAMA", 100), ("status", "DETAY & DURUM", 380)
        ]
        for col_id, title, w in headers:
            self.tree_q.heading(col_id, text=title)
            self.tree_q.column(col_id, width=w, anchor="w")
        self.tree_q.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ==========================================================================
    # SEKME 3: TELEGRAM OTO-PAYLASIM & SECIMLI FACEBOOK GRUP BUTONLARI
    # ==========================================================================
    def build_timing_box(self, parent, scope):
        settings = timing.load(scope)
        box = ctk.CTkFrame(parent, fg_color="#0b1526", corner_radius=9)
        box.pack(fill="x", padx=20, pady=8)
        widgets = {}
        ctk.CTkLabel(box, text="Cihaz / görev arası (sn)", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(12, 4), pady=10)
        for key in ("delay_min", "delay_max"):
            entry = ctk.CTkEntry(box, width=55, height=30, justify="center")
            entry.insert(0, str(settings[key]))
            entry.pack(side="left", padx=3)
            widgets[key] = entry
        enabled = tk.BooleanVar(value=settings["prewarm_enabled"])
        ctk.CTkSwitch(box, text="Önce 30 sn ısınma", variable=enabled, font=("Segoe UI", 11)).pack(side="left", padx=14)
        ctk.CTkLabel(box, text="Isınma beğeni (%)").pack(side="left", padx=(0, 4))
        rate = ctk.CTkEntry(box, width=55, height=30, justify="center")
        rate.insert(0, str(settings["like_percent"]))
        rate.pack(side="left", padx=3)
        widgets.update(prewarm_enabled=enabled, like_percent=rate)
        self.timing_widgets[scope] = widgets
        ctk.CTkButton(box, text="Ayarları Kaydet", width=120, height=30, command=lambda: self.save_task_timing(scope)).pack(side="right", padx=10)
        if scope == "campaign":
            self.ent_wmin, self.ent_wmax = widgets["delay_min"], widgets["delay_max"]
            self.var_sandwich = enabled

    def task_timing(self, scope):
        w = self.timing_widgets[scope]
        settings = timing.validate({"delay_min": w["delay_min"].get(), "delay_max": w["delay_max"].get(),
            "prewarm_enabled": w["prewarm_enabled"].get(), "prewarm_seconds": 30, "like_percent": w["like_percent"].get()})
        return timing.save(scope, settings)

    def save_task_timing(self, scope):
        try:
            self.task_timing(scope)
            self.log("[AYARLAR] Bu bölümün cihaz aralığı ve ön ısınma ayarları kaydedildi.")
        except ValueError as exc:
            self.log(f"[!] {exc}")

    def build_operation_picker(self, parent, key, title):
        picker = PhonePicker(parent, self, title)
        picker.pack(fill="x", padx=20, pady=5)
        self.operation_pickers[key] = picker
        return picker

    def operation_nodes(self, key):
        return self.operation_pickers[key].nodes()

    def refresh_operation_phones(self):
        for picker in self.operation_pickers.values():
            picker.refresh()
        if hasattr(self, "lbl_engagement_preview"):
            self.refresh_engagement_preview()

    def build_tab_publish(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#121f34", corner_radius=12, border_width=1, border_color="#24354d")
        card.pack(fill="x", padx=6, pady=6)
        self.build_timing_box(card, "publish")
        ctk.CTkButton(card, text="Kayıtlı Paylaşım Sıraları / Devam Et", height=32, command=self.open_sequential_plans).pack(anchor="e", padx=20, pady=4)
        ctk.CTkLabel(card, text="01  Paylaşım İçeriği", font=("Segoe UI", 17, "bold"), text_color="#e2e8f0").pack(anchor="w", padx=20, pady=(16, 0))
        ctk.CTkLabel(card, text="Görsel ve başlık, aşağıdaki grup ve sayfa işlemlerinde ortak kullanılır.", text_color="#94a3b8").pack(anchor="w", padx=20)
        form = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=10)
        form.pack(fill="x", padx=20, pady=8)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Bilgisayardan Görsel Yükle:", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=14, pady=8)
        image_row = ctk.CTkFrame(form, fg_color="transparent")
        image_row.grid(row=0, column=1, sticky="ew", padx=14, pady=8)
        self.selected_image_path = ""
        ctk.CTkButton(image_row, text="📁 Görsel Seç", width=130, height=34,
                      command=self.choose_post_image).pack(side="left", padx=(0, 10))
        self.lbl_selected_image = ctk.CTkLabel(image_row, text="Henüz görsel seçilmedi (JPG / PNG / WEBP)", anchor="w")
        self.lbl_selected_image.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(form, text="Paylaşıma Eklenecek Ürün Başlığı:", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", padx=14, pady=8)
        self.ent_prod_title = ctk.CTkEntry(form, height=34, corner_radius=8)
        self.ent_prod_title.insert(0, "Fırsat Ürünü Stokta")
        self.ent_prod_title.grid(row=1, column=1, sticky="ew", padx=14, pady=8)

        act_row = ctk.CTkFrame(card, fg_color="transparent")
        act_row.pack(fill="x", padx=20, pady=(4, 14))
        watcher_available = os.path.isfile(os.path.join(os.path.dirname(__file__), "..", "keyword_watcher.py"))
        self.var_tg_autowatch = tk.BooleanVar(value=False)
        watcher_text = ("Paylaşım Sonrası Yalnız İzleme Nöbetçisini Başlat" if watcher_available
                        else "Nöbetçi kapalı (modül eksik). Paylaşım sonrası cihazlar uyutulur.")
        ctk.CTkSwitch(
            act_row, text=watcher_text,
            state="normal" if watcher_available else "disabled",
            variable=self.var_tg_autowatch, font=("Segoe UI", 11, "bold")
        ).pack(side="left")

        ctk.CTkLabel(parent, text="02  Hedefler ve Telefonlar", font=("Segoe UI", 17, "bold"), anchor="w").pack(fill="x", padx=24, pady=(12, 0))
        self.publish_targets = ctk.CTkTabview(parent, fg_color="#121f34", corner_radius=12,
            segmented_button_selected_color="#2563eb", height=660)
        self.publish_targets.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.publish_targets.add("Gruplar")
        self.publish_targets.add("Sayfalar")
        self.build_tab_telegram(self.publish_targets.tab("Gruplar"))
        self.build_tab_pages(self.publish_targets.tab("Sayfalar"))

    def build_tab_telegram(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#121f34", corner_radius=12, border_width=1, border_color="#24354d")
        card.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(
            card, text="Gruplar • Kayıtlı hedefler",
            font=("Segoe UI", 15, "bold"), text_color="#ec4899"
        ).pack(anchor="w", padx=20, pady=(14, 4))

        # 1. Grup Linki Ekleme ve Buton Olusturma Alani
        add_grp_bar = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=10)
        add_grp_bar.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(add_grp_bar, text="Yeni Grup Adı:", font=("Segoe UI", 11, "bold"), text_color="#38bdf8").pack(side="left", padx=(12, 4), pady=10)
        self.ent_new_grp_name = ctk.CTkEntry(add_grp_bar, width=180, height=32, placeholder_text="Örn: İndirim Grubu 1")
        self.ent_new_grp_name.pack(side="left", padx=4, pady=10)

        ctk.CTkLabel(add_grp_bar, text="Facebook Grup Linki:", font=("Segoe UI", 11, "bold"), text_color="#38bdf8").pack(side="left", padx=(10, 4), pady=10)
        self.ent_new_grp_url = ctk.CTkEntry(add_grp_bar, height=32, placeholder_text="https://www.facebook.com/groups/...")
        self.ent_new_grp_url.pack(side="left", fill="x", expand=True, padx=4, pady=10)

        ctk.CTkButton(
            add_grp_bar, text="➕ Facebook Grup Butonu Ekle", height=32, corner_radius=8,
            fg_color="#16a34a", hover_color="#15803d", font=("Segoe UI", 11, "bold"),
            command=self.add_group_button
        ).pack(side="left", padx=6, pady=10)

        # 2. Secilebilir Grup Butonlari (Tiklanabilir Buton Havuzu)
        grp_pool_hdr = ctk.CTkFrame(card, fg_color="transparent")
        grp_pool_hdr.pack(fill="x", padx=20, pady=(4, 2))
        ctk.CTkLabel(grp_pool_hdr, text="📌 Paylaşım Yapılacak Facebook Grupları (Göndermek İstediğin Gruplara Tıkla / Seç):", font=("Segoe UI", 12, "bold"), text_color="#facc15").pack(side="left")
        ctk.CTkButton(grp_pool_hdr, text="☑️ Tüm Grupları Seç", width=130, height=26, fg_color="#334155", font=("Segoe UI", 10, "bold"), command=lambda: self.toggle_all_group_btns(True)).pack(side="right", padx=4)
        ctk.CTkButton(grp_pool_hdr, text="⬜ Seçimi Kaldır", width=110, height=26, fg_color="#334155", font=("Segoe UI", 10), command=lambda: self.toggle_all_group_btns(False)).pack(side="right", padx=4)

        self.grp_buttons_frame = ctk.CTkScrollableFrame(card, height=150, fg_color="#0b0f19", corner_radius=10)
        self.grp_buttons_frame.pack(fill="x", padx=20, pady=4)
        self.render_group_buttons()

        self.build_operation_picker(card, "group_share", "Grup Paylaşımı")
        ctk.CTkButton(card, text="Görsel ve Başlığı Seçili Gruplarda Paylaş", height=38,
            fg_color="#2563eb", command=self.start_telegram_pipeline).pack(fill="x", padx=20, pady=(2, 10))
        self.build_operation_picker(card, "group_join", "Seçili Gruplara Katılma")
        ctk.CTkButton(card, text="Seçilen Telefonları Seçili Gruplara Katılmaya Gönder", height=34,
            fg_color="#243e61", command=self.join_selected_group_buttons).pack(fill="x", padx=20, pady=(2, 14))

    def choose_post_image(self):
        path = filedialog.askopenfilename(
            parent=self, title="Paylaşılacak görseli seçin",
            filetypes=[("Görseller", "*.jpg *.jpeg *.png *.webp"), ("Tüm Dosyalar", "*.*")])
        if not path:
            return
        try:
            path = validate_image(path)
        except ValueError as exc:
            self.log(f"[!] {exc}")
            return
        self.selected_image_path = path
        filename = os.path.basename(path)
        display_name = filename if len(filename) <= 65 else filename[:30] + "…" + filename[-30:]
        self.lbl_selected_image.configure(text=display_name, text_color="#4ade80")
        self.log(f"[GÖRSEL SEÇİLDİ] {path}")

    def render_group_buttons(self):
        for widget in self.grp_buttons_frame.winfo_children():
            widget.destroy()
        self.group_btn_vars.clear()

        for idx, grp in enumerate(self.saved_groups):
            row_f = ctk.CTkFrame(self.grp_buttons_frame, fg_color="#16253c", corner_radius=8)
            row_f.grid(row=idx // 3, column=idx % 3, padx=6, pady=5, sticky="ew")
            self.grp_buttons_frame.grid_columnconfigure(idx % 3, weight=1)

            var = tk.BooleanVar(value=grp.get("selected", True))
            self.group_btn_vars.append((var, grp))

            cb = ctk.CTkCheckBox(
                row_f, text=f"👥 {grp['name']} ({grp['url'][:28]}...)",
                variable=var, font=("Segoe UI", 11, "bold"), text_color="#f8fafc",
                fg_color="#16a34a", hover_color="#15803d",
                command=self.save_group_selections
            )
            cb.pack(side="left", padx=10, pady=8)

            ctk.CTkButton(
                row_f, text="✕", width=26, height=24, corner_radius=6,
                fg_color="#dc2626", hover_color="#b91c1c", font=("Segoe UI", 10, "bold"),
                command=lambda i=idx: self.remove_group_button(i)
            ).pack(side="right", padx=6, pady=6)

    def add_group_button(self):
        name = self.ent_new_grp_name.get().strip() or f"Grup #{len(self.saved_groups)+1}"
        url = self.ent_new_grp_url.get().strip()
        if not url or "facebook.com" not in url:
            self.log("[!] Geçerli bir Facebook grup linki girin!")
            return
        self.saved_groups.append({"name": name, "url": url, "selected": True})
        save_json(GROUPS_FILE, self.saved_groups)
        self.ent_new_grp_name.delete(0, "end")
        self.ent_new_grp_url.delete(0, "end")
        self.render_group_buttons()
        self.lbl_kpi_acc.configure(text=f"{len(self.saved_groups)} Grup | {len(self.saved_pages)} Sayfa")
        self.log(f"[GRUP BUTONU EKLENDİ] '{name}' ({url}) seçilebilir buton olarak eklendi.")

    def remove_group_button(self, index):
        if 0 <= index < len(self.saved_groups):
            removed = self.saved_groups.pop(index)
            save_json(GROUPS_FILE, self.saved_groups)
            self.render_group_buttons()
            self.lbl_kpi_acc.configure(text=f"{len(self.saved_groups)} Grup | {len(self.saved_pages)} Sayfa")
            self.log(f"[SİLİNDİ] '{removed['name']}' grup butonu kaldırıldı.")

    def save_group_selections(self):
        for var, grp in self.group_btn_vars:
            grp["selected"] = bool(var.get())
        save_json(GROUPS_FILE, self.saved_groups)

    def toggle_all_group_btns(self, state):
        for var, grp in self.group_btn_vars:
            var.set(state)
            grp["selected"] = state
        save_json(GROUPS_FILE, self.saved_groups)

    def join_selected_group_buttons(self):
        self.save_group_selections()
        urls = [g["url"] for g in self.saved_groups if g.get("selected")]
        selected = self.operation_nodes("group_join")
        if not urls or not selected:
            self.log("[!] Katılma için en az bir grup ve bu işleme ait ONLINE telefon seçin.")
            return
        code = f"CMP-{uuid.uuid4().hex}"
        queued = False
        for url in urls:
            queued = bool(self.queue_custom_task("GRUP_KATIL", url, "Gruba Katıl", selected, code, timing_scope="publish")) or queued
        if queued:
            self.run_queue_worker(code)

    # ==========================================================================
    # SEKME 4: SAYFALAR (PAGES) BOLUMU
    # ==========================================================================
    def build_tab_pages(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#121f34", corner_radius=12, border_width=1, border_color="#24354d")
        card.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(
            card, text="📄 Facebook Sayfalar (Pages) Yönetim & Etkileşim Merkezi",
            font=("Segoe UI", 15, "bold"), text_color="#a855f7"
        ).pack(anchor="w", padx=20, pady=(14, 4))
        ctk.CTkLabel(
            card, text="Sayfaları kaydet ve seç. Görsel ile başlık üstteki ortak içerik alanından alınır; her işlem kendi telefon seçimini kullanır.",
            font=("Segoe UI", 11), text_color="#94a3b8"
        ).pack(anchor="w", padx=20, pady=(0, 10))

        add_pg_bar = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=10)
        add_pg_bar.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(add_pg_bar, text="Sayfa Adı:", font=("Segoe UI", 11, "bold"), text_color="#c084fc").pack(side="left", padx=(12, 4), pady=10)
        self.ent_new_pg_name = ctk.CTkEntry(add_pg_bar, width=180, height=32, placeholder_text="Örn: Mağaza Sayfamız")
        self.ent_new_pg_name.pack(side="left", padx=4, pady=10)

        ctk.CTkLabel(add_pg_bar, text="Sayfa Linki:", font=("Segoe UI", 11, "bold"), text_color="#c084fc").pack(side="left", padx=(10, 4), pady=10)
        self.ent_new_pg_url = ctk.CTkEntry(add_pg_bar, height=32, placeholder_text="https://www.facebook.com/sayfa_adi")
        self.ent_new_pg_url.pack(side="left", fill="x", expand=True, padx=4, pady=10)

        ctk.CTkButton(
            add_pg_bar, text="➕ Sayfa Butonu Ekle", height=32, corner_radius=8,
            fg_color="#9333ea", hover_color="#7e22ce", font=("Segoe UI", 11, "bold"),
            command=self.add_page_button
        ).pack(side="left", padx=10, pady=10)

        self.pg_buttons_frame = ctk.CTkScrollableFrame(card, height=140, fg_color="#0b0f19", corner_radius=10)
        self.pg_buttons_frame.pack(fill="x", padx=20, pady=8)
        self.render_page_buttons()

        self.build_operation_picker(card, "page_follow", "Sayfa Beğeni / Takip / Son Gönderi")
        ctk.CTkButton(card, text="Seçili Sayfaları Beğen, Takip Et ve Son Gönderiyi Beğen", height=38,
            fg_color="#7c3aed", command=self.follow_selected_pages).pack(fill="x", padx=20, pady=(2, 10))
        self.build_operation_picker(card, "page_share", "Sayfa Görsel Paylaşımı")
        ctk.CTkButton(card, text="Ortak Görsel ve Başlığı Seçili Sayfalarda Paylaş", height=38,
            fg_color="#2563eb", command=self.share_telegram_on_selected_pages).pack(fill="x", padx=20, pady=(2, 14))

    def render_page_buttons(self):
        for widget in self.pg_buttons_frame.winfo_children():
            widget.destroy()
        self.page_btn_vars.clear()

        for idx, pg in enumerate(self.saved_pages):
            row_f = ctk.CTkFrame(self.pg_buttons_frame, fg_color="#16253c", corner_radius=8)
            row_f.grid(row=idx // 3, column=idx % 3, padx=6, pady=5, sticky="ew")
            self.pg_buttons_frame.grid_columnconfigure(idx % 3, weight=1)

            var = tk.BooleanVar(value=pg.get("selected", True))
            self.page_btn_vars.append((var, pg))

            cb = ctk.CTkCheckBox(
                row_f, text=f"📄 {pg['name']} ({pg['url'][:28]}...)",
                variable=var, font=("Segoe UI", 11, "bold"), text_color="#f8fafc",
                fg_color="#9333ea", hover_color="#7e22ce",
                command=self.save_page_selections
            )
            cb.pack(side="left", padx=10, pady=8)

            ctk.CTkButton(
                row_f, text="✕", width=26, height=24, corner_radius=6,
                fg_color="#dc2626", hover_color="#b91c1c", font=("Segoe UI", 10, "bold"),
                command=lambda i=idx: self.remove_page_button(i)
            ).pack(side="right", padx=6, pady=6)

    def add_page_button(self):
        name = self.ent_new_pg_name.get().strip() or f"Sayfa #{len(self.saved_pages)+1}"
        url = self.ent_new_pg_url.get().strip()
        if not url or "facebook.com" not in url:
            self.log("[!] Geçerli bir Facebook sayfa linki girin!")
            return
        self.saved_pages.append({"name": name, "url": url, "selected": True})
        save_json(PAGES_FILE, self.saved_pages)
        self.ent_new_pg_name.delete(0, "end")
        self.ent_new_pg_url.delete(0, "end")
        self.render_page_buttons()
        self.lbl_kpi_acc.configure(text=f"{len(self.saved_groups)} Grup | {len(self.saved_pages)} Sayfa")
        self.log(f"[SAYFA EKLENDİ] '{name}' sayfası buton olarak kaydedildi.")

    def remove_page_button(self, index):
        if 0 <= index < len(self.saved_pages):
            removed = self.saved_pages.pop(index)
            save_json(PAGES_FILE, self.saved_pages)
            self.render_page_buttons()
            self.lbl_kpi_acc.configure(text=f"{len(self.saved_groups)} Grup | {len(self.saved_pages)} Sayfa")
            self.log(f"[SİLİNDİ] '{removed['name']}' sayfası kaldırıldı.")

    def save_page_selections(self):
        for var, pg in self.page_btn_vars:
            pg["selected"] = bool(var.get())
        save_json(PAGES_FILE, self.saved_pages)

    def follow_selected_pages(self):
        self.save_page_selections()
        urls = [p["url"] for p in self.saved_pages if p.get("selected")]
        selected = self.operation_nodes("page_follow")
        if not urls or not selected:
            self.log("[!] Sayfa etkileşimi için en az bir sayfa ve bu işleme ait ONLINE telefon seçin.")
            return
        code = f"CMP-{uuid.uuid4().hex}"
        queued = False
        for url in urls:
            queued = bool(self.queue_custom_task("SAYFA_ETKILESIM", url, "Sayfa Beğen & Takip Et", selected, code, timing_scope="publish")) or queued
        if queued:
            self.run_queue_worker(code)

    def share_telegram_on_selected_pages(self):
        self.save_page_selections()
        urls = [p["url"] for p in self.saved_pages if p.get("selected")]
        if not urls:
            self.log("[!] Paylaşım için en az 1 sayfa butonu seçin!")
            return
        self.run_telegram_to_targets(",".join(urls), "page_share")

    # ==========================================================================
    # SEKME 5: DOGAL SIKAYET ETME (REPORT) MERKEZI
    # ==========================================================================
    def build_tab_report(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#121f34", corner_radius=12, border_width=1, border_color="#24354d")
        card.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            card, text="🚩 Doğal Biyometrik Şikayet (Report) Operasyon Merkezi",
            font=("Segoe UI", 16, "bold"), text_color="#f87171"
        ).pack(anchor="w", padx=24, pady=(18, 6))
        ctk.CTkLabel(
            card,
            text="Hedef Kişi Hesabı, Grup veya Sayfa linkini girdiğinde cihazlar önce organik sandviç gezinmesi yapar,\nardından hedef sayfayı doğal sürelerle inceleyip 3 nokta menüsünden şikayet adımlarını tamamlar ve uygulamayı kapatır.",
            justify="left", font=("Segoe UI", 12), text_color="#94a3b8"
        ).pack(anchor="w", padx=24, pady=(0, 18))

        self.build_timing_box(card, "report")

        form = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=12)
        form.pack(fill="x", padx=24, pady=10)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Şikayet Edilecek Link (Kişi / Grup / Sayfa):", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=14)
        self.ent_rep_url = ctk.CTkEntry(form, height=36, corner_radius=8, placeholder_text="https://www.facebook.com/...")
        self.ent_rep_url.grid(row=0, column=1, sticky="ew", padx=18, pady=14)

        ctk.CTkLabel(form, text="Şikayet Kategorisi (Neden):", font=("Segoe UI", 12, "bold")).grid(row=1, column=0, sticky="w", padx=18, pady=14)
        self.cmb_rep_reason = ctk.CTkComboBox(
            form, values=["SAHTE (Sahte Hesap / Taklit)", "SPAM (Dolandırıcılık / Yanıltıcı / Spam)", "TACIZ (Zorbalık / Taciz)", "UYGUNSUZ (Nefret Söylemi / Uygunsuz İçerik)"],
            height=36, width=380
        )
        self.cmb_rep_reason.set("SAHTE (Sahte Hesap / Taklit)")
        self.cmb_rep_reason.grid(row=1, column=1, sticky="w", padx=18, pady=14)

        self.build_operation_picker(card, "report", "Şikayet İşlemi")

        ctk.CTkButton(
            card, text="🚩 Seçili Tüm Cihazlarla Doğal Şikayet Operasyonunu Başlat",
            height=46, corner_radius=10, fg_color="#dc2626", hover_color="#b91c1c", font=("Segoe UI", 13, "bold"),
            command=self.start_natural_report
        ).pack(fill="x", padx=24, pady=20)

    def start_natural_report(self):
        url = self.ent_rep_url.get().strip()
        if not url or "facebook.com" not in url:
            self.log("[!] Şikayet edilecek geçerli bir Facebook linki girin!")
            return
        reason_code = self.cmb_rep_reason.get().split()[0]
        code = self.queue_custom_task("SIKAYET_ET", url, reason_code, self.operation_nodes("report"), timing_scope="report")
        if code:
            self.select_tab("tab_campaign")
            self.run_queue_worker(code)

    # ==========================================================================
    # SEKME 6: GRUP & ANAHTAR KELIME NOBETCISI (16 DK / MAX 3 CEVAP)
    # ==========================================================================
    def build_watcher_phone_picker(self, parent):
        self.watcher_phone_serials = set(self.load_watch_cfg().get("selected_serials", []))
        self.watcher_phone_widgets = {}
        box = ctk.CTkFrame(parent, fg_color="#0b1322", corner_radius=8)
        box.grid(row=1, column=0, columnspan=4, sticky="ew", pady=5)
        header = ctk.CTkFrame(box, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=4)
        self.lbl_watcher_phones = ctk.CTkLabel(header, text="Nöbetçi Telefonları: 0 seçili", text_color="#38bdf8", font=("Segoe UI", 11, "bold"))
        self.lbl_watcher_phones.pack(side="left")
        ctk.CTkButton(header, text="Cihazları Yenile", height=24, width=110, command=self.refresh_devices).pack(side="right", padx=3)
        ctk.CTkButton(header, text="Seçimi Temizle", height=24, width=110, command=lambda: self.select_watcher_phones(False)).pack(side="right", padx=3)
        ctk.CTkButton(header, text="Tüm ONLINE Telefonları Seç", height=24, width=180, command=lambda: self.select_watcher_phones(True)).pack(side="right", padx=3)
        listing = ctk.CTkScrollableFrame(box, height=64, fg_color="transparent")
        listing.pack(fill="x", padx=6, pady=(0, 5))
        listing.grid_columnconfigure((0, 1), weight=1)
        for index in self.row_widgets:
            variable = tk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(listing, text="", variable=variable, height=24,
                font=("Segoe UI", 11), command=lambda i=index: self.toggle_watcher_phone(i))
            checkbox.grid(row=(index-1)//2, column=(index-1)%2, sticky="w", padx=6, pady=3)
            self.watcher_phone_widgets[index] = (variable, checkbox)
        self.refresh_watcher_phones()

    def toggle_watcher_phone(self, index):
        serial = self.row_widgets[index]["serial_val"]
        if serial:
            if self.watcher_phone_widgets[index][0].get():
                self.watcher_phone_serials.add(serial)
            else:
                self.watcher_phone_serials.discard(serial)
        self.refresh_watcher_phones()

    def select_watcher_phones(self, select_all):
        self.watcher_phone_serials = {w["serial_val"] for w in self.row_widgets.values() if w["serial_val"]} if select_all else set()
        self.refresh_watcher_phones()

    def get_watcher_phone_nodes(self):
        return [(i, f"NODE-{i:02d}", w["serial_val"], w["name"].get().strip(), w["persona"].get().strip())
                for i, w in self.row_widgets.items() if w["serial_val"] and w["serial_val"] in self.watcher_phone_serials]

    def refresh_watcher_phones(self):
        for index, (variable, checkbox) in self.watcher_phone_widgets.items():
            w = self.row_widgets[index]
            serial = w["serial_val"]
            name = w["name"].get().strip()
            if len(name) > 30:
                name = name[:27] + "…"
            variable.set(bool(serial and serial in self.watcher_phone_serials))
            checkbox.configure(text=f"NODE-{index:02d} | {name} | {'ONLINE' if serial else 'OFFLINE'}",
                               state="normal" if serial else "disabled",
                               text_color="#e2e8f0" if serial else "#64748b")
        count = len(self.get_watcher_phone_nodes())
        self.lbl_watcher_phones.configure(text=f"Nöbetçi Telefonları: {count} ONLINE seçili (yalnızca bu işlem için)")

    def build_tab_watcher(self, parent):
        watch_cfg = self.load_watch_cfg()
        card = ctk.CTkScrollableFrame(parent, fg_color="#121f34", corner_radius=12, border_width=1, border_color="#24354d")
        card.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(card, text="🔍 Grup Gönderileri Nöbetçisi — Anahtar Kelime Yanıtları", font=("Segoe UI", 15, "bold"), text_color="#facc15").pack(anchor="w", padx=20, pady=(14, 4))

        self.build_timing_box(card, "watcher")

        f_grid = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=10)
        f_grid.pack(fill="x", padx=20, pady=6)
        f_grid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(f_grid, text="İzlenecek Grup / Gönderi Linki:", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=14, pady=8)
        self.ent_watch_url = ctk.CTkEntry(f_grid, height=34, corner_radius=8)
        self.ent_watch_url.insert(0, "https://www.facebook.com/groups/...")
        self.ent_watch_url.grid(row=0, column=1, sticky="ew", padx=6, pady=8)

        ctk.CTkButton(f_grid, text="➕ Listeye Ekle", width=130, height=34, corner_radius=8, fg_color="#ca8a04", hover_color="#a16207", font=("Segoe UI", 11, "bold"), command=self.add_watched_post).grid(row=0, column=2, padx=4, pady=8)
        ctk.CTkButton(f_grid, text="🧹 Listeyi Temizle", width=130, height=34, corner_radius=8, fg_color="#475569", hover_color="#334155", font=("Segoe UI", 11), command=self.clear_watched_posts).grid(row=0, column=3, padx=(4, 14), pady=8)

        ctk.CTkLabel(f_grid, text="Anahtar Kelimeler (Virgülle):", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", padx=14, pady=8)
        self.ent_keywords = ctk.CTkEntry(f_grid, height=34, corner_radius=8)
        self.ent_keywords.insert(0, watch_cfg.get("keywords", "fiyat, link, bilgi"))
        self.ent_keywords.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(6, 14), pady=8)

        ctk.CTkLabel(f_grid, text="Yanıt Metni:", font=("Segoe UI", 11, "bold")).grid(row=2, column=0, sticky="w", padx=14, pady=8)
        self.ent_kw_reply = ctk.CTkEntry(f_grid, height=34, corner_radius=8)
        self.ent_kw_reply.insert(0, watch_cfg.get("reply_template", "Merhaba, hangi konuda bilgi almak istersiniz?"))
        self.ent_kw_reply.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(6, 14), pady=8)

        keyword_box = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=10)
        keyword_box.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(keyword_box, text="Kayıtlı Anahtar Kelimeler (birden fazla seçebilirsin)", anchor="w").pack(fill="x", padx=12, pady=(8, 4))
        list_row = ctk.CTkFrame(keyword_box, fg_color="transparent")
        list_row.pack(fill="x", padx=12, pady=(0, 10))
        self.lst_saved_keywords = tk.Listbox(list_row, selectmode=tk.EXTENDED, exportselection=False,
            height=4, bg="#101827", fg="#e2e8f0", selectbackground="#2563eb", relief="flat",
            highlightthickness=0, font=("Segoe UI", 11))
        self.lst_saved_keywords.pack(side="left", fill="x", expand=True)
        keyword_scroll = ttk.Scrollbar(list_row, orient="vertical", command=self.lst_saved_keywords.yview)
        keyword_scroll.pack(side="left", fill="y")
        self.lst_saved_keywords.configure(yscrollcommand=keyword_scroll.set)
        keyword_actions = ctk.CTkFrame(list_row, fg_color="transparent")
        keyword_actions.pack(side="left", padx=(10, 0))
        ctk.CTkButton(keyword_actions, text="Kelimeleri Kaydet", command=self.save_watcher_keywords).pack(pady=2)
        ctk.CTkButton(keyword_actions, text="Seçilenleri Ekle", command=self.add_saved_watcher_keywords).pack(pady=2)
        self.lst_saved_keywords.bind("<Double-Button-1>", lambda event: self.add_saved_watcher_keywords())
        self.ent_keywords.bind("<FocusOut>", lambda event: self.save_watcher_keywords())
        self.ent_keywords.bind("<Return>", lambda event: self.save_watcher_keywords())
        self.refresh_saved_watcher_keywords()

        mode_row = ctk.CTkFrame(card, fg_color="transparent")
        mode_row.pack(fill="x", padx=20, pady=6)
        self.var_watcher_auto = tk.BooleanVar(value=bool(watch_cfg.get("auto_reply_enabled", False)))
        self.var_watcher_owned = tk.BooleanVar(value=bool(watch_cfg.get("owned_targets_confirmed", False)))
        ctk.CTkSwitch(mode_row, text="Otomatik Yanıt (English Facebook)", variable=self.var_watcher_auto,
                      command=self.refresh_watcher_engine_status).pack(side="left", padx=(0, 14))
        ctk.CTkCheckBox(mode_row, text="Hedef gruplar/gönderiler benim yönetimimde", variable=self.var_watcher_owned).pack(side="left")

        sequence_row = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=9)
        sequence_row.pack(fill="x", padx=20, pady=6)
        self.var_watcher_sequential = tk.BooleanVar(value=bool(watch_cfg.get("sequential_enabled", True)))
        ctk.CTkCheckBox(sequence_row, text="Sıralı ve dengeli dağıtım", variable=self.var_watcher_sequential,
            command=self.refresh_watcher_engine_status).pack(side="left", padx=12, pady=10)
        ctk.CTkLabel(sequence_row, text="Yanıtlar arası bekleme (sn):").pack(side="left", padx=8)
        self.ent_reply_gap = ctk.CTkEntry(sequence_row, width=70, justify="center")
        self.ent_reply_gap.insert(0, str(watch_cfg.get("reply_delay_seconds", 10)))
        self.ent_reply_gap.pack(side="left", padx=4)
        ctk.CTkButton(sequence_row, text="Bekleyen Sıralar / Devam Et", command=self.open_sequential_plans).pack(side="right", padx=10)

        phone_area = ctk.CTkFrame(card, fg_color="transparent")
        phone_area.pack(fill="x", padx=20, pady=4)
        self.build_watcher_phone_picker(phone_area)
        self.watcher_engine_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "keyword_watcher.py"))
        self.lbl_watcher_engine = ctk.CTkLabel(card, text="", font=("Segoe UI", 11), anchor="w")
        self.lbl_watcher_engine.pack(fill="x", padx=20, pady=(0, 4))
        self.refresh_watcher_engine_status()

        opt_row = ctk.CTkFrame(card, fg_color="transparent")
        opt_row.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(opt_row, text="Kontrol Periyodu (Dakika):", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 8))
        self.ent_cycle_min = ctk.CTkEntry(opt_row, width=65, height=34, justify="center", font=("Segoe UI", 12, "bold"))
        self.ent_cycle_min.insert(0, str(watch_cfg.get("cycle_minutes", 16)))
        self.ent_cycle_min.pack(side="left", padx=(0, 24))

        ctk.CTkLabel(opt_row, text="Turda Hedef Başına Yanıt / Eşleşme Sınırı:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 8))
        self.ent_max_rep = ctk.CTkEntry(opt_row, width=65, height=34, justify="center", font=("Segoe UI", 12, "bold"))
        self.ent_max_rep.insert(0, str(watch_cfg.get("max_replies_per_visit", 3)))
        self.ent_max_rep.pack(side="left", padx=(0, 24))

        ctk.CTkButton(
            opt_row, text="▶️ Nöbetçiyi Başlat / Devam Et", height=38, width=260, corner_radius=8,
            fg_color="#d97706", hover_color="#b45309", font=("Segoe UI", 12, "bold"),
            command=self.start_keyword_watcher
        ).pack(side="right")

        monitor_row = ctk.CTkFrame(card, fg_color="transparent")
        monitor_row.pack(fill="x", padx=20, pady=4)
        ctk.CTkButton(monitor_row, text="Nöbetçi Takip Ekranını Aç", command=self.open_watcher_monitor, width=220).pack(side="left", padx=(0, 8))
        ctk.CTkButton(monitor_row, text="Nöbetçiyi Durdur", command=self.stop_keyword_watcher, width=160, fg_color="#be123c").pack(side="left")
        self.lbl_watch_live = ctk.CTkLabel(monitor_row, text="İzleme henüz başlamadı.", anchor="w")
        self.lbl_watch_live.pack(side="left", padx=12)

        self.lbl_watch_count = ctk.CTkLabel(card, text="İzlenen Gönderi Listesi (0 Adet):", font=("Segoe UI", 12, "bold"), text_color="#38bdf8")
        self.lbl_watch_count.pack(anchor="w", padx=20, pady=(4, 4))

        self.txt_watched_list = ctk.CTkTextbox(card, height=130, fg_color="#0b0f19", text_color="#cbd5e1", font=("Consolas", 11), corner_radius=8)
        self.txt_watched_list.pack(fill="both", expand=True, padx=20, pady=(0, 12))

    # ==========================================================================
    # SEKME 7: AKILLI HESAP ISITMA MERKEZI
    # ==========================================================================
    def build_tab_warmup(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#121f34", corner_radius=12, border_width=1, border_color="#24354d")
        card.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(card, text="🔥 Biyometrik Facebook Hesap Isıtma & Donma Kurtarıcı Stüdyosu", font=("Segoe UI", 16, "bold"), text_color="#facc15").pack(anchor="w", padx=24, pady=(20, 6))
        ctk.CTkLabel(
            card,
            text="Cihazlar dikey modda ana akışta insan gibi gezinir ve beğeni bırakır. Isıtma bittiğinde Facebook ve TikTok kapatılıp ekran uyutulur.",
            justify="left", font=("Segoe UI", 12), text_color="#94a3b8"
        ).pack(anchor="w", padx=24, pady=(0, 20))

        form = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=12)
        form.pack(fill="x", padx=24, pady=10)

        r1 = ctk.CTkFrame(form, fg_color="transparent")
        r1.pack(fill="x", padx=20, pady=16)

        ctk.CTkLabel(r1, text="Isıtma Oturum Süresi (Dakika):", font=("Segoe UI", 13, "bold")).pack(side="left", padx=(0, 10))
        self.ent_warm_min = ctk.CTkEntry(r1, width=80, height=36, justify="center", font=("Segoe UI", 13, "bold"))
        self.ent_warm_min.insert(0, "30")
        self.ent_warm_min.pack(side="left", padx=(0, 30))

        ctk.CTkLabel(r1, text="Organik Gönderi Beğeni Oranı (%):", font=("Segoe UI", 13, "bold")).pack(side="left", padx=(0, 10))
        self.ent_warm_like = ctk.CTkEntry(r1, width=80, height=36, justify="center", font=("Segoe UI", 13, "bold"))
        self.ent_warm_like.insert(0, "15")
        self.ent_warm_like.pack(side="left", padx=(0, 30))

        self.var_auto_warm = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            r1, text="Açılışta görevler bekler — elle başlatılır", state="disabled",
            variable=self.var_auto_warm, font=("Segoe UI", 12, "bold")
        ).pack(side="left", padx=10)

        prefs = load_json("config/warmup_preferences.json", {})
        self.ent_warm_like.delete(0, "end")
        self.ent_warm_like.insert(0, str(prefs.get("like_percent", 15)))
        pool = ctk.CTkFrame(card, fg_color="#0e192b", corner_radius=10)
        pool.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(pool, text="Hazır yorum taslakları — otomatik gönderilmez; bir satıra bir yorum", anchor="w").pack(fill="x", padx=12, pady=6)
        self.txt_warm_drafts = ctk.CTkTextbox(pool, height=80)
        self.txt_warm_drafts.pack(fill="x", padx=12, pady=4)
        defaults = ["Paylaşım için teşekkürler.", "Güzel paylaşım.", "Emeğinize sağlık.", "Faydalı olmuş, teşekkürler.", "Çok hoş görünüyor."]
        self.txt_warm_drafts.insert("1.0", "\n".join(prefs.get("drafts", defaults)))
        row = ctk.CTkFrame(pool, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)
        self.ent_warm_draft = ctk.CTkEntry(row)
        self.ent_warm_draft.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(row, text="Taslak Seç / Kopyala", command=self.pick_warmup_draft).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Isınma Ayarlarını Kaydet", command=self.save_warmup_preferences).pack(side="left", padx=4)

        self.build_operation_picker(card, "warmup", "Hesap Isıtma")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=16)

        ctk.CTkButton(
            btn_row, text="▶️ Seçili Tüm Cihazları Şimdi Isıtmaya Al", height=44, width=300, corner_radius=10,
            fg_color="#16a34a", hover_color="#15803d", font=("Segoe UI", 13, "bold"),
            command=self.start_selected_warmup
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            btn_row, text="📴 Isıtmayı Durdur & Ekranları Kapat", height=44, width=260, corner_radius=10,
            fg_color="#e11d48", hover_color="#be123c", font=("Segoe UI", 13, "bold"),
            command=self.stop_selected_warmup
        ).pack(side="left")

    # ==========================================================================
    # YARDIMCI FONKSIYONLAR
    # ==========================================================================
    def log(self, msg):
        if threading.get_ident() != self.ui_thread:
            self.ui_events.put(("log", str(msg)))
            return
        line = time.strftime("%H:%M:%S") + "  " + str(msg) + "\n"
        self.txt_log.insert("end", line)
        self.txt_log.see("end")
        # Keep the live drawer bounded during long-running monitoring.
        if int(self.txt_log.index("end-1c").split(".")[0]) > 3000:
            self.txt_log.delete("1.0", "500.0")
        preview = str(msg).replace("\n", " ")
        self.lbl_log_preview.configure(text=preview[:78] + ("…" if len(preview) > 78 else ""))

    def select_only_online(self):
        for w in self.row_widgets.values():
            w["chk"].set(bool(w["serial_val"]))

    def get_selected_online_nodes(self):
        nodes = []
        for i, w in self.row_widgets.items():
            if w["chk"].get() and w["serial_val"]:
                nodes.append((i, f"NODE-{i:02d}", w["serial_val"], w["name"].get().strip(), w["persona"].get().strip()))
        return nodes

    def save_all_profiles(self):
        for i, w in self.row_widgets.items():
            self.profiles[f"NODE-{i:02d}"] = {
                "fb_name": w["name"].get().strip(),
                "proxy": w["proxy"].get().strip(),
                "persona": w["persona"].get().strip()
            }
        save_json(PROF_FILE, self.profiles)
        self.log("[KAYDEDİLDİ] Tüm Facebook İsim Soyisim, Proxy ve Persona DNA ayarları kaydedildi.")

    def refresh_devices(self):
        if self.device_scan_running:
            self.log("[TARAMA] Cihaz taraması zaten sürüyor.")
            return
        self.device_scan_running = True
        self.log("[TARAMA] Telefon bağlantıları ve durumları okunuyor…")
        threading.Thread(target=self._refresh_devices_bg, daemon=True).start()

    def _refresh_devices_bg(self):
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=15)
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "ADB cihaz listesi okunamadı.")
            serials = [parts[0] for line in result.stdout.splitlines()[1:] if len(parts := line.split()) >= 2 and parts[1] == "device"]
            devices = []
            for serial in serials[:25]:
                item = {"serial": serial, "vpn": False, "temp": None}
                try:
                    vpn = subprocess.run(["adb", "-s", serial, "shell", "ip", "addr", "show", "tun0"], capture_output=True, text=True, timeout=8)
                    battery = subprocess.run(["adb", "-s", serial, "shell", "dumpsys", "battery"], capture_output=True, text=True, timeout=8)
                    item["vpn"] = vpn.returncode == 0 and "inet " in vpn.stdout
                    for line in battery.stdout.splitlines():
                        if line.strip().startswith("temperature:"):
                            item["temp"] = int(line.split(":", 1)[1].strip()) / 10
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    pass
                devices.append(item)
            self.ui_events.put(("devices", (devices, len(serials))))
        except Exception as exc:
            self.ui_events.put(("scan_error", str(exc)))

    def apply_device_scan(self, devices, total):
        self.device_scan_running = False
        self.lbl_kpi_nodes.configure(text=f"{total} / 25 Online")
        for index, widgets in self.row_widgets.items():
            if index <= len(devices):
                item = devices[index-1]
                widgets["serial_val"] = item["serial"]
                widgets["ser"].configure(text=item["serial"], text_color="#f1f5f9")
                temperature = f'{item["temp"]:.0f}°C' if item["temp"] is not None else "Isı: ?"
                widgets["st"].configure(text=f'● ONLINE | VPN:{"OK" if item["vpn"] else "YOK"} | {temperature}', text_color="#5eead4" if item["vpn"] else "#fbbf24")
            else:
                widgets["serial_val"] = None
                widgets["ser"].configure(text="Bağlı değil", text_color="#64748b")
                widgets["st"].configure(text="○ OFFLINE", text_color="#8193ae")
        self.last_scan_text = time.strftime("%H:%M:%S")
        self.lbl_last_scan.configure(text=f"Son tarama: {self.last_scan_text}")
        self.refresh_comment_phones()
        self.refresh_watcher_phones()
        self.refresh_operation_phones()
        self.log(f"[TARAMA] {total} telefon bağlı. Durum okundu; telefon ayarları değiştirilmedi.")

    def process_ui_events(self):
        for _ in range(100):
            try:
                event, value = self.ui_events.get_nowait()
            except queue.Empty:
                break
            if event == "log":
                self.log(value)
            elif event == "devices":
                self.apply_device_scan(*value)
            elif event == "scan_error":
                self.device_scan_running = False
                self.log(f"[TARAMA HATASI] {value}")
            elif event == "refresh_after_task":
                self.refresh_queue_table()
                self.refresh_share_history()

    def refresh_workspace_status(self):
        run = watcher_store.get_run()
        if run and run["status"] in {"STARTING", "RUNNING", "WAITING"}:
            text, color, background = "● Nöbetçi açık", "#fbbf24", "#3c3019"
        elif self.active_proc and self.active_proc.poll() is None:
            text, color, background = "● Görev çalışıyor", "#93c5fd", "#1b3457"
        elif self.device_scan_running:
            text, color, background = "● Taranıyor", "#93c5fd", "#1b3457"
        else:
            text, color, background = "● Hazır", "#5eead4", "#123431"
        self.lbl_live_state.configure(text=text, text_color=color, fg_color=background)
        self.lbl_side_state.configure(text=text.upper(), text_color=color)

    def lock_all_portrait(self):
        def _bg():
            for _, _, ser, _, _ in self.get_selected_online_nodes():
                lock_portrait_mode(ser)
            self.log("[📱 DİKEY KİLİT] Tüm cihazlar dikey (Portrait) ekran moduna kilitlendi.")
        threading.Thread(target=_bg, daemon=True).start()

    def sleep_single_device(self, idx):
        ser = self.row_widgets[idx]["serial_val"]
        if not ser:
            return
        def _bg():
            home_and_sleep(ser)
            self.log(f"[📴 CİHAZ KAPATILDI] NODE-{idx:02d} arka plan FB/TikTok kapatıldı ve telefon ekranı uyutuldu.")
        threading.Thread(target=_bg, daemon=True).start()

    def screen_metadata(self):
        return {w["serial_val"]: (i, w["name"].get().strip())
                for i, w in self.row_widgets.items() if w["serial_val"]}

    def _open_screen_target(self, serial, index, name, rectangle):
        previous = self.scrcpy_procs.get(serial)
        if previous and previous.poll() is None:
            self.log(f"[EKRAN] {serial} izleme penceresi zaten açık.")
            return False
        # Wake without Home: opening a mirror must not leave the user's current app.
        fleet_controls.adb("-s", serial, "shell", "input", "keyevent", "224")
        x, y, width, height = rectangle
        title = f"NODE-{index:02d} | {name} ({serial})" if index else f"Telefon | {serial}"
        command = ["scrcpy", "-s", serial, "--no-audio", "--window-title", title,
                   "--window-x", str(x), "--window-y", str(y), "--window-width", str(width),
                   "--window-height", str(height), "--max-size", "640", "--max-fps", "15", "-b", "1M"]
        logs = os.path.join(os.path.dirname(__file__), "..", "logs")
        os.makedirs(logs, exist_ok=True)
        safe_serial = "".join(c if c.isalnum() else "_" for c in serial)
        log_path = os.path.join(logs, f"scrcpy_{safe_serial}.log")
        with open(log_path, "w", encoding="utf-8") as output:
            proc = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.scrcpy_procs[serial] = proc
        time.sleep(0.4)
        if proc.poll() is not None:
            self.scrcpy_procs.pop(serial, None)
            raise RuntimeError(f"scrcpy açılamadı ({serial}); ayrıntı: {log_path}")
        self.log(f"[EKRAN AÇILDI] {title}")
        return True

    def _open_screen_batch(self, serials, metadata, screen_size):
        try:
            rectangles = fleet_controls.mirror_layout(len(serials), *screen_size)
            opened = 0
            for serial, rectangle in zip(serials, rectangles):
                if self.fleet_sleep_busy:
                    self.log("[EKRAN] Telefon kapatma isteği nedeniyle kalan pencereler açılmadı.")
                    break
                index, name = metadata.get(serial, (None, ""))
                try:
                    opened += self._open_screen_target(serial, index, name, rectangle)
                except Exception as exc:
                    self.log(f"[EKRAN HATASI] {serial}: {exc}")
            self.log(f"[EKRAN] {len(serials)} telefon kontrol edildi; {opened} yeni izleme penceresi açıldı.")
        finally:
            self.fleet_view_busy = False

    def open_all_online_screens(self):
        if self.fleet_view_busy or self.fleet_sleep_busy:
            self.log("[!] Toplu ekran işlemi zaten sürüyor.")
            return
        metadata = self.screen_metadata()
        screen_size = (self.winfo_screenwidth(), self.winfo_screenheight())
        self.fleet_view_busy = True
        def worker():
            try:
                serials = fleet_controls.online_devices()
                if not serials:
                    self.log("[!] ADB üzerinde ONLINE telefon bulunamadı.")
                    return
                self.log(f"[EKRAN] {len(serials)} ONLINE telefonun ekranı açılıyor; kutucuk seçimi gerekmez.")
                self._open_screen_batch(serials, metadata, screen_size)
            except Exception as exc:
                self.log(f"[EKRAN HATASI] {exc}")
            finally:
                self.fleet_view_busy = False
        threading.Thread(target=worker, daemon=True).start()

    def open_single_screen(self, idx):
        widgets = self.row_widgets[idx]
        serial = widgets["serial_val"]
        if not serial:
            self.log(f"[!] NODE-{idx:02d} USB'de bağlı değil!")
            return
        if self.fleet_sleep_busy or self.fleet_view_busy:
            self.log("[!] Toplu ekran işleminin bitmesini bekleyin.")
            return
        self.fleet_view_busy = True
        metadata = {serial: (idx, widgets["name"].get().strip())}
        size = (self.winfo_screenwidth(), self.winfo_screenheight())
        threading.Thread(target=self._open_screen_batch, args=([serial], metadata, size), daemon=True).start()

    def close_single_screen(self, idx):
        serial = self.row_widgets[idx]["serial_val"]
        proc = self.scrcpy_procs.get(serial)
        if proc:
            try:
                fleet_controls.stop_process_tree(proc)
                self.scrcpy_procs.pop(serial, None)
            except Exception as exc:
                self.log(f"[EKRAN KAPATMA HATASI] {exc}")

    def open_selected_screens(self):
        if self.fleet_view_busy or self.fleet_sleep_busy:
            self.log("[!] Toplu ekran işlemi zaten sürüyor.")
            return
        selected = self.get_selected_online_nodes()
        if not selected:
            self.log("[!] Ekranı açılacak seçili ONLINE telefon yok.")
            return
        self.fleet_view_busy = True
        metadata = {s: (i, name) for i, _, s, name, _ in selected}
        size = (self.winfo_screenwidth(), self.winfo_screenheight())
        threading.Thread(target=self._open_screen_batch, args=([x[2] for x in selected], metadata, size), daemon=True).start()

    def close_all_screens(self):
        if os.name == "nt":
            subprocess.run("taskkill /F /IM scrcpy.exe /T", shell=True, capture_output=True)
        else:
            subprocess.run("pkill -f scrcpy", shell=True, capture_output=True)
        self.scrcpy_procs.clear()
        self.log("[*] PC'deki tüm izleme pencereleri kapatıldı.")

    def mute_all_connected(self):
        def _bg():
            for _, _, ser, _, _ in self.get_selected_online_nodes():
                mute_device_audio(ser)
            self.log("[🔇 SES KAPATILDI] Tüm aktif cihazların sesleri sıfırlandı.")
        threading.Thread(target=_bg, daemon=True).start()

    def sleep_every_online_device(self):
        if self.fleet_sleep_busy:
            self.log("[!] Tüm telefonları kapatma işlemi zaten sürüyor.")
            return
        self.fleet_sleep_busy = True
        run = watcher_store.get_run()
        if run and run["status"] in {"STARTING", "RUNNING", "WAITING"}:
            watcher_store.request_stop(run["id"])
        def worker():
            try:
                self.stop_active_proc()
                if self.active_proc and self.active_proc.poll() is None:
                    raise RuntimeError("Çalışan görev durdurulamadı; telefonların yeniden uyanmaması için kapatma iptal edildi.")
                if self.watcher_proc and self.watcher_proc.poll() is None:
                    fleet_controls.stop_process_tree(self.watcher_proc)
                    if run:
                        watcher_store.update_run(run["id"], "STOPPED", "Tüm telefonları kapatma isteğiyle durduruldu.")
                elif run and run["status"] in {"STARTING", "RUNNING", "WAITING"}:
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        state = watcher_store.get_run(run["id"])
                        if not state or state["status"] in {"STOPPED", "ERROR"} or not watcher_store.process_alive(state["process_id"]):
                            break
                        time.sleep(0.5)
                    else:
                        raise RuntimeError("Nöbetçi hâlâ durduruluyor. Durduktan sonra kapatma düğmesine tekrar basın.")
                if run and run["status"] in {"STARTING", "RUNNING", "WAITING"}:
                    watcher_store.update_run(run["id"], "STOPPED", "Tüm telefonları kapatma isteğiyle durduruldu.")
                # Let a screen-open batch finish its in-flight wake before sending Sleep.
                deadline = time.monotonic() + 12
                while self.fleet_view_busy and time.monotonic() < deadline:
                    time.sleep(0.1)
                if self.fleet_view_busy:
                    raise RuntimeError("Ekran açma işlemi henüz bitmedi; kapatma işlemini tekrar deneyin.")
                serials = fleet_controls.online_devices()
                if not serials:
                    self.log("[!] Kapatılacak ONLINE telefon bulunamadı.")
                    return
                verified, failed = 0, 0
                for serial in serials:
                    result = fleet_controls.sleep_device(serial)
                    verified += bool(result["asleep"])
                    failed += bool(result["errors"])
                    message = "Ekran uykusu doğrulandı" if result["asleep"] else "Uyku komutu gönderildi; ekran durumu doğrulanamadı"
                    self.log(f"[CİHAZ KAPATMA] {serial}: {message}." + (" Hatalar: " + "; ".join(result["errors"]) if result["errors"] else ""))
                self.log(f"[TOPLU KAPATMA] {len(serials)} ONLINE telefona FB/TikTok kapatma ve uyku komutları gönderildi. Uyku doğrulanan: {verified}; komut hatası olan: {failed}.")
            except Exception as exc:
                self.log(f"[TOPLU KAPATMA HATASI] {exc}")
            finally:
                self.fleet_sleep_busy = False
        threading.Thread(target=worker, daemon=True).start()

    def sleep_all_connected(self):
        def _bg():
            for _, _, ser, _, _ in self.get_selected_online_nodes():
                home_and_sleep(ser)
            self.log("[📴 CİHAZ EKRANLARI KAPATILDI] Tüm telefonlarda Facebook & TikTok kapatıldı, ana sayfaya dönülüp ekranlar uyutuldu.")
        threading.Thread(target=_bg, daemon=True).start()

    def stop_and_sleep_all(self):
        self.stop_active_proc()
        self.sleep_all_connected()

    def _stream_cmd(self, cmd):
        with self.process_lock:
            if self.fleet_sleep_busy or getattr(self, "task_cleanup_busy", False) or getattr(self, "watcher_cleanup_busy", False):
                self.watcher_log_queue.put("[!] Önceki görev veya telefon kapatma işlemi sürüyor; yeni görev başlatılmadı.")
                return
            watcher_run = watcher_store.get_run()
            if watcher_run and watcher_run["status"] in {"STARTING", "RUNNING", "WAITING"}:
                self.watcher_log_queue.put("[!] Nöbetçi izliyor. Yeni cihaz görevinden önce Nöbetçiyi Durdur düğmesini kullanın.")
                return
            serials = task_serials(cmd, DB_FILE)
            self.stop_active_proc()
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self.active_proc = proc
            self.task_cleanup_busy = True
        try:
            os.makedirs("logs", exist_ok=True)
            with open(os.path.join("logs", f"task_{proc.pid}.log"), "a", encoding="utf-8") as task_log:
                for line in proc.stdout:
                    task_log.write(line)
                    task_log.flush()
                    self.log(line.strip())
            proc.wait()
        finally:
            try:
                if proc.poll() is None:
                    fleet_controls.stop_process_tree(proc)
                close_devices(serials, self.log)
                interrupt_process(proc.pid)
            finally:
                self.task_cleanup_busy = False
                self.ui_events.put(("refresh_after_task", None))

    def save_warmup_preferences(self):
        try:
            rate = int(self.ent_warm_like.get())
            if not 0 <= rate <= 100:
                raise ValueError()
            drafts = list(dict.fromkeys(x.strip() for x in self.txt_warm_drafts.get("1.0", "end").splitlines() if x.strip()))
            save_json("config/warmup_preferences.json", {"like_percent": rate, "drafts": drafts})
            return True
        except ValueError:
            self.log("[!] Günlük ısınma beğeni oranı 0–100 arasında olmalı.")
            return False

    def pick_warmup_draft(self):
        if not self.save_warmup_preferences():
            return
        choices = load_json("config/warmup_preferences.json", {}).get("drafts", [])
        if choices:
            text = random.choice(choices)
            self.ent_warm_draft.delete(0, "end")
            self.ent_warm_draft.insert(0, text)
            self.clipboard_clear()
            self.clipboard_append(text)
            self.log("[TASLAK] Yorum panoya kopyalandı; otomatik gönderilmedi.")

    def start_selected_warmup(self):
        if not self.save_warmup_preferences():
            return
        selected = self.operation_nodes("warmup")
        if not selected:
            self.log("[!] Isıtma için seçili ONLINE cihaz yok!")
            return
        mins = self.ent_warm_min.get().strip() or "30"
        lprob = self.ent_warm_like.get().strip() or "15"
        ser_list = ",".join([x[2] for x in selected])
        self.warmup_active_serials = [x[2] for x in selected]
        self.log(f"[HESAP ISITMA] {len(selected)} cihaz {mins} dk dikey modda Facebook ısıtmaya alındı...")
        threading.Thread(target=self._stream_cmd, args=([sys.executable, "core_engine.py", "warmup", mins, lprob, ser_list],), daemon=True).start()

    def stop_selected_warmup(self):
        serials = list(getattr(self, "warmup_active_serials", [])) or [x[2] for x in self.operation_nodes("warmup")]
        self.stop_active_proc()
        def sleep_targets():
            for serial in serials:
                home_and_sleep(serial)
            self.log(f"[ISITMA DURDU] {len(serials)} ısıtma telefonuna kapatma ve uyku komutu gönderildi.")
        threading.Thread(target=sleep_targets, daemon=True).start()

    def start_single_warmup(self, idx):
        if not self.save_warmup_preferences():
            return
        ser = self.row_widgets[idx]["serial_val"]
        if not ser: return
        mins = self.ent_warm_min.get().strip() or "30"
        lprob = self.ent_warm_like.get().strip() or "15"
        self.warmup_active_serials = [ser]
        self.log(f"[TEKİL ISITMA] NODE-{idx:02d} ({ser}) {mins} dk ısıtmaya alındı...")
        threading.Thread(target=self._stream_cmd, args=([sys.executable, "core_engine.py", "warmup", mins, lprob, ser],), daemon=True).start()

    def refresh_engagement_preview(self):
        try:
            _, counts = engagement_plan(self.get_comment_phone_nodes(), self.ent_campaign_like.get(), self.ent_campaign_comment.get())
            self.lbl_engagement_preview.configure(text=f"Plan: {counts[0]} beğeni · {counts[1]} yorum (en yakın tam sayı)")
        except ValueError as exc:
            self.lbl_engagement_preview.configure(text=str(exc))

    def queue_custom_task(self, task_mode, url, comment_label, selected=None, campaign_code=None, timing_scope="campaign"):
        self.save_all_profiles()
        selected = list(self.get_selected_online_nodes() if selected is None else selected)
        if not selected:
            self.log("[!] Bu işlem için Telefonları Seç düğmesinden en az bir ONLINE telefon seçin.")
            return None
        try:
            options = self.task_timing(timing_scope)
            wmin, wmax = options["delay_min"], options["delay_max"]
            if not 0 <= wmin <= wmax:
                raise ValueError()
        except ValueError as exc:
            self.log(f"[!] {exc}")
            return None
        if not url or "facebook.com" not in url or "..." in url:
            self.log("[!] Geçerli bir Facebook hedef bağlantısı girin.")
            return None
        if self.var_rand_order.get():
            random.shuffle(selected)
        camp_code = campaign_code or f"CMP-{uuid.uuid4().hex}"
        timing.store_campaign(DB_FILE, camp_code, options)
        with closing(sqlite3.connect(DB_FILE)) as db, db:
            for idx, node_id, ser, fb_name, persona in selected:
                db.execute("""INSERT INTO campaign_queue
                    (camp_code, node_id, serial, fb_name, persona, task_type, target_url, comment_text, delay_sec, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (camp_code, node_id, ser, fb_name, persona, task_mode, url, comment_label,
                     random.randint(wmin, wmax), f"[PENDING] {comment_label}"))
        self.refresh_queue_table()
        return camp_code

    def queue_and_run(self, task_mode):
        if task_mode == "YORUM+BEGENI":
            selected = self.get_comment_phone_nodes()
            if not selected:
                self.log("[!] Beğeni / yorum için bu bölümden en az bir ONLINE telefon seçin.")
                return
            url = self.ent_post_url.get().strip()
            if not url or "facebook.com" not in url or "..." in url:
                self.log("[!] Geçerli bir Facebook gönderi bağlantısı girin.")
                return
            if self.var_rand_order.get():
                random.shuffle(selected)
            try:
                plan, counts = engagement_plan(selected, self.ent_campaign_like.get(), self.ent_campaign_comment.get())
                options = self.task_timing("campaign")
                wmin, wmax = options["delay_min"], options["delay_max"]
                if not 0 <= wmin <= wmax:
                    raise ValueError("Dalga aralığı: 0 ≤ minimum ≤ maksimum olmalı.")
            except ValueError as exc:
                self.log(f"[!] {exc}")
                return
            if not plan:
                self.log("[!] Oranlara göre işlem yok (0 beğeni, 0 yorum). Oranı veya telefon sayısını artırın.")
                return
            self.save_all_profiles()
            save_json("config/panel_preferences.json", {"like_percent": self.ent_campaign_like.get(), "comment_percent": self.ent_campaign_comment.get()})
            base_title = self.ent_comm_title.get().strip() or "Harika paylaşım"
            camp_code = f"CMP-{uuid.uuid4().hex}"
            timing.store_campaign(DB_FILE, camp_code, options)
            with closing(sqlite3.connect(DB_FILE)) as db, db:
                for (idx, node_id, ser, fb_name, persona), mode in plan:
                    if "YORUM" in mode:
                        label = f"{base_title} #{self.comment_counter}"
                        self.comment_counter += 1
                    else:
                        label = "Yalnız Beğeni"
                    db.execute("""INSERT INTO campaign_queue
                        (camp_code, node_id, serial, fb_name, persona, task_type, target_url, comment_text, delay_sec, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (camp_code, node_id, ser, fb_name, persona, mode, url, label,
                         random.randint(wmin, wmax), f"[PENDING] {label}"))
            self.log(f"[KAMPANYA PLANI] {len(selected)} seçili telefon: {counts[0]} beğeni, {counts[1]} yorum.")
            self.refresh_queue_table()
            self.run_queue_worker(camp_code)
            return
        if task_mode == "GRUP_KATIL":
            code = self.queue_custom_task("GRUP_KATIL", self.ent_grp_url.get().strip(), "Gruba Katıl", self.operation_nodes("campaign_join"))
        else:
            code = self.queue_custom_task("KISI_EKLE", self.ent_frd_url.get().strip(), "Arkadaş Ekle", self.operation_nodes("friend"))
        if code:
            self.run_queue_worker(code)

    def run_queue_worker(self, campaign_code=None):
        sw_flag = "1" if self.var_sandwich.get() else "0"
        command = [sys.executable, "core_engine.py", "run_queue", sw_flag]
        if campaign_code:
            command.append(campaign_code)
        threading.Thread(target=self._stream_cmd, args=(command,), daemon=True).start()

    @staticmethod
    def merge_watcher_keywords(*values):
        result, seen = [], set()
        for value in values:
            parts = value.split(",") if isinstance(value, str) else value
            for part in parts:
                word = str(part).strip()
                key = word.casefold()
                if word and key not in seen:
                    seen.add(key)
                    result.append(word)
        return result

    def refresh_saved_watcher_keywords(self):
        saved = load_json("config/saved_watcher_keywords.json", [])
        self.saved_watcher_keywords = self.merge_watcher_keywords(saved, self.ent_keywords.get())
        self.lst_saved_keywords.delete(0, "end")
        for word in self.saved_watcher_keywords:
            self.lst_saved_keywords.insert("end", word)

    def save_watcher_keywords(self):
        saved = load_json("config/saved_watcher_keywords.json", [])
        words = self.merge_watcher_keywords(saved, self.ent_keywords.get())
        save_json("config/saved_watcher_keywords.json", words)
        cfg = self.load_watch_cfg()
        cfg["keywords"] = self.ent_keywords.get().strip()
        save_json("config/watched_posts.json", cfg)
        self.refresh_saved_watcher_keywords()

    def add_saved_watcher_keywords(self):
        selected = [self.lst_saved_keywords.get(i) for i in self.lst_saved_keywords.curselection()]
        if not selected:
            return
        words = self.merge_watcher_keywords(self.ent_keywords.get(), selected)
        self.ent_keywords.delete(0, "end")
        self.ent_keywords.insert(0, ", ".join(words))
        self.save_watcher_keywords()

    def load_watch_cfg(self):
        return load_json("config/watched_posts.json", {"posts": [], "keywords": "fiyat, link, bilgi", "reply_template": "Detayli bilgi icin DM kontrol edin", "cycle_minutes": 16, "max_replies_per_visit": 3})

    def refresh_watched_list_ui(self):
        cfg = self.load_watch_cfg()
        posts = cfg.get("posts", [])
        self.lbl_watch_count.configure(text=f"İzlenen Gönderi Listesi ({len(posts)} Adet):")
        self.txt_watched_list.delete("1.0", "end")
        for idx, p in enumerate(posts, 1):
            self.txt_watched_list.insert("end", f"{idx:02d}. {p}\n")

    def add_watched_post(self):
        url = self.ent_watch_url.get().strip()
        from keyword_watcher import valid_target
        if not valid_target(url):
            self.log("[!] Geçerli bir Facebook grup veya gönderi linki girin!")
            return
        cfg = self.load_watch_cfg()
        if url not in cfg["posts"]:
            cfg["posts"].append(url)
        save_json("config/watched_posts.json", cfg)
        self.refresh_watched_list_ui()
        self.log(f"[EKLENDİ] Gönderi izleme listesine eklendi (Toplam: {len(cfg['posts'])}).")

    def clear_watched_posts(self):
        cfg = self.load_watch_cfg()
        cfg["posts"] = []
        save_json("config/watched_posts.json", cfg)
        self.refresh_watched_list_ui()
        self.log("[TEMİZLENDİ] İzlenen gönderi listesi sıfırlandı.")

    def refresh_watcher_engine_status(self):
        available = os.path.isfile(self.watcher_engine_path)
        self.lbl_watcher_engine.configure(
            text=(("Sıralı dağıtım: seçili ONLINE telefonlar dengeli kullanılır; yanıtı olan yorumlar atlanır." if self.var_watcher_sequential.get() else "Tek telefonlu eski mod: en fazla 3 deneme/tur.") if self.var_watcher_auto.get() else "İzleme modu: metin eşleşmeleri kaydedilir; yanıt gönderilmez.") if available else "Nöbetçi motoru eksik: keyword_watcher.py bulunamadı. Telefon seçebilirsiniz; motor başlatılamaz.",
            text_color="#4ade80" if available else "#facc15")
        return available

    def start_keyword_watcher(self):
        if getattr(self, "watcher_cleanup_busy", False) or getattr(self, "task_cleanup_busy", False):
            self.log("[!] Önceki görev ve telefon kapatma işlemi tamamlanınca yeniden başlatın.")
            return
        if self.fleet_sleep_busy:
            self.log("[!] Telefonları kapatma işleminin bitmesini bekleyin.")
            return
        current = watcher_store.get_run()
        if current and current["status"] in {"STARTING", "RUNNING", "WAITING"}:
            self.log("[!] Bir nöbetçi oturumu zaten açık. Takip ekranından kontrol edin veya durdurun.")
            self.open_watcher_monitor()
            return
        selected = self.get_watcher_phone_nodes()
        if not selected:
            self.log("[!] Nöbetçi için bu bölümdeki listeden en az bir ONLINE telefon seçin.")
            return
        if not self.refresh_watcher_engine_status():
            self.log("[!] Nöbetçi motoru dosyası eksik.")
            return
        if self.active_proc and self.active_proc.poll() is None:
            self.log("[!] Telefonlarda başka bir görev çalışıyor. Önce o görevin bitmesini bekleyin veya durdurun.")
            return
        from keyword_watcher import validate_settings, valid_target
        cfg = self.load_watch_cfg()
        cur_url = self.ent_watch_url.get().strip()
        if valid_target(cur_url) and cur_url not in cfg["posts"]:
            cfg["posts"].append(cur_url)
        pool_metadata = dict(cfg.get("device_metadata", {}))
        pool_metadata.update({x[2]: {"node_id": x[1], "fb_name": x[3]} for x in selected})
        selected_pool = [x[2] for x in selected]
        if self.var_watcher_sequential.get():
            selected_pool = list(dict.fromkeys([s for s in cfg.get("selected_serials", []) if s in self.watcher_phone_serials and s in pool_metadata] + selected_pool))
        try:
            cfg.update(sequential_enabled=self.var_watcher_sequential.get(), reply_delay_seconds=int(self.ent_reply_gap.get()), timing=self.task_timing("watcher"), auto_reply_enabled=self.var_watcher_auto.get(), owned_targets_confirmed=self.var_watcher_owned.get(),
                       keywords=self.ent_keywords.get().strip(), reply_template=self.ent_kw_reply.get().strip(),
                       cycle_minutes=int(self.ent_cycle_min.get().strip()),
                       max_replies_per_visit=int(self.ent_max_rep.get().strip()),
                       selected_serials=selected_pool,
                       device_metadata={serial: pool_metadata[serial] for serial in selected_pool})
            cfg = validate_settings(cfg)
        except (ValueError, TypeError) as exc:
            self.log(f"[!] Nöbetçi ayarları: {exc}")
            return
        self.save_watcher_keywords()
        watcher_store.save_settings(cfg)
        self.refresh_watched_list_ui()
        run_id = watcher_store.create_run(cfg)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        try:
            proc = subprocess.Popen([sys.executable, self.watcher_engine_path, ",".join(cfg["selected_serials"]), run_id],
                cwd=os.path.dirname(self.watcher_engine_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, env=env)
        except OSError as exc:
            watcher_store.update_run(run_id, "ERROR", str(exc))
            self.log(f"[!] Nöbetçi başlatılamadı: {exc}")
            return
        self.watcher_proc, self.watcher_run_id = proc, run_id
        self.watcher_cleanup_busy = True
        watcher_store.set_process(run_id, proc.pid)
        def stream():
            try:
                for line in proc.stdout:
                    self.watcher_log_queue.put(line.strip())
                proc.wait()
            finally:
                try:
                    if proc.poll() is None:
                        fleet_controls.stop_process_tree(proc)
                    close_devices(cfg["selected_serials"], self.watcher_log_queue.put)
                finally:
                    self.watcher_cleanup_busy = False
                    self.watcher_log_queue.put(f"[NÖBETÇİ] İşçi kapandı (çıkış kodu {proc.returncode}).")
        threading.Thread(target=stream, daemon=True).start()
        self.open_watcher_monitor()

    def stop_keyword_watcher(self):
        run = watcher_store.get_run()
        if not run or run["status"] not in {"STARTING", "RUNNING", "WAITING"}:
            self.log("[NÖBETÇİ] Durdurulacak aktif izleme yok.")
            return
        watcher_store.request_stop(run["id"])
        self.log("[NÖBETÇİ] Durdurma istendi. Mevcut okuma tamamlanıyor.")
        proc = self.watcher_proc
        if proc and proc.pid == run["process_id"]:
            self.after(12000, lambda: self.force_stop_watcher(proc, run["id"]))

    def force_stop_watcher(self, proc, run_id):
        if proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=5)
            else:
                proc.terminate()
            watcher_store.update_run(run_id, "STOPPED", "Okuma beklemesi nedeniyle işçi sonlandırıldı. Son kontrol tamamlanmamış olabilir.")
            self.log("[NÖBETÇİ] İşçi durduruldu; son kontrol yarıda kesildi.")

    def open_watcher_monitor(self):
        if self.watcher_window and self.watcher_window.winfo_exists():
            self.watcher_window.lift()
            self.refresh_watcher_monitor()
            return
        window = ctk.CTkToplevel(self)
        self.watcher_window = window
        window.title("Nöbetçi Takip Ekranı — İzleme ve Yanıtlar")
        window.geometry("1180x680")
        window.minsize(800, 450)
        window.transient(self)
        header = ctk.CTkFrame(window)
        header.pack(fill="x", padx=12, pady=10)
        self.lbl_monitor_status = ctk.CTkLabel(header, text="", anchor="w", wraplength=780)
        self.lbl_monitor_status.pack(side="left", fill="x", expand=True, padx=10)
        ctk.CTkButton(header, text="Nöbetçiyi Durdur", command=self.stop_keyword_watcher, width=150, fg_color="#be123c").pack(side="right", padx=8)
        ctk.CTkLabel(window, text="İzleme veya tek hesaplı otomatik yanıt modu çalışır. Gönderim denemesi yayın teyidi değildir; sonuçları Facebook'tan kontrol edin.", text_color="#facc15", wraplength=1050).pack(fill="x", padx=16, pady=(0, 8))
        self.monitor_tabs = ttk.Notebook(window)
        self.monitor_tabs.pack(fill="both", expand=True, padx=12, pady=6)
        self.monitor_tables = {}
        specs = [
            ("scans", "Kontrol Geçmişi", ("time", "phone", "account", "target", "status", "matches"),
             ("Zaman", "Telefon / Seri", "Kayıtlı Hesap", "Hedef", "Sonuç", "Yeni Eşleşme")),
            ("findings", "Anahtar Kelime Eşleşmeleri", ("time", "phone", "target", "keyword", "text", "review"),
             ("İlk Görülme", "Telefon / Seri", "Hedef", "Anahtar Kelime", "Ekrandaki Metin", "İnceleme"))]
        for key, title, columns, headings in specs:
            frame = ttk.Frame(self.monitor_tabs)
            self.monitor_tabs.add(frame, text=title)
            tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
            for col, heading in zip(columns, headings):
                tree.heading(col, text=heading)
                tree.column(col, width=175 if col != "text" else 350, minwidth=80)
            tree.grid(row=0, column=0, sticky="nsew")
            sy = ttk.Scrollbar(frame, command=tree.yview)
            sy.grid(row=0, column=1, sticky="ns")
            sx = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            sx.grid(row=1, column=0, sticky="ew")
            tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_columnconfigure(0, weight=1)
            tree.bind("<Double-1>", lambda event, kind=key: self.show_watcher_detail(kind))
            self.monitor_tables[key] = tree
        buttons = ctk.CTkFrame(window, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(buttons, text="Seçili Kaydın Ayrıntıları", command=self.show_watcher_detail).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text="Daha Eski Kayıtlar", command=self.more_watcher_history).pack(side="left", padx=4)
        ctk.CTkButton(buttons, text="Otomatik Yanıt Kayıtları", command=self.open_auto_reply_history).pack(side="left", padx=4)
        self.lbl_monitor_count = ctk.CTkLabel(buttons, text="")
        self.lbl_monitor_count.pack(side="right", padx=8)
        self.monitor_limit = 200
        self.monitor_rows = {"scans": {}, "findings": {}}
        self.monitor_signature = None
        self.refresh_watcher_monitor()

    def more_watcher_history(self):
        self.monitor_limit += 200
        self.monitor_signature = None
        self.refresh_watcher_monitor()

    def refresh_watcher_monitor(self):
        run = watcher_store.get_run()
        labels = {"STARTING": "Başlatılıyor", "RUNNING": "Kontrol ediliyor", "WAITING": "Sonraki tur bekleniyor", "STOPPED": "Durduruldu", "ERROR": "Hata"}
        status = labels.get(run["status"], run["status"]) if run else "Henüz başlatılmadı"
        if run and run["stop_requested"] and run["status"] in {"STARTING", "RUNNING", "WAITING"}:
            status = "Durduruluyor"
        next_check = f' | Sonraki: {run["next_check"][11:19]}' if run and run["next_check"] else ""
        self.lbl_watch_live.configure(text=status + next_check)
        if not self.watcher_window or not self.watcher_window.winfo_exists():
            return
        self.lbl_monitor_status.configure(text=f'{status}{next_check}\n{run["message"] if run else "Kontroller ve eşleşmeler burada görünecek."}')
        scans, findings = watcher_store.list_scans(self.monitor_limit), watcher_store.list_findings(self.monitor_limit)
        signature = ([(r["id"], r["status"], r["new_matches"]) for r in scans],
                     [(r["id"], r["last_seen"], r["review_state"], r["is_replied"], r["reply_at"], r["similar_replies"]) for r in findings])
        if signature == self.monitor_signature:
            return
        self.monitor_signature = signature
        self.monitor_rows = {"scans": {str(r["id"]): r for r in scans}, "findings": {str(r["id"]): r for r in findings}}
        scan_labels = {"SCANNING": "Okunuyor", "DONE": "Görünür metin tarandı", "UNREADABLE": "Metin okunamadı", "ERROR": "Hata", "SKIPPED": "Kontrol atlandı (ayrıntıya bakın)", "INTERRUPTED": "Yarıda kesildi", "AUTO_ATTEMPTED": "Otomatik yanıt akışı denendi", "CONTEXT_MISSING": "Yorum yapısı doğrulanamadı"}
        for key, rows in (("scans", scans), ("findings", findings)):
            tree = self.monitor_tables[key]
            selected = tree.selection()
            tree.delete(*tree.get_children())
            for row in rows:
                if key == "scans":
                    values = (row["started_at"][:19].replace("T", " "), f'{row["node_id"]} / {row["serial"]}', row["account"], row["target_url"], scan_labels.get(row["status"], row["status"]), row["new_matches"])
                else:
                    review = "Yanıtlandı (elle doğrulandı)" if row["is_replied"] else "İncelendi" if row["review_state"] == "REVIEWED" else "Yeni / inceleme bekliyor"
                    if not row["comment_key"] and row["similar_replies"]:
                        review = "Benzer yanıtlama var; yorum kimliği belirsiz"
                    values = (row["first_seen"][:19].replace("T", " "), f'{row["node_id"]} / {row["serial"]}', row["target_url"], row["keyword"], row["screen_text"], review)
                tree.insert("", "end", iid=str(row["id"]), values=values)
            if selected and tree.exists(selected[0]):
                tree.selection_set(selected[0])
        attempts = watcher_store.list_auto_replies(self.monitor_limit)
        self.lbl_monitor_count.configure(text=f"{len(scans)} kontrol | {len(findings)} eşleşme | {len(attempts)} yanıt kaydı")

    def open_auto_reply_history(self):
        window = ctk.CTkToplevel(self)
        window.title("Otomatik Yanıt Kayıtları")
        window.geometry("1100x650")
        ctk.CTkLabel(window, text="Send tıklanması yayın teyidi değildir. Belirsiz veya başarısız denemeler otomatik tekrarlanmaz.", text_color="#facc15", wraplength=1000).pack(padx=12, pady=10)
        columns = ("time", "phone", "author", "comment", "state")
        tree = ttk.Treeview(window, columns=columns, show="headings", height=9)
        for key, title, width in zip(columns, ("Kayıt Zamanı", "Telefon / Seri", "Yorum Yazarı", "Yorum", "Durum"), (160, 180, 160, 300, 230)):
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=80)
        tree.pack(fill="both", expand=True, padx=12)
        details = ctk.CTkTextbox(window, height=200, wrap="word")
        details.pack(fill="both", expand=True, padx=12, pady=10)
        snapshot = {}
        def selected(event=None):
            choices = tree.selection()
            if not choices or choices[0] not in snapshot:
                return
            row = snapshot[choices[0]]
            details.configure(state="normal")
            details.delete("1.0", "end")
            for label, key in [("Hedef", "target_url"), ("Telefon", "serial"), ("Kayıtlı Hesap", "account"), ("Yorum Yazarı", "author"), ("Yorum", "screen_text"), ("Yanıt Metni", "reply_text"), ("Durum", "status"), ("Açıklama", "message")]:
                details.insert("end", f"{label}: {row[key]}\n\n")
            details.configure(state="disabled")
        tree.bind("<<TreeviewSelect>>", selected)
        labels = {"RESERVED": "Hazırlanıyor", "SENDING": "Send tetikleniyor", "SEND_UNVERIFIED": "Gönderim denendi; yayın teyitsiz", "RECHECK_VISIBLE": "Yeniden açılışta görüldü", "NOT_SENT": "Gönderilmedi", "UNKNOWN": "Sonuç belirsiz; tekrar yok"}
        def refresh():
            if not window.winfo_exists():
                return
            rows = watcher_store.list_auto_replies(200)
            for row in rows:
                iid = str(row["id"])
                snapshot[iid] = row
                values = (row["created_at"][:19].replace("T", " "), f'{row["node_id"]} / {row["serial"]}', row["author"], row["screen_text"], labels.get(row["status"], row["status"]))
                if tree.exists(iid):
                    tree.item(iid, values=values)
                else:
                    tree.insert("", "end", iid=iid, values=values)
            selected()
            window.after(1500, refresh)
        refresh()

    def show_watcher_detail(self, kind=None):
        if kind is None:
            kind = "scans" if self.monitor_tabs.index(self.monitor_tabs.select()) == 0 else "findings"
        selection = self.monitor_tables[kind].selection()
        if not selection:
            return
        row = self.monitor_rows[kind].get(selection[0])
        if not row:
            return
        window = ctk.CTkToplevel(self.watcher_window)
        window.title("Kontrol Ayrıntıları" if kind == "scans" else "Eşleşme ve Yanıt Taslağı")
        window.geometry("800x580")
        text = ctk.CTkTextbox(window, wrap="word")
        text.pack(fill="both", expand=True, padx=12, pady=12)
        fields = [("Telefon", "node_id"), ("Seri", "serial"), ("Kayıtlı Hesap", "account"), ("Hedef", "target_url")]
        fields += [("Başlangıç", "started_at"), ("Bitiş", "finished_at"), ("Durum", "status"), ("Açıklama", "message"), ("Okunan Metin Sayısı", "visible_count")] if kind == "scans" else [("İlk Görülme", "first_seen"), ("Son Görülme", "last_seen"), ("Anahtar Kelime", "keyword"), ("Ekrandaki Metin", "screen_text"), ("Yorum Bağlantısı", "comment_url"), ("Yanıtlayan Hesabımız (elle doğrulama)", "reply_account"), ("Yanıt Kayıt Zamanı", "reply_at"), ("Yanıt Bağlantısı", "reply_url"), ("Yanıt Taslağı (bu program göndermedi)", "draft")]
        notice = "Yorum bağlantısı elle bağlandı. Yanıtlandı bilgisi elle doğrulama kaydıdır; program yanıt göndermedi." if kind == "findings" and row.get("comment_key") else "Yorum sahibi ve yorum kimliği doğrulanmadı. Ekran metni eşleşmesidir."
        text.insert("end", notice + "\n\n")
        for label, key in fields:
            text.insert("end", f"{label}: {row.get(key, '')}\n\n")
        text.configure(state="disabled")
        buttons = ctk.CTkFrame(window, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(0, 12))
        def copy_value(value):
            self.clipboard_clear()
            self.clipboard_append(value)
        ctk.CTkButton(buttons, text="Gönderi Linkini Kopyala", command=lambda: copy_value(row["target_url"])).pack(side="left", padx=4)
        if kind == "findings":
            ctk.CTkButton(buttons, text="Taslağı Kopyala", command=lambda: copy_value(row["draft"]), state="disabled" if row["is_replied"] else "normal").pack(side="left", padx=4)
            def reviewed():
                watcher_store.review_finding(row["id"])
                self.refresh_watcher_monitor()
                window.destroy()
            ctk.CTkButton(buttons, text="İnceledim", command=reviewed).pack(side="left", padx=4)
            response_row = ctk.CTkFrame(window, fg_color="transparent")
            response_row.pack(fill="x", padx=12, pady=(0, 12))
            ctk.CTkButton(response_row, text="Yanıtlandı Olarak Kaydet", command=lambda: self.open_reply_confirmation(row, window)).pack(side="left", padx=4)
            if row["is_replied"]:
                def undo():
                    watcher_store.undo_reply(row["id"])
                    self.refresh_watcher_monitor()
                    window.destroy()
                ctk.CTkButton(response_row, text="Yanıtlandı İşaretini Geri Al", command=undo).pack(side="left", padx=4)

    def open_reply_confirmation(self, row, parent):
        window = ctk.CTkToplevel(parent)
        window.title("Yanıtlandı Kaydı — Ortak Yorum Takibi")
        window.geometry("760x490")
        ctk.CTkLabel(window, text="Yalnız bu orijinal yorum yanıtlandı olarak işaretlenir. Gönderi takibi devam eder.\nAynı metni yazan başka kişiler otomatik elenmez.", wraplength=700).pack(padx=15, pady=12)
        entries = {}
        for name, label, value in [("comment_url", "Orijinal Yorumun Bağlantısı (comment_id içermeli)", row.get("comment_url", "")),
                                   ("account", "Yanıtlayan Hesabımızın Adı", ""),
                                   ("reply_url", "Verilmiş Yanıtın Bağlantısı (isteğe bağlı)", "")]:
            ctk.CTkLabel(window, text=label, anchor="w").pack(fill="x", padx=15, pady=(6, 0))
            entries[name] = ctk.CTkEntry(window)
            entries[name].insert(0, value)
            entries[name].pack(fill="x", padx=15, pady=4)
        confirmed = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(window, text="Bu yoruma hesabımızdan yanıt verildiğini Facebook'ta gördüm.", variable=confirmed).pack(padx=15, pady=12)
        error = ctk.CTkLabel(window, text="", text_color="#facc15", wraplength=700)
        error.pack(fill="x", padx=15)
        def save():
            if not confirmed.get():
                error.configure(text="Önce yanıtı Facebook'ta kontrol edip doğrulama kutusunu işaretleyin.")
                return
            try:
                watcher_store.record_reply(row["id"], entries["comment_url"].get(), entries["account"].get(), entries["reply_url"].get())
            except ValueError as exc:
                error.configure(text=str(exc))
                return
            self.log("[NÖBETÇİ] Yorumun yanıtlandığı ortak kayda işlendi. Gönderi takibi devam eder.")
            self.refresh_watcher_monitor()
            window.destroy()
            parent.destroy()
        ctk.CTkButton(window, text="Yanıtlandı Kaydını Onayla", command=save).pack(pady=10)

    def poll_watcher_monitor(self):
        try:
            self.process_ui_events()
            self.refresh_workspace_status()
            for _ in range(100):
                try:
                    line = self.watcher_log_queue.get_nowait()
                except queue.Empty:
                    break
                self.log(line)
            run = watcher_store.get_run()
            if run and run["status"] in {"STARTING", "RUNNING", "WAITING"} and run["process_id"] and not watcher_store.process_alive(run["process_id"]):
                watcher_store.update_run(run["id"], "ERROR", "Nöbetçi işçisi kapandı; son kontrol tamamlanmamış olabilir.")
            self.refresh_watcher_monitor()
        except Exception as exc:
            self.log(f"[NÖBETÇİ TAKİP HATASI] {exc}")
        self.after(1000, self.poll_watcher_monitor)

    def close_command_center(self):
        if getattr(self, "closing_requested", False):
            return
        self.closing_requested = True
        run = watcher_store.get_run()
        if run and run["status"] in {"STARTING", "RUNNING", "WAITING"}:
            self.stop_keyword_watcher()
        if getattr(self, "task_cleanup_busy", False):
            self.stop_active_proc()
        def finish_close():
            if getattr(self, "task_cleanup_busy", False) or getattr(self, "watcher_cleanup_busy", False):
                self.after(200, finish_close)
            else:
                self.destroy()
        finish_close()

    def start_telegram_pipeline(self):
        self.save_group_selections()
        selected_group_urls = [g["url"] for g in self.saved_groups if g.get("selected")]
        if not selected_group_urls:
            self.log("[!] Lütfen yukarıdaki Facebook Grup Butonlarından en az 1 tanesini seçin!")
            return
        self.run_telegram_to_targets(",".join(selected_group_urls))

    def run_telegram_to_targets(self, targets_csv, scope="group_share"):
        try:
            image_path = validate_image(self.selected_image_path)
            options = self.task_timing("publish")
        except ValueError as exc:
            self.log(f"[!] {exc}")
            return
        prod_title = self.ent_prod_title.get().strip()
        prod_link = ""
        aw_flag = "1" if self.var_tg_autowatch.get() else "0"

        selected = self.operation_nodes(scope)
        if not selected:
            self.log("[!] Bu paylaşım işlemi için Telefonları Seç düğmesinden en az bir ONLINE telefon seçin!")
            return
        ser_list = ",".join([x[2] for x in selected])
        metadata = {"timing": options, "devices": {x[2]: {"node_id": x[1], "fb_name": x[3]} for x in selected},
                    "targets": {item["url"]: item["name"] for item in self.saved_groups + self.saved_pages}}
        stable_image = remember_image(image_path)
        metadata["image_name"] = os.path.basename(image_path)
        metadata["history_image"] = stable_image
        metadata["post_watch"] = aw_flag
        plan_id = publication_queue.create(stable_image, prod_title, targets_csv.split(","), [x[2] for x in selected], metadata)
        metadata["publication_plan_id"] = plan_id
        self.log(f"[PAYLAŞIM SIRASI] {len(targets_csv.split(','))} hedef, {len(selected)} telefon; sıra kaydedildi.")
        self.log(f"[GÖRSEL PAYLAŞIMI] {os.path.basename(image_path)} -> Seçili {len(targets_csv.split(','))} hedefe paylaşılacak...")
        threading.Thread(
            target=self._stream_cmd,
            args=([sys.executable, "telegram_pipeline.py", stable_image, targets_csv, prod_title, prod_link, ser_list, aw_flag, json.dumps(metadata, ensure_ascii=False)],),
            daemon=True
        ).start()

    def open_sequential_plans(self):
        window = ctk.CTkToplevel(self)
        window.title("Kayıtlı Sıralar — yalnız elle başlatılır")
        window.geometry("1000x600")
        ctk.CTkLabel(window, text="Panel açılışında görev çalıştırılmaz. Bir sıra seçip Başlat / Devam Et'e basın.", anchor="w").pack(fill="x", padx=16, pady=12)
        tree = ttk.Treeview(window, columns=("kind", "date", "state", "count"), show="headings")
        for key, title in [("kind", "İşlem"), ("date", "Oluşturuldu"), ("state", "Durum"), ("count", "Bekleyen / Kesilen")]:
            tree.heading(key, text=title)
        tree.pack(fill="both", expand=True, padx=16)
        details = ctk.CTkTextbox(window, height=160)
        details.pack(fill="x", padx=16, pady=10)
        plans = {}
        def refresh():
            plans.clear()
            for item in tree.get_children():
                tree.delete(item)
            for item in sequential_jobs.pending_plans():
                plans[item["id"]] = item
                tree.insert("", "end", iid=item["id"], values=("Paylaşım" if item["kind"] == "publication" else "Sıralı Nöbetçi", item["created_at"], item["status"], item["pending"]))
        def show(event=None):
            details.delete("1.0", "end")
            if tree.selection():
                for job in sequential_jobs.jobs(tree.selection()[0]):
                    body = job["payload"]
                    details.insert("end", f"{job['id']} | {job['status']} | {job['serial'] or 'Atanmadı'} | {body.get('author','')} {body.get('text','')} | {body['target']} | {job['message']}\n")
        tree.bind("<<TreeviewSelect>>", show)
        def resume():
            if tree.selection():
                self.resume_sequential_plan(tree.selection()[0])
        bar = ctk.CTkFrame(window, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(bar, text="Seçili Sırayı Başlat / Devam Et", command=resume).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="Yenile", command=refresh).pack(side="left", padx=4)
        refresh()

    def resume_sequential_plan(self, plan_id):
        if self.fleet_sleep_busy or getattr(self, "task_cleanup_busy", False) or getattr(self, "watcher_cleanup_busy", False):
            self.log("[!] Önceki işlem bitmeden başka sıra başlatılmadı.")
            return
        running = watcher_store.get_run()
        if running and running["status"] in {"STARTING", "RUNNING", "WAITING"}:
            self.log("[!] Önce çalışan Nöbetçiyi durdurun.")
            return
        stored = sequential_jobs.plan(plan_id)
        if not stored:
            return
        data = stored["data"]
        if stored["kind"] == "publication":
            metadata = dict(data["metadata"], publication_plan_id=plan_id)
            command = [sys.executable, "telegram_pipeline.py", data["image_path"], ",".join(data["targets"]), data["caption"], "", ",".join(data["selected_serials"]), metadata.get("post_watch", "0"), json.dumps(metadata, ensure_ascii=False)]
            threading.Thread(target=self._stream_cmd, args=(command,), daemon=True).start()
        else:
            watcher_store.save_settings(data)
            for entry, key in [(self.ent_keywords, "keywords"), (self.ent_kw_reply, "reply_template"), (self.ent_cycle_min, "cycle_minutes"), (self.ent_max_rep, "max_replies_per_visit"), (self.ent_reply_gap, "reply_delay_seconds")]:
                entry.delete(0, "end")
                entry.insert(0, str(data.get(key, 10)))
            self.ent_watch_url.delete(0, "end")
            self.var_watcher_sequential.set(True)
            self.var_watcher_auto.set(True)
            self.var_watcher_owned.set(bool(data.get("owned_targets_confirmed")))
            self.watcher_phone_serials = set(data["selected_serials"])
            for key in ("delay_min", "delay_max", "like_percent"):
                widget = self.timing_widgets["watcher"][key]
                widget.delete(0, "end")
                widget.insert(0, str(data.get("timing", timing.DEFAULTS).get(key, timing.DEFAULTS[key])))
            self.timing_widgets["watcher"]["prewarm_enabled"].set(data.get("timing", timing.DEFAULTS)["prewarm_enabled"])
            self.refresh_watched_list_ui()
            self.refresh_watcher_phones()
            self.start_keyword_watcher()

    def refresh_queue_table(self):
        for item in self.tree_q.get_children():
            self.tree_q.delete(item)
        db = sqlite3.connect(DB_FILE)
        c = db.cursor()
        rows = c.execute("SELECT id, node_id, fb_name, persona, task_type, delay_sec, status FROM campaign_queue ORDER BY id DESC LIMIT 80").fetchall()
        pending_cnt = c.execute("SELECT COUNT(*) FROM campaign_queue WHERE status LIKE '%PENDING%'").fetchone()[0]
        db.close()
        self.lbl_kpi_queue.configure(text=f"{pending_cnt} Görev")
        for r in rows:
            self.tree_q.insert("", "end", values=(f"#{r[0]}", r[1], r[2], r[3], r[4], f"T+{r[5]}sn", r[6]))

    def clear_queue_table(self):
        db = sqlite3.connect(DB_FILE)
        db.execute("DELETE FROM campaign_queue")
        db.commit()
        db.close()
        self.comment_counter = 1
        self.refresh_queue_table()
        self.log("[TEMİZLENDİ] Görev kuyruğu sıfırlandı.")

    def stop_active_proc(self):
        with self.process_lock:
            if self.active_proc:
                try:
                    fleet_controls.stop_process_tree(self.active_proc)
                    interrupt_process(self.active_proc.pid)
                    if threading.get_ident() == self.ui_thread:
                        self.refresh_share_history()
                    else:
                        self.ui_events.put(("refresh_after_task", None))
                except Exception as exc:
                    self.log(f"[!] Durdurma: {exc}")
            self.log("[⏹️ DURDURULDU] Aktif arka plan görevi sonlandırıldı.")

    def periodic_ui_sync(self):
        try:
            self.refresh_queue_table()
            self.refresh_watched_list_ui()
            self.refresh_share_history()
            self.refresh_comment_phones()
            self.refresh_watcher_phones()
            self.refresh_operation_phones()
            self.refresh_watcher_engine_status()
        except:
            pass
        self.after(4000, self.periodic_ui_sync)

    def auto_warmup_on_startup(self):
        self.log("[BAŞLANGIÇ] Otomatik görev başlatma kapalı. Başlat / Devam Et düğmesini kullanın.")

if __name__ == "__main__":
    app = AutoFarmModernCommandCenter()
    if "--watcher-monitor" in sys.argv:
        app.select_tab("tab_watcher")
        app.after(200, app.open_watcher_monitor)
    app.mainloop()
