"""Scrollable work surface: long forms stay reachable on smaller screens."""
import tkinter as tk
import customtkinter as ctk


class Workspace(ctk.CTkFrame):
    def __init__(self, master, minimum_width=1000, **kwargs):
        super().__init__(master, fg_color="#101c2f", corner_radius=14, border_width=1, border_color="#24354d", **kwargs)
        self.minimum_width = minimum_width
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg="#101c2f", highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        self.vertical = ctk.CTkScrollbar(self, command=self.canvas.yview)
        self.vertical.grid(row=0, column=1, sticky="ns", padx=(0, 3), pady=8)
        self.horizontal = ctk.CTkScrollbar(self, orientation="horizontal", command=self.canvas.xview)
        self.horizontal.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 3))
        self.canvas.configure(xscrollcommand=self.horizontal.set, yscrollcommand=self.vertical.set)
        self.body = ctk.CTkFrame(self.canvas, fg_color="transparent", corner_radius=0)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.pending_resize = None
        self.canvas.bind("<Configure>", self.schedule_resize)
        self.body.bind("<Configure>", self.schedule_resize)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.body.bind("<MouseWheel>", self.wheel)

    def wheel(self, event):
        if event.state & 0x1:
            self.canvas.xview_scroll(-int(event.delta / 120), "units")
        else:
            self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def schedule_resize(self, event=None):
        if self.pending_resize is None:
            self.pending_resize = self.after_idle(self.resize_surface)

    def resize_surface(self):
        self.pending_resize = None
        if not self.winfo_exists():
            return
        scale = self._get_widget_scaling()
        width = max(self.canvas.winfo_width(), int(self.minimum_width * scale), self.body.winfo_reqwidth())
        height = max(self.canvas.winfo_height(), self.body.winfo_reqheight())
        self.canvas.itemconfigure(self.window, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def reset_view(self):
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
