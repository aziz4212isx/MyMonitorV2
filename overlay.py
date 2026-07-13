import customtkinter as ctk
import ctypes
import platform

class CompactOverlay(ctk.CTkToplevel):
    def __init__(self, master, config_mgr):
        super().__init__(master)
        self.config_mgr = config_mgr
        self.conf = self.config_mgr.get_overlay_conf()
        
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", self.conf.get("transparency", 0.85))
        
        pos = self.conf.get("position", {"x": 100, "y": 100})
        x = max(0, min(pos.get("x", 100), self.winfo_screenwidth() - 100))
        y = max(0, min(pos.get("y", 100), self.winfo_screenheight() - 50))
        self.geometry(f"+{x}+{y}")
        
        self.configure(fg_color="#121212")
        
        self.main_frame = ctk.CTkFrame(self, corner_radius=12, fg_color="#1a1a1a")
        self.main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        self._drag_start_x = 0
        self._drag_start_y = 0
        self.bind_drag(self.main_frame)
        self.metric_labels = {}
        
        if platform.system() == "Windows":
            self.after(10, self.apply_window_styles)
        
        self.build_ui()

    def build_ui(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        self.metric_labels.clear()
        self.metric_buffer = {}  # Bug #10: always initialize before any early return

        metrics = self.conf.get("enabled_metrics", [])
        if not metrics:
            msg = ctk.CTkLabel(self.main_frame, text="No metrics selected", font=ctk.CTkFont(size=10, slant="italic"))
            msg.pack(padx=10, pady=10)
            self.geometry("160x50")
            return
            
        layout = self.conf.get("layout", "RTSS Compact")
        theme_name = self.conf.get("theme", "Cyan")
        theme_colors = {
            "Cyan": "#00E5FF",
            "Razer Green": "#00FF00",
            "Afterburner Orange": "#FF7F00",
            "Pink": "#FF00FF",
            "White": "#FFFFFF"
        }
        self.value_color = theme_colors.get(theme_name, "#00E5FF")
        self.f_size = self.conf.get("font_size", 12)
        self.font_main = ctk.CTkFont(family="Consolas", size=self.f_size, weight="bold")
        
        self.metric_buffer = {m: "--" for m in metrics}
        
        if layout == "RTSS Compact":
            self._build_rtss_layout(metrics)
        else:
            self._build_classic_layout(metrics)

    def _build_rtss_layout(self, metrics):
        groups = {"CPU": [], "GPU": [], "RAM": [], "DSK": [], "NET": []}
        for m in metrics:
            if m.startswith("cpu_"): groups["CPU"].append(m)
            elif m.startswith("gpu_") or m == "vram_usage": groups["GPU"].append(m)
            elif m in ["ram_usage", "swap_usage"]: groups["RAM"].append(m)
            elif m.startswith("disk_usage_") or m == "disk_io": groups["DSK"].append(m)
            elif m == "net_speed": groups["NET"].append(m)
        
        self.groups = groups
        self.group_labels = {}
        
        for g_name, g_metrics in groups.items():
            if not g_metrics: continue
            
            row = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)
            
            lbl = ctk.CTkLabel(row, text=g_name, font=self.font_main, text_color="#aaaaaa", width=40, anchor="w")
            lbl.pack(side="left")
            
            val = ctk.CTkLabel(row, text="...", font=self.font_main, text_color=self.value_color, justify="left")
            val.pack(side="left", padx=(10, 0))
            
            self.group_labels[g_name] = val
            self.bind_drag(row); self.bind_drag(lbl); self.bind_drag(val)
            
        h = 10 + (len([g for g in groups.values() if g]) * (self.f_size + 16))
        # Bug #5 fix: wider multiplier + minimum to prevent text overflow
        w = max(200, self.f_size * 32)
        self.geometry(f"{w}x{h}")

    def _build_classic_layout(self, metrics):
        labels_map = {
            "cpu_usage": "CPU", "cpu_temp": "CPU Tmp", "cpu_freq": "CPU Clk",
            "gpu_usage": "GPU", "gpu_temp": "GPU Tmp", "vram_usage": "VRAM",
            "ram_usage": "RAM", "swap_usage": "Swap", "net_speed": "Net DL/UL", "disk_io": "Disk I/O"
        }
        
        for m in metrics:
            display_name = labels_map.get(m, m)
            if m.startswith("disk_usage_"):
                display_name = f"Disk {m.split('_')[-1]}"
                
            row = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=self.f_size + 10)
            row.pack(fill="x", padx=8, pady=2)
            row.pack_propagate(False)
            
            lbl = ctk.CTkLabel(row, text=display_name, font=self.font_main, text_color="#aaaaaa")
            lbl.pack(side="left", padx=5)
            
            val = ctk.CTkLabel(row, text="--", font=self.font_main, text_color=self.value_color)
            val.pack(side="right", padx=5)
            
            self.metric_labels[m] = val
            self.bind_drag(row); self.bind_drag(lbl); self.bind_drag(val)
            
        h = 10 + (len(metrics) * (self.f_size + 14))
        self.geometry(f"{self.f_size * 18}x{h}")

    def bind_drag(self, widget):
        widget.bind("<Button-1>", self.start_move)
        widget.bind("<B1-Motion>", self.do_move)
        widget.bind("<ButtonRelease-1>", self.stop_move)

    def start_move(self, event):
        if self.conf.get("click_through", False): return
        self._drag_start_x = event.x_root - self.winfo_x()
        self._drag_start_y = event.y_root - self.winfo_y()

    def do_move(self, event):
        if self.conf.get("click_through", False): return
        x = event.x_root - self._drag_start_x
        y = event.y_root - self._drag_start_y
        self.geometry(f"+{x}+{y}")

    def stop_move(self, event):
        if self.conf.get("click_through", False): return
        self.conf["position"] = {"x": self.winfo_x(), "y": self.winfo_y()}
        self.config_mgr.save_config()
        
    def apply_window_styles(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ex_style |= 0x00000080
            if self.conf.get("click_through", False):
                ex_style |= 0x00080000 | 0x00000020
            else:
                ex_style &= ~0x00000020
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style)
        except: pass

    def rebuild_if_needed(self):
        self.conf = self.config_mgr.get_overlay_conf()
        self.attributes("-alpha", self.conf.get("transparency", 0.85))
        self.apply_window_styles()
        self.build_ui()

    def update_data(self, d):
        self.metric_buffer["cpu_usage"] = f"{d.cpu_use}%"
        self.metric_buffer["cpu_temp"] = f"{d.cpu_temp}°C"
        self.metric_buffer["cpu_freq"] = f"{d.cpu_freq}MHz"
        self.metric_buffer["gpu_usage"] = f"{d.gpu_use}%" if d.gpu_use != "--" else "N/A"
        self.metric_buffer["gpu_temp"] = f"{d.gpu_temp}°C" if d.gpu_temp != "--" else "N/A"
        self.metric_buffer["vram_usage"] = f"{d.gpu_mem}MB" if d.gpu_mem != "--" else "N/A"
        self.metric_buffer["ram_usage"] = f"{d.ram_pct}%"
        self.metric_buffer["swap_usage"] = f"{d.swap_pct}%"
        self.metric_buffer["net_speed"] = f"{d.dl_speed:.0f}/{d.ul_speed:.0f} KB/s"
        
        if "GLOBAL_IO" in d.disk_data:
            gio = d.disk_data["GLOBAL_IO"]
            self.metric_buffer["disk_io"] = f"{gio['read']:.1f}/{gio['write']:.1f} MB/s"
            
        for key, val in d.disk_data.items():
            if key != "GLOBAL_IO":
                # Bug #4 fix: val can be None when drive is unreadable
                if val is None:
                    self.metric_buffer[f"disk_usage_{key}"] = "--"
                else:
                    self.metric_buffer[f"disk_usage_{key}"] = f"{val['pct']}%"

        layout = self.conf.get("layout", "RTSS Compact")
        if layout == "RTSS Compact":
            for g_name, g_metrics in getattr(self, "groups", {}).items():
                if g_metrics:
                    s = "   ".join(self.metric_buffer.get(m, "--") for m in g_metrics)
                    if g_name in self.group_labels:
                        self.group_labels[g_name].configure(text=s)
        else:
            for key, val_str in self.metric_buffer.items():
                if key in getattr(self, "metric_labels", {}):
                    self.metric_labels[key].configure(text=val_str)
