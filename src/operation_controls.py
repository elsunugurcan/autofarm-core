"""Operation-specific phone selection and explicit engagement allocation."""
import tkinter as tk
import customtkinter as ctk


def engagement_plan(nodes, like_percent, comment_percent):
    rates = []
    for value in (like_percent, comment_percent):
        try:
            rate = float(value)
        except (TypeError, ValueError):
            raise ValueError("Beğeni ve yorum yüzdelerini 0–100 arasında girin.")
        if not 0 <= rate <= 100:
            raise ValueError("Beğeni ve yorum yüzdelerini 0–100 arasında girin.")
        rates.append(rate)
    counts = [int(len(nodes) * rate / 100 + 0.5) for rate in rates]
    plan = []
    for index, node in enumerate(nodes):
        like, comment = index < counts[0], index < counts[1]
        if like or comment:
            mode = "YORUM+BEGENI" if like and comment else "BEGENI" if like else "YORUM"
            plan.append((node, mode))
    return plan, counts


class PhonePicker(ctk.CTkFrame):
    """Compact selector; selections belong to this operation and follow serials."""
    def __init__(self, parent, app, title):
        super().__init__(parent, fg_color="#0b1526", corner_radius=9)
        self.app, self.title = app, title
        self.serials, self.window, self.checks = set(), None, {}
        self.label = ctk.CTkLabel(self, text="", anchor="w", font=("Segoe UI", 11))
        self.label.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        ctk.CTkButton(self, text="Telefonları Seç", width=135, height=30,
                      fg_color="#243e61", command=self.open).pack(side="right", padx=8, pady=6)
        self.refresh()

    def nodes(self):
        return [(i, f"NODE-{i:02d}", w["serial_val"], w["name"].get().strip(), w["persona"].get().strip())
                for i, w in self.app.row_widgets.items()
                if w["serial_val"] and w["serial_val"] in self.serials]

    def refresh(self):
        self.label.configure(text=f"{self.title}  ·  {len(self.nodes())} telefon seçili")
        for i, (var, checkbox) in self.checks.items():
            w = self.app.row_widgets[i]
            serial = w["serial_val"]
            var.set(bool(serial and serial in self.serials))
            checkbox.configure(text=f"NODE-{i:02d}  |  {w['name'].get().strip()}  |  {'ONLINE' if serial else 'OFFLINE'}",
                               state="normal" if serial else "disabled")

    def select_all(self, enabled):
        self.serials = {w["serial_val"] for w in self.app.row_widgets.values() if w["serial_val"]} if enabled else set()
        self.refresh()

    def toggle(self, index):
        serial = self.app.row_widgets[index]["serial_val"]
        if serial:
            if self.checks[index][0].get():
                self.serials.add(serial)
            else:
                self.serials.discard(serial)
        self.refresh()

    def close(self):
        self.checks.clear()
        self.window.destroy()
        self.window = None

    def open(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            return
        self.window = ctk.CTkToplevel(self.app)
        self.window.title(self.title + " — Telefon Seçimi")
        self.window.geometry("760x520")
        self.window.minsize(600, 360)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        ctk.CTkLabel(self.window, text=self.title, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=18, pady=14)
        actions = ctk.CTkFrame(self.window, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=4)
        for text, command in [("Tüm ONLINE", lambda: self.select_all(True)),
                              ("Seçimi Temizle", lambda: self.select_all(False)),
                              ("Cihazları Yenile", self.app.refresh_devices)]:
            ctk.CTkButton(actions, text=text, width=135, command=command).pack(side="left", padx=(0, 8))
        listing = ctk.CTkScrollableFrame(self.window, fg_color="#0b1526")
        listing.pack(fill="both", expand=True, padx=18, pady=12)
        for i in self.app.row_widgets:
            var = tk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(listing, text="", variable=var, command=lambda index=i: self.toggle(index))
            checkbox.pack(anchor="w", padx=8, pady=6)
            self.checks[i] = (var, checkbox)
        ctk.CTkButton(self.window, text="Seçimi Kullan", command=self.close).pack(pady=(0, 14))
        self.refresh()
        self.window.after(100, self.window.lift)
