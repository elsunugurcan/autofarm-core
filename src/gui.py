import sys, os, json, subprocess, threading, time, random, sqlite3
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath("."))

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

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
        self.title("AutoFarm-30 // Enterprise Biometric Command Center v7.0")
        self.geometry("1620x950")
        self.configure(fg_color="#090d16")

        self.profiles = get_profiles()
        self.saved_groups = load_json(GROUPS_FILE, [
            {"name": "Örnek Grup 1", "url": "https://www.facebook.com/groups/ornek1", "selected": True}
        ])
        self.saved_pages = load_json(PAGES_FILE, [
            {"name": "Ana Sayfamız", "url": "https://www.facebook.com/ornek_sayfa", "selected": True}
        ])

        self.scrcpy_procs = {}
        self.active_proc = None
        self.row_widgets = {}
        self.group_btn_vars = []
        self.page_btn_vars = []
        self.comment_counter = 1
        self.sidebar_expanded = True
        self.console_expanded = True

        self.setup_treeview_style()
        self.build_layout()
        self.refresh_devices()
        self.refresh_queue_table()
        self.refresh_watched_list_ui()

        self.after(4000, self.periodic_ui_sync)
        self.after(6000, self.auto_warmup_on_startup)

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
            background="#1e293b",
            foreground="#38bdf8",
            borderwidth=0,
            font=("Segoe UI", 9, "bold")
        )
        style.map("Treeview", background=[("selected", "#2563eb")])

    def build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # SOL ACILIR / KAPANIR NAVIGASYON SIDEBAR
        self.sidebar = ctk.CTkFrame(self, width=255, corner_radius=0, fg_color="#0f1523")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        brand_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_row.pack(fill="x", padx=14, pady=(14, 8))

        ctk.CTkButton(
            brand_row, text="☰", width=34, height=34, corner_radius=8,
            fg_color="#1e293b", hover_color="#334155", font=("Segoe UI", 15, "bold"),
            command=self.toggle_sidebar
        ).pack(side="left")

        self.lbl_brand_title = ctk.CTkLabel(
            brand_row, text="⚡ AUTOFARM-30", font=("Segoe UI", 16, "bold"), text_color="#38bdf8"
        )
        self.lbl_brand_title.pack(side="left", padx=10)

        self.lbl_brand_sub = ctk.CTkLabel(
            self.sidebar, text="Enterprise Suite v7.0 (Dikey Kilit)", font=("Segoe UI", 11), text_color="#64748b"
        )
        self.lbl_brand_sub.pack(anchor="w", padx=18, pady=(0, 10))

        self.nav_buttons = {}
        nav_items = [
            ("tab_fleet", "📱  Filo Cihaz Yönetimi"),
            ("tab_campaign", "🎯  Kampanya Dağıtıcı"),
            ("tab_telegram", "✈️  Telegram & Grup Butonları"),
            ("tab_pages", "📄  Sayfalar (Pages) Bölümü"),
            ("tab_report", "🚩  Doğal Şikayet Merkezi"),
            ("tab_watcher", "🔍  Grup & Kelime Nöbetçisi"),
            ("tab_warmup", "🔥  Hesap Isıtma Merkezi")
        ]
        for key, text in nav_items:
            btn = ctk.CTkButton(
                self.sidebar, text=text, anchor="w", height=36, corner_radius=8,
                font=("Segoe UI", 12, "bold"), fg_color="transparent", text_color="#cbd5e1",
                hover_color="#1e293b", command=lambda k=key: self.select_tab(k)
            )
            btn.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[key] = (btn, text)

        # HIZLI CIHAZ EKRAN KAPATMA & DIKEY MOD KONTROLU
        self.quick_frame = ctk.CTkFrame(self.sidebar, fg_color="#161f33", corner_radius=10)
        self.quick_frame.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            self.quick_frame, text="DONANIM & EKRAN KONTROLÜ", font=("Segoe UI", 10, "bold"), text_color="#94a3b8"
        ).pack(anchor="w", padx=12, pady=(8, 4))

        ctk.CTkButton(
            self.quick_frame, text="📴 Cihazda Ekranları & FB/TT Kapat", height=34, corner_radius=6,
            fg_color="#e11d48", hover_color="#be123c", font=("Segoe UI", 11, "bold"),
            command=self.sleep_all_connected
        ).pack(fill="x", padx=10, pady=3)

        ctk.CTkButton(
            self.quick_frame, text="📱 Tümünü Dikey Moda Kilitle", height=30, corner_radius=6,
            fg_color="#0d9488", hover_color="#0f766e", font=("Segoe UI", 11, "bold"),
            command=self.lock_all_portrait
        ).pack(fill="x", padx=10, pady=3)

        ctk.CTkButton(
            self.quick_frame, text="🖥️ PC'de Seçili Ekranları Aç", height=30, corner_radius=6,
            fg_color="#0284c7", hover_color="#0369a1", font=("Segoe UI", 11, "bold"),
            command=self.open_selected_screens
        ).pack(fill="x", padx=10, pady=3)

        ctk.CTkButton(
            self.quick_frame, text="❌ PC'de İzleme Pencerelerini Kapat", height=30, corner_radius=6,
            fg_color="#475569", hover_color="#334155", font=("Segoe UI", 11),
            command=self.close_all_screens
        ).pack(fill="x", padx=10, pady=3)

        ctk.CTkButton(
            self.quick_frame, text="🔇 Tüm Sesleri Kapat", height=28, corner_radius=6,
            fg_color="#334155", hover_color="#475569", font=("Segoe UI", 11),
            command=self.mute_all_connected
        ).pack(fill="x", padx=10, pady=(3, 8))

        self.status_badge = ctk.CTkFrame(self.sidebar, fg_color="#0b131e", corner_radius=10, border_width=1, border_color="#059669")
        self.status_badge.pack(side="bottom", fill="x", padx=12, pady=10)
        ctk.CTkLabel(
            self.status_badge, text="● OTOMATİK TEMİZLİK: AKTİF", font=("Segoe UI", 10, "bold"), text_color="#4ade80"
        ).pack(anchor="w", padx=10, pady=(6, 2))
        ctk.CTkLabel(
            self.status_badge,
            text="• Sürekli Dikey Ekran Kilidi\n• İşlem Bitince FB & TikTok Kapatır\n• Cihaz Ekranlarını Uyku Moduna Alır",
            justify="left", font=("Segoe UI", 10), text_color="#94a3b8"
        ).pack(anchor="w", padx=10, pady=(0, 6))

        # SAG ANA CALISMA ALANI
        self.main_area = ctk.CTkFrame(self, fg_color="#090d16", corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=16, pady=12)
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(1, weight=1)

        kpi_row = ctk.CTkFrame(self.main_area, fg_color="transparent")
        kpi_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for c in range(4):
            kpi_row.grid_columnconfigure(c, weight=1)

        self.lbl_kpi_nodes = self.create_kpi_card(kpi_row, 0, "FİLO & DİKEY KİLİT", "0 / 25 Node", "Sürekli Dikey (Portrait) Aktif", "#38bdf8")
        self.lbl_kpi_acc = self.create_kpi_card(kpi_row, 1, "GRUP & SAYFA HAVUZU", f"{len(self.saved_groups)} Grup | {len(self.saved_pages)} Sayfa", "Seçilebilir Buton Sistemi", "#a855f7")
        self.lbl_kpi_queue = self.create_kpi_card(kpi_row, 2, "KUYRUKTAKİ GÖREV", "0 Görev", "Bitince FB/TT & Ekran Kapanır", "#22c55e")
        self.lbl_kpi_bio = self.create_kpi_card(kpi_row, 3, "BİYOLOJİK SAAT FAZI", "PRIME_TIME (Zirve)", "Doğal Şikayet & Sandviç Açık", "#f59e0b")

        self.notebook_container = ctk.CTkFrame(self.main_area, fg_color="#0f1523", corner_radius=12, border_width=1, border_color="#1e293b")
        self.notebook_container.grid(row=1, column=0, sticky="nsew")
        self.notebook_container.grid_columnconfigure(0, weight=1)
        self.notebook_container.grid_rowconfigure(0, weight=1)

        self.tabs = {}
        for key in ["tab_fleet", "tab_campaign", "tab_telegram", "tab_pages", "tab_report", "tab_watcher", "tab_warmup"]:
            frame = ctk.CTkFrame(self.notebook_container, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=14, pady=12)
            self.tabs[key] = frame

        self.build_tab_fleet(self.tabs["tab_fleet"])
        self.build_tab_campaign(self.tabs["tab_campaign"])
        self.build_tab_telegram(self.tabs["tab_telegram"])
        self.build_tab_pages(self.tabs["tab_pages"])
        self.build_tab_report(self.tabs["tab_report"])
        self.build_tab_watcher(self.tabs["tab_watcher"])
        self.build_tab_warmup(self.tabs["tab_warmup"])

        # ALT ACILIR / KAPANIR CANLI KONSOL CEKMECESI
        self.console_wrapper = ctk.CTkFrame(self.main_area, fg_color="#0f1523", corner_radius=10, border_width=1, border_color="#1e293b")
        self.console_wrapper.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        con_hdr = ctk.CTkFrame(self.console_wrapper, fg_color="#161f33", corner_radius=8, height=34)
        con_hdr.pack(fill="x", padx=4, pady=4)

        ctk.CTkLabel(
            con_hdr, text="🖥️  Canlı Operasyon, Sandviç Akışı & Telemetri Konsolu",
            font=("Segoe UI", 11, "bold"), text_color="#38bdf8"
        ).pack(side="left", padx=10)

        self.btn_toggle_con = ctk.CTkButton(
            con_hdr, text="▼ Konsolu Gizle", width=120, height=24, corner_radius=6,
            fg_color="#334155", hover_color="#475569", font=("Segoe UI", 10, "bold"),
            command=self.toggle_console
        )
        self.btn_toggle_con.pack(side="right", padx=6, pady=4)

        ctk.CTkButton(
            con_hdr, text="⏹️ Görevi Durdur & FB/TT Kapat", width=190, height=24, corner_radius=6,
            fg_color="#ea580c", hover_color="#c2410c", font=("Segoe UI", 10, "bold"),
            command=self.stop_active_proc
        ).pack(side="right", padx=4, pady=4)

        self.txt_log = ctk.CTkTextbox(
            self.console_wrapper, height=125, fg_color="#060911", text_color="#4ade80",
            font=("Consolas", 11), corner_radius=6
        )
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.log("[SİSTEM] AutoFarm-30 v7.0 hazır. Tüm telefonlar dikey (Portrait) moda kilitlendi.")

        self.select_tab("tab_fleet")

    def create_kpi_card(self, parent, col, title, main_val, sub_val, accent_color):
        card = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1e293b")
        card.grid(row=0, column=col, sticky="ew", padx=6)

        top_line = ctk.CTkFrame(card, height=4, corner_radius=2, fg_color=accent_color)
        top_line.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(card, text=title, font=("Segoe UI", 10, "bold"), text_color="#94a3b8").pack(anchor="w", padx=16)
        lbl_val = ctk.CTkLabel(card, text=main_val, font=("Segoe UI", 18, "bold"), text_color="#f8fafc")
        lbl_val.pack(anchor="w", padx=16, pady=(2, 2))
        ctk.CTkLabel(card, text=sub_val, font=("Segoe UI", 10), text_color=accent_color).pack(anchor="w", padx=16, pady=(0, 8))
        return lbl_val

    def toggle_sidebar(self):
        if self.sidebar_expanded:
            self.sidebar.configure(width=64)
            self.lbl_brand_title.pack_forget()
            self.lbl_brand_sub.pack_forget()
            self.quick_frame.pack_forget()
            self.status_badge.pack_forget()
            for key, (btn, full_txt) in self.nav_buttons.items():
                icon = full_txt.split()[0]
                btn.configure(text=icon, width=40, anchor="center")
            self.sidebar_expanded = False
        else:
            self.sidebar.configure(width=255)
            self.lbl_brand_title.pack(side="left", padx=10)
            self.lbl_brand_sub.pack(anchor="w", padx=18, pady=(0, 10))
            for key, (btn, full_txt) in self.nav_buttons.items():
                btn.configure(text=full_txt, anchor="w")
            self.quick_frame.pack(fill="x", padx=12, pady=10)
            self.status_badge.pack(side="bottom", fill="x", padx=12, pady=10)
            self.sidebar_expanded = True

    def toggle_console(self):
        if self.console_expanded:
            self.txt_log.pack_forget()
            self.btn_toggle_con.configure(text="▲ Konsolu Aç")
            self.console_expanded = False
        else:
            self.txt_log.pack(fill="both", expand=True, padx=6, pady=(0, 6))
            self.btn_toggle_con.configure(text="▼ Konsolu Gizle")
            self.console_expanded = True

    def select_tab(self, tab_key):
        for k, frame in self.tabs.items():
            if k == tab_key:
                frame.tkraise()
        for k, (btn, _) in self.nav_buttons.items():
            if k == tab_key:
                btn.configure(fg_color="#1d4ed8", text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color="#cbd5e1")

    # ==========================================================================
    # SEKME 1: FILO CIHAZ YONETIMI (+ CIHAZ EKRAN KAPATMA BUTONU)
    # ==========================================================================
    def build_tab_fleet(self, parent):
        top_bar = ctk.CTkFrame(parent, fg_color="#161f33", corner_radius=10)
        top_bar.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            top_bar, text="📱 Fiziksel Cihaz Filosu (25 Node) & Tekil Ekran / Uygulama Kontrolü",
            font=("Segoe UI", 14, "bold"), text_color="#38bdf8"
        ).pack(side="left", padx=14, pady=10)

        ctk.CTkButton(
            top_bar, text="💾 İsim, Proxy & DNA Kaydet", height=32, corner_radius=8,
            fg_color="#7c3aed", hover_color="#6d28d9", font=("Segoe UI", 11, "bold"),
            command=self.save_all_profiles
        ).pack(side="right", padx=8, pady=8)

        ctk.CTkButton(
            top_bar, text="📴 Tüm Cihaz Ekranlarını & FB/TT Kapat", height=32, corner_radius=8,
            fg_color="#e11d48", hover_color="#be123c", font=("Segoe UI", 11, "bold"),
            command=self.sleep_all_connected
        ).pack(side="right", padx=4, pady=8)

        ctk.CTkButton(
            top_bar, text="🔄 Cihazları Tara (Dikey Kilitle)", height=32, corner_radius=8,
            fg_color="#2563eb", hover_color="#1d4ed8", font=("Segoe UI", 11, "bold"),
            command=self.refresh_devices
        ).pack(side="right", padx=4, pady=8)

        ctk.CTkButton(
            top_bar, text="🟢 Sadece ONLINE Seç", height=32, corner_radius=8,
            fg_color="#059669", hover_color="#047857", font=("Segoe UI", 11, "bold"),
            command=self.select_only_online
        ).pack(side="right", padx=4, pady=8)

        hdr = ctk.CTkFrame(parent, fg_color="#1e293b", corner_radius=8, height=34)
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

            ent_name = ctk.CTkEntry(row, width=170, height=28, corner_radius=6, fg_color="#1e293b", border_color="#334155", font=("Segoe UI", 11))
            ent_name.insert(0, self.profiles[node_id].get("fb_name", f"FB Hesap {i:02d}"))
            ent_name.pack(side="left", padx=4)

            ent_proxy = ctk.CTkEntry(row, width=200, height=28, corner_radius=6, fg_color="#1e293b", border_color="#334155", font=("Consolas", 10))
            ent_proxy.insert(0, self.profiles[node_id].get("proxy", f"socks5://127.0.0.1:{1080+i}"))
            ent_proxy.pack(side="left", padx=4)

            cmb_persona = ctk.CTkComboBox(row, values=PERSONAS, width=145, height=28, corner_radius=6, fg_color="#1e293b", border_color="#334155", font=("Segoe UI", 10))
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
    def build_tab_campaign(self, parent):
        top_card = ctk.CTkFrame(parent, fg_color="#141c2e", corner_radius=12, border_width=1, border_color="#1e293b")
        top_card.pack(fill="x", pady=(0, 10))

        hdr_row = ctk.CTkFrame(top_card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkLabel(hdr_row, text="🚀 Otomatik Kampanya Dağıtıcı (Sayılı Yorum | Gruba Katıl | Kişi Ekle | Şikayet)", font=("Segoe UI", 14, "bold"), text_color="#38bdf8").pack(side="left")

        self.var_rand_order = tk.BooleanVar(value=True)
        ctk.CTkSwitch(hdr_row, text="Rastgele Cihaz Sırası", variable=self.var_rand_order, font=("Segoe UI", 11, "bold")).pack(side="right", padx=10)

        self.var_sandwich = tk.BooleanVar(value=True)
        ctk.CTkSwitch(hdr_row, text="Organik Sandviç Oturumu", variable=self.var_sandwich, font=("Segoe UI", 11, "bold")).pack(side="right", padx=10)

        ctk.CTkLabel(hdr_row, text="Dalga Aralığı (Min-Max sn):", font=("Segoe UI", 11), text_color="#94a3b8").pack(side="right", padx=4)
        self.ent_wmax = ctk.CTkEntry(hdr_row, width=48, height=28, justify="center")
        self.ent_wmax.insert(0, "14")
        self.ent_wmax.pack(side="right", padx=2)
        self.ent_wmin = ctk.CTkEntry(hdr_row, width=48, height=28, justify="center")
        self.ent_wmin.insert(0, "5")
        self.ent_wmin.pack(side="right", padx=2)

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

        ctk.CTkButton(grid_f, text="🎯 Yorum + Beğeni Dağıt", width=190, height=34, corner_radius=8, fg_color="#2563eb", hover_color="#1d4ed8", font=("Segoe UI", 11, "bold"), command=lambda: self.queue_and_run("YORUM+BEGENI")).grid(row=0, column=3, pady=5, padx=(4, 0))

        ctk.CTkLabel(grid_f, text="👥 Facebook Gruba Katılma:", font=("Segoe UI", 11, "bold"), text_color="#4ade80").grid(row=1, column=0, sticky="w", pady=5, padx=(0, 10))
        self.ent_grp_url = ctk.CTkEntry(grid_f, height=34, corner_radius=8)
        self.ent_grp_url.insert(0, "https://www.facebook.com/groups/...")
        self.ent_grp_url.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5, padx=4)

        ctk.CTkButton(grid_f, text="👥 Tüm Kişilerle Gruba Katıl", width=190, height=34, corner_radius=8, fg_color="#16a34a", hover_color="#15803d", font=("Segoe UI", 11, "bold"), command=lambda: self.queue_and_run("GRUP_KATIL")).grid(row=1, column=3, pady=5, padx=(4, 0))

        ctk.CTkLabel(grid_f, text="➕ Kişi Profili (Arkadaş Ekle):", font=("Segoe UI", 11, "bold"), text_color="#c084fc").grid(row=2, column=0, sticky="w", pady=5, padx=(0, 10))
        self.ent_frd_url = ctk.CTkEntry(grid_f, height=34, corner_radius=8)
        self.ent_frd_url.insert(0, "https://www.facebook.com/profile.php?id=...")
        self.ent_frd_url.grid(row=2, column=1, columnspan=2, sticky="ew", pady=5, padx=4)

        ctk.CTkButton(grid_f, text="➕ Kişiyi Ekle (Korumalı)", width=190, height=34, corner_radius=8, fg_color="#9333ea", hover_color="#7e22ce", font=("Segoe UI", 11, "bold"), command=lambda: self.queue_and_run("KISI_EKLE")).grid(row=2, column=3, pady=5, padx=(4, 0))

        q_card = ctk.CTkFrame(parent, fg_color="#141c2e", corner_radius=12, border_width=1, border_color="#1e293b")
        q_card.pack(fill="both", expand=True)

        q_bar = ctk.CTkFrame(q_card, fg_color="transparent")
        q_bar.pack(fill="x", padx=14, pady=8)
        ctk.CTkLabel(q_bar, text="📋 Canlı Drip-Feed Görev Kuyruğu (Görev Bitince FB/TikTok & Ekranlar Otomatik Kapanır)", font=("Segoe UI", 13, "bold"), text_color="#f8fafc").pack(side="left")

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
    def build_tab_telegram(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#141c2e", corner_radius=12, border_width=1, border_color="#1e293b")
        card.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(
            card, text="✈️ Telegram Ürün Görseli + Başlık + Link İndirici ve Seçilebilir Grup Butonları",
            font=("Segoe UI", 15, "bold"), text_color="#ec4899"
        ).pack(anchor="w", padx=20, pady=(14, 4))

        # 1. Grup Linki Ekleme ve Buton Olusturma Alani
        add_grp_bar = ctk.CTkFrame(card, fg_color="#0f1523", corner_radius=10)
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

        ctk.CTkButton(
            add_grp_bar, text="👥 Seçili Gruplara Tüm Cihazları Katılt", height=32, corner_radius=8,
            fg_color="#2563eb", hover_color="#1d4ed8", font=("Segoe UI", 11, "bold"),
            command=self.join_selected_group_buttons
        ).pack(side="left", padx=(2, 12), pady=10)

        # 2. Secilebilir Grup Butonlari (Tiklanabilir Buton Havuzu)
        grp_pool_hdr = ctk.CTkFrame(card, fg_color="transparent")
        grp_pool_hdr.pack(fill="x", padx=20, pady=(4, 2))
        ctk.CTkLabel(grp_pool_hdr, text="📌 Paylaşım Yapılacak Facebook Grupları (Göndermek İstediğin Gruplara Tıkla / Seç):", font=("Segoe UI", 12, "bold"), text_color="#facc15").pack(side="left")
        ctk.CTkButton(grp_pool_hdr, text="☑️ Tüm Grupları Seç", width=130, height=26, fg_color="#334155", font=("Segoe UI", 10, "bold"), command=lambda: self.toggle_all_group_btns(True)).pack(side="right", padx=4)
        ctk.CTkButton(grp_pool_hdr, text="⬜ Seçimi Kaldır", width=110, height=26, fg_color="#334155", font=("Segoe UI", 10), command=lambda: self.toggle_all_group_btns(False)).pack(side="right", padx=4)

        self.grp_buttons_frame = ctk.CTkScrollableFrame(card, height=120, fg_color="#0b0f19", corner_radius=10)
        self.grp_buttons_frame.pack(fill="x", padx=20, pady=4)
        self.render_group_buttons()

        # 3. Telegram Gonderi + Baslik + Gorsel + Urun Linki Formu
        form = ctk.CTkFrame(card, fg_color="#0f1523", corner_radius=10)
        form.pack(fill="x", padx=20, pady=8)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Telegram Gönderi Linki (Görsel + Başlık + Link Alınır):", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=14, pady=8)
        self.ent_tg_url = ctk.CTkEntry(form, height=34, corner_radius=8)
        self.ent_tg_url.insert(0, "https://t.me/kanal_adi/123")
        self.ent_tg_url.grid(row=0, column=1, sticky="ew", padx=14, pady=8)

        ctk.CTkLabel(form, text="Yoruma Eklenecek Ürün Başlığı:", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", padx=14, pady=8)
        self.ent_prod_title = ctk.CTkEntry(form, height=34, corner_radius=8)
        self.ent_prod_title.insert(0, "Fırsat Ürünü Stokta")
        self.ent_prod_title.grid(row=1, column=1, sticky="ew", padx=14, pady=8)

        ctk.CTkLabel(form, text="Yoruma / Posta Eklenecek Ürün Linki:", font=("Segoe UI", 11, "bold")).grid(row=2, column=0, sticky="w", padx=14, pady=8)
        self.ent_prod_link = ctk.CTkEntry(form, height=34, corner_radius=8)
        self.ent_prod_link.insert(0, "https://urun-linki.com/kampanya")
        self.ent_prod_link.grid(row=2, column=1, sticky="ew", padx=14, pady=8)

        act_row = ctk.CTkFrame(card, fg_color="transparent")
        act_row.pack(fill="x", padx=20, pady=8)

        self.var_tg_autowatch = tk.BooleanVar(value=True)
        ctk.CTkSwitch(
            act_row, text="Paylaşım Sonrası 16 Dk Yorum Nöbetçisini Başlat (Kapalıysa İşlem Bitince FB/TT ve Ekranları Kapatır)",
            variable=self.var_tg_autowatch, font=("Segoe UI", 11, "bold")
        ).pack(side="left")

        ctk.CTkButton(
            act_row, text="🚀 Telegram'dan Görsel + Başlık İndir ve Seçili Grup Butonlarında Paylaş",
            height=42, width=460, corner_radius=10, fg_color="#db2777", hover_color="#be185d", font=("Segoe UI", 12, "bold"),
            command=self.start_telegram_pipeline
        ).pack(side="right")

    def render_group_buttons(self):
        for widget in self.grp_buttons_frame.winfo_children():
            widget.destroy()
        self.group_btn_vars.clear()

        for idx, grp in enumerate(self.saved_groups):
            row_f = ctk.CTkFrame(self.grp_buttons_frame, fg_color="#161f33", corner_radius=8)
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
        selected_urls = [g["url"] for g in self.saved_groups if g.get("selected")]
        if not selected_urls:
            self.log("[!] Katılmak için en az 1 grup butonu seçin!")
            return
        for u in selected_urls:
            self.ent_grp_url.delete(0, "end")
            self.ent_grp_url.insert(0, u)
            self.queue_and_run("GRUP_KATIL")

    # ==========================================================================
    # SEKME 4: SAYFALAR (PAGES) BOLUMU
    # ==========================================================================
    def build_tab_pages(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#141c2e", corner_radius=12, border_width=1, border_color="#1e293b")
        card.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(
            card, text="📄 Facebook Sayfalar (Pages) Yönetim & Etkileşim Merkezi",
            font=("Segoe UI", 15, "bold"), text_color="#a855f7"
        ).pack(anchor="w", padx=20, pady=(14, 4))
        ctk.CTkLabel(
            card, text="Sayfalarını buton olarak kaydet; istediğin sayfalara tek tıkla toplu Beğeni/Takip, Son Gönderiye Yorum veya Post Paylaşımı gönder.",
            font=("Segoe UI", 11), text_color="#94a3b8"
        ).pack(anchor="w", padx=20, pady=(0, 10))

        add_pg_bar = ctk.CTkFrame(card, fg_color="#0f1523", corner_radius=10)
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

        pg_act = ctk.CTkFrame(card, fg_color="#0f1523", corner_radius=10)
        pg_act.pack(fill="x", padx=20, pady=10)

        ctk.CTkButton(
            pg_act, text="👍 Seçili Sayfaları Beğen, Takip Et & Son Gönderiyi Beğen", height=40, corner_radius=8,
            fg_color="#7c3aed", hover_color="#6d28d9", font=("Segoe UI", 12, "bold"),
            command=self.follow_selected_pages
        ).pack(side="left", padx=14, pady=14)

        ctk.CTkButton(
            pg_act, text="✈️ Seçili Sayfalarda Telegram Gönderisini Paylaş", height=40, corner_radius=8,
            fg_color="#db2777", hover_color="#be185d", font=("Segoe UI", 12, "bold"),
            command=self.share_telegram_on_selected_pages
        ).pack(side="left", padx=8, pady=14)

    def render_page_buttons(self):
        for widget in self.pg_buttons_frame.winfo_children():
            widget.destroy()
        self.page_btn_vars.clear()

        for idx, pg in enumerate(self.saved_pages):
            row_f = ctk.CTkFrame(self.pg_buttons_frame, fg_color="#161f33", corner_radius=8)
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
        if not urls:
            self.log("[!] İşlem için en az 1 sayfa butonu seçin!")
            return
        for u in urls:
            self.queue_custom_task("SAYFA_ETKILESIM", u, "Sayfa Beğen & Takip Et")
        self.run_queue_worker()

    def share_telegram_on_selected_pages(self):
        self.save_page_selections()
        urls = [p["url"] for p in self.saved_pages if p.get("selected")]
        if not urls:
            self.log("[!] Paylaşım için en az 1 sayfa butonu seçin!")
            return
        self.run_telegram_to_targets(",".join(urls))

    # ==========================================================================
    # SEKME 5: DOGAL SIKAYET ETME (REPORT) MERKEZI
    # ==========================================================================
    def build_tab_report(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#141c2e", corner_radius=12, border_width=1, border_color="#1e293b")
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

        form = ctk.CTkFrame(card, fg_color="#0f1523", corner_radius=12)
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
        self.queue_custom_task("SIKAYET_ET", url, reason_code)
        self.select_tab("tab_campaign")
        self.run_queue_worker()

    # ==========================================================================
    # SEKME 6: GRUP & ANAHTAR KELIME NOBETCISI (16 DK / MAX 3 CEVAP)
    # ==========================================================================
    def build_tab_watcher(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#141c2e", corner_radius=12, border_width=1, border_color="#1e293b")
        card.pack(fill="both", expand=True, padx=6, pady=6)

        ctk.CTkLabel(card, text="🔍 Grup Gönderileri Anahtar Kelime Nöbetçisi (16 Dk Karışık Kontrol | Max 3 Cevap)", font=("Segoe UI", 15, "bold"), text_color="#facc15").pack(anchor="w", padx=20, pady=(14, 4))

        f_grid = ctk.CTkFrame(card, fg_color="#0f1523", corner_radius=10)
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
        self.ent_keywords.insert(0, "fiyat, link, bilgi, kaç, ne kadar, nerede, dm, ?")
        self.ent_keywords.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(6, 14), pady=8)

        ctk.CTkLabel(f_grid, text="Otomatik Cevap Metni (+Sayı):", font=("Segoe UI", 11, "bold")).grid(row=2, column=0, sticky="w", padx=14, pady=8)
        self.ent_kw_reply = ctk.CTkEntry(f_grid, height=34, corner_radius=8)
        self.ent_kw_reply.insert(0, "Detaylı bilgi ve ürün linki için mesaj kutunuzu kontrol edebilirsiniz")
        self.ent_kw_reply.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(6, 14), pady=8)

        opt_row = ctk.CTkFrame(card, fg_color="transparent")
        opt_row.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(opt_row, text="Kontrol Periyodu (Dakika):", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 8))
        self.ent_cycle_min = ctk.CTkEntry(opt_row, width=65, height=34, justify="center", font=("Segoe UI", 12, "bold"))
        self.ent_cycle_min.insert(0, "16")
        self.ent_cycle_min.pack(side="left", padx=(0, 24))

        ctk.CTkLabel(opt_row, text="Gönderi Başına Max Cevap Sayısı:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 8))
        self.ent_max_rep = ctk.CTkEntry(opt_row, width=65, height=34, justify="center", font=("Segoe UI", 12, "bold"))
        self.ent_max_rep.insert(0, "3")
        self.ent_max_rep.pack(side="left", padx=(0, 24))

        ctk.CTkButton(
            opt_row, text="▶️ Karışık Nöbetçi Motorunu Başlat", height=38, width=260, corner_radius=8,
            fg_color="#d97706", hover_color="#b45309", font=("Segoe UI", 12, "bold"),
            command=self.start_keyword_watcher
        ).pack(side="right")

        self.lbl_watch_count = ctk.CTkLabel(card, text="İzlenen Gönderi Listesi (0 Adet):", font=("Segoe UI", 12, "bold"), text_color="#38bdf8")
        self.lbl_watch_count.pack(anchor="w", padx=20, pady=(4, 4))

        self.txt_watched_list = ctk.CTkTextbox(card, height=130, fg_color="#0b0f19", text_color="#cbd5e1", font=("Consolas", 11), corner_radius=8)
        self.txt_watched_list.pack(fill="both", expand=True, padx=20, pady=(0, 12))

    # ==========================================================================
    # SEKME 7: AKILLI HESAP ISITMA MERKEZI
    # ==========================================================================
    def build_tab_warmup(self, parent):
        card = ctk.CTkFrame(parent, fg_color="#141c2e", corner_radius=12, border_width=1, border_color="#1e293b")
        card.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(card, text="🔥 Biyometrik Facebook Hesap Isıtma & Donma Kurtarıcı Stüdyosu", font=("Segoe UI", 16, "bold"), text_color="#facc15").pack(anchor="w", padx=24, pady=(20, 6))
        ctk.CTkLabel(
            card,
            text="Cihazlar dikey modda ana akışta insan gibi gezinir ve beğeni bırakır. Isıtma bittiğinde Facebook ve TikTok kapatılıp ekran uyutulur.",
            justify="left", font=("Segoe UI", 12), text_color="#94a3b8"
        ).pack(anchor="w", padx=24, pady=(0, 20))

        form = ctk.CTkFrame(card, fg_color="#0f1523", corner_radius=12)
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
            r1, text="Panel Açıldığında Boştaki Cihazları Otomatik Isıtmaya Al",
            variable=self.var_auto_warm, font=("Segoe UI", 12, "bold")
        ).pack(side="left", padx=10)

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
            command=self.stop_and_sleep_all
        ).pack(side="left")

    # ==========================================================================
    # YARDIMCI FONKSIYONLAR
    # ==========================================================================
    def log(self, msg):
        line = time.strftime("%H:%M:%S") + "  " + str(msg) + "\n"
        self.txt_log.insert("end", line)
        self.txt_log.see("end")

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
        threading.Thread(target=self._refresh_devices_bg, daemon=True).start()

    def _refresh_devices_bg(self):
        subprocess.run("adb reconnect offline", shell=True, capture_output=True)
        out = subprocess.check_output("adb devices", shell=True, text=True).strip().splitlines()[1:]
        connected = [l.split()[0] for l in out if len(l.split()) >= 2 and l.split()[1] == "device"]

        self.lbl_kpi_nodes.configure(text=f"{len(connected)} / 25 Online")
        for i in range(1, 26):
            w = self.row_widgets[i]
            if i <= len(connected):
                ser = connected[i - 1]
                w["serial_val"] = ser
                lock_portrait_mode(ser)
                vpn_ok, level, temp = check_vpn_and_temp(ser)
                vpn_tag = "VPN:OK" if vpn_ok else "VPN:YOK"
                st_color = "#4ade80" if vpn_ok else "#facc15"
                w["ser"].configure(text=ser, text_color="#f8fafc")
                w["st"].configure(text=f"● ON | {vpn_tag} | {int(temp)}°C", text_color=st_color)
            else:
                w["serial_val"] = None
                w["ser"].configure(text=f"BEKLIYOR_NODE_{i:02d}", text_color="#64748b")
                w["st"].configure(text="○ OFFLINE", text_color="#f87171")
        self.log(f"[TARAMA & DİKEY KİLİT] {len(connected)} cihaz eşleştirildi ve dikey (Portrait) moda sabitlendi.")

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

    def open_single_screen(self, idx):
        ser = self.row_widgets[idx]["serial_val"]
        if not ser:
            self.log(f"[!] NODE-{idx:02d} USB'de bağlı değil!")
            return
        self.close_single_screen(idx)
        fb_name = self.row_widgets[idx]["name"].get().strip()
        col, row = (idx - 1) % 7, (idx - 1) // 7
        x, y = 10 + col * 265, 25 + row * 340
        port = 27183 + idx
        wake_and_home(ser)
        cmd = f'scrcpy -s {ser} -p {port} --no-audio --window-title "NODE-{idx:02d} | {fb_name} ({ser})" --window-x {x} --window-y {y} --window-width 255 --window-height 310 --max-size 640 --max-fps 15 -b 1M'
        self.scrcpy_procs[idx] = subprocess.Popen(cmd, shell=True)
        self.log(f"[EKRAN AÇILDI] NODE-{idx:02d} ({fb_name})")

    def close_single_screen(self, idx):
        ser = self.row_widgets[idx]["serial_val"]
        if os.name == "nt":
            subprocess.run(f'taskkill /F /FI "WINDOWTITLE eq NODE-{idx:02d}*" /T', shell=True, capture_output=True)
        elif ser:
            subprocess.run(f'pkill -f "scrcpy.*{ser}"', shell=True, capture_output=True)
        if idx in self.scrcpy_procs:
            try: self.scrcpy_procs[idx].terminate()
            except: pass

    def open_selected_screens(self):
        selected = self.get_selected_online_nodes()
        self.log(f"[*] Seçili {len(selected)} cihazın ekranı PC'de açılıyor...")
        def _bg():
            for idx, _, _, _, _ in selected:
                self.open_single_screen(idx)
                time.sleep(0.55)
        threading.Thread(target=_bg, daemon=True).start()

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
        self.stop_active_proc()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.active_proc = proc
        for line in proc.stdout:
            self.log(line.strip())
        self.refresh_queue_table()

    def start_selected_warmup(self):
        selected = self.get_selected_online_nodes()
        if not selected:
            self.log("[!] Isıtma için seçili ONLINE cihaz yok!")
            return
        mins = self.ent_warm_min.get().strip() or "30"
        lprob = self.ent_warm_like.get().strip() or "15"
        ser_list = ",".join([x[2] for x in selected])
        self.log(f"[HESAP ISITMA] {len(selected)} cihaz {mins} dk dikey modda Facebook ısıtmaya alındı...")
        threading.Thread(target=self._stream_cmd, args=([sys.executable, "core_engine.py", "warmup", mins, lprob, ser_list],), daemon=True).start()

    def start_single_warmup(self, idx):
        ser = self.row_widgets[idx]["serial_val"]
        if not ser: return
        mins = self.ent_warm_min.get().strip() or "30"
        lprob = self.ent_warm_like.get().strip() or "15"
        self.log(f"[TEKİL ISITMA] NODE-{idx:02d} ({ser}) {mins} dk ısıtmaya alındı...")
        threading.Thread(target=self._stream_cmd, args=([sys.executable, "core_engine.py", "warmup", mins, lprob, ser],), daemon=True).start()

    def queue_custom_task(self, task_mode, url, comment_label):
        self.save_all_profiles()
        selected = self.get_selected_online_nodes()
        if not selected:
            self.log("[!] Görev atanacak seçili ONLINE cihaz bulunamadı!")
            return
        if self.var_rand_order.get():
            random.shuffle(selected)
        wmin = int(self.ent_wmin.get().strip() or "5")
        wmax = int(self.ent_wmax.get().strip() or "14")
        camp_code = f"CMP-{random.randint(1000, 9999)}"

        db = sqlite3.connect(DB_FILE)
        c = db.cursor()
        for idx, node_id, ser, fb_name, persona in selected:
            delay_s = random.randint(wmin, wmax)
            c.execute("""INSERT INTO campaign_queue
                (camp_code, node_id, serial, fb_name, persona, task_type, target_url, comment_text, delay_sec, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (camp_code, node_id, ser, fb_name, persona, task_mode, url, comment_label, delay_s, f"[PENDING] {comment_label}"))
        db.commit()
        db.close()
        self.refresh_queue_table()

    def queue_and_run(self, task_mode):
        if task_mode == "YORUM+BEGENI":
            url = self.ent_post_url.get().strip()
            base_title = self.ent_comm_title.get().strip() or "Harika paylaşım"
            self.save_all_profiles()
            selected = self.get_selected_online_nodes()
            if not selected: return
            if self.var_rand_order.get(): random.shuffle(selected)
            wmin = int(self.ent_wmin.get().strip() or "5")
            wmax = int(self.ent_wmax.get().strip() or "14")
            camp_code = f"CMP-{random.randint(1000, 9999)}"
            db = sqlite3.connect(DB_FILE)
            c = db.cursor()
            for idx, node_id, ser, fb_name, persona in selected:
                delay_s = random.randint(wmin, wmax)
                numbered_comment = f"{base_title} #{self.comment_counter}"
                self.comment_counter += 1
                c.execute("""INSERT INTO campaign_queue
                    (camp_code, node_id, serial, fb_name, persona, task_type, target_url, comment_text, delay_sec, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (camp_code, node_id, ser, fb_name, persona, task_mode, url, numbered_comment, delay_s, f"[PENDING] {numbered_comment}"))
            db.commit()
            db.close()
            self.refresh_queue_table()
        elif task_mode == "GRUP_KATIL":
            self.queue_custom_task("GRUP_KATIL", self.ent_grp_url.get().strip(), "Gruba Katıl")
        else:
            self.queue_custom_task("KISI_EKLE", self.ent_frd_url.get().strip(), "Arkadaş Ekle")

        self.run_queue_worker()

    def run_queue_worker(self):
        sw_flag = "1" if self.var_sandwich.get() else "0"
        threading.Thread(target=self._stream_cmd, args=([sys.executable, "core_engine.py", "run_queue", sw_flag],), daemon=True).start()

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
        if not url or "facebook.com" not in url:
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

    def start_keyword_watcher(self):
        cfg = self.load_watch_cfg()
        cur_url = self.ent_watch_url.get().strip()
        if "facebook.com" in cur_url and cur_url not in cfg["posts"]:
            cfg["posts"].append(cur_url)
        cfg["keywords"] = self.ent_keywords.get().strip()
        cfg["reply_template"] = self.ent_kw_reply.get().strip()
        cfg["cycle_minutes"] = int(self.ent_cycle_min.get().strip() or "16")
        cfg["max_replies_per_visit"] = int(self.ent_max_rep.get().strip() or "3")
        cfg["min_wait"] = int(self.ent_wmin.get().strip() or "6")
        cfg["max_wait"] = int(self.ent_wmax.get().strip() or "15")
        save_json("config/watched_posts.json", cfg)
        self.refresh_watched_list_ui()

        selected = self.get_selected_online_nodes()
        if not selected:
            self.log("[!] Kontrol için seçili ONLINE cihaz yok!")
            return
        ser_list = ",".join([x[2] for x in selected])
        threading.Thread(target=self._stream_cmd, args=([sys.executable, "keyword_watcher.py", ser_list],), daemon=True).start()

    def start_telegram_pipeline(self):
        self.save_group_selections()
        selected_group_urls = [g["url"] for g in self.saved_groups if g.get("selected")]
        if not selected_group_urls:
            self.log("[!] Lütfen yukarıdaki Facebook Grup Butonlarından en az 1 tanesini seçin!")
            return
        self.run_telegram_to_targets(",".join(selected_group_urls))

    def run_telegram_to_targets(self, targets_csv):
        tg_url = self.ent_tg_url.get().strip()
        prod_title = self.ent_prod_title.get().strip()
        prod_link = self.ent_prod_link.get().strip()
        aw_flag = "1" if self.var_tg_autowatch.get() else "0"

        selected = self.get_selected_online_nodes()
        if not selected:
            self.log("[!] Paylaşım için seçili ONLINE cihaz yok!")
            return
        ser_list = ",".join([x[2] for x in selected])
        self.log(f"[TELEGRAM POST MOTORU] Görsel + Başlık + Link indiriliyor -> Seçili {len(targets_csv.split(','))} hedefe paylaşılacak...")
        threading.Thread(
            target=self._stream_cmd,
            args=([sys.executable, "telegram_pipeline.py", tg_url, targets_csv, prod_title, prod_link, ser_list, aw_flag],),
            daemon=True
        ).start()

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
        if self.active_proc:
            try: self.active_proc.terminate()
            except: pass
        self.log("[⏹️ DURDURULDU] Aktif arka plan görevi sonlandırıldı.")

    def periodic_ui_sync(self):
        try:
            self.refresh_queue_table()
            self.refresh_watched_list_ui()
        except:
            pass
        self.after(4000, self.periodic_ui_sync)

    def auto_warmup_on_startup(self):
        if not self.var_auto_warm.get():
            return
        db = sqlite3.connect(DB_FILE)
        pending_cnt = db.execute("SELECT COUNT(*) FROM campaign_queue WHERE status LIKE '%PENDING%'").fetchone()[0]
        db.close()
        if pending_cnt == 0 and (not self.active_proc or self.active_proc.poll() is not None):
            self.start_selected_warmup()

if __name__ == "__main__":
    app = AutoFarmModernCommandCenter()
    app.mainloop()
