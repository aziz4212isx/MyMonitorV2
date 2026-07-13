import os
import sys
import customtkinter as ctk
import psutil
import threading
import time
import platform
import datetime
import collections
import tkinter as tk
from dataclasses import dataclass, field
from typing import List, Dict
from config_manager import ConfigManager
from overlay import CompactOverlay
from gpu_utils import GPUFetcher
from cpu_temp_utils import CPUTempFetcher
import ctypes
import logging
import csv
import traceback

try:
    import keyboard
except:
    pass


logger = logging.getLogger("LightMonitor")
logger.setLevel(logging.DEBUG)
# Always log to stderr so errors are visible in terminal
_sh = logging.StreamHandler()
_sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_sh)
try:
    _log_dir = os.path.join(os.getenv('APPDATA') or os.path.expanduser('~'), 'LightMonitor')
    os.makedirs(_log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(_log_dir, 'error_log.txt'))
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
except Exception:
    pass  # Logging is non-critical; silently skip if unavailable

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_color_by_value(val, metric_type="usage"):
    try:
        v = float(val)
    except:
        return "gray"
    
    if metric_type == "temp":
        if v < 60: return "#2ECC71"  # green
        elif v <= 80: return "#F1C40F"  # yellow
        else: return "#E74C3C"  # red
    elif metric_type == "usage":
        if v < 60: return "#2ECC71"
        elif v <= 85: return "#F1C40F"
        else: return "#E74C3C"
    return "white"

@dataclass
class SystemData:
    uptime: str = "--"
    cpu_use: float = 0.0
    cpu_temp: str = "--"
    cpu_freq: str = "--"
    cpu_cores: List[float] = field(default_factory=list)
    
    gpu_name: str = "--"
    gpu_use: str = "--"
    gpu_temp: str = "--"
    gpu_mem: str = "--"
    gpu_pow: str = "--"
    gpu_pow_limit: str = "--"
    top5_cpu: List[str] = field(default_factory=list)
    top5_ram: List[str] = field(default_factory=list)
    gpu_c_clock: str = "--"
    gpu_m_clock: str = "--"
    gpu_fan: str = "--"
    
    ram_pct: float = 0.0
    ram_used: float = 0.0
    ram_total: float = 0.0
    swap_pct: float = 0.0
    
    disk_data: Dict[str, dict] = field(default_factory=dict)
    
    dl_speed: float = 0.0
    ul_speed: float = 0.0
    net_tot_dl: float = 0.0
    net_tot_ul: float = 0.0

class LightMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("LightMonitor Pro V2")
        self.geometry("600x750")
        self.resizable(True, True)
        try:
            self.iconbitmap(resource_path('icon.ico'))
        except: pass
        
        self.is_topmost = True
        self.attributes("-topmost", self.is_topmost)

        # Header Frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=10, pady=(15, 5))
        
        self.title_label = ctk.CTkLabel(self.header_frame, text="System Monitor", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(side="left")
        
        self.topmost_switch = ctk.CTkSwitch(self.header_frame, text="Always on Top", command=self.toggle_topmost)
        self.topmost_switch.select()
        self.topmost_switch.pack(side="right")
        
        self.hud_btn = ctk.CTkButton(self.header_frame, text="HUD Mode", width=80, command=self.toggle_overlay)

        self.after(5000, self.watchdog_check)
        self._apply_hotkey()

        self.hud_btn.pack(side="right", padx=10)
        
        self.config_mgr = ConfigManager()
        self.overlay_window = None
        
        # Tabs
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        self.tab_overview = self.tabview.add("Overview")
        self.tab_cpu = self.tabview.add("CPU")
        self.tab_gpu = self.tabview.add("GPU")
        self.tab_storage = self.tabview.add("Storage & Network")
        self.tab_settings = self.tabview.add("Settings")

        # History Data (60 points ~ 2 minutes at 2s interval)
        self.hist_cpu = collections.deque([0]*60, maxlen=60)
        self.hist_ram = collections.deque([0]*60, maxlen=60)
        self.hist_gpu = collections.deque([0]*60, maxlen=60)
        
        self.stats = {
            "cpu_sum": 0.0, "cpu_count": 0, "cpu_min": 100.0, "cpu_max": 0.0,
            "gpu_sum": 0.0, "gpu_count": 0, "gpu_min": 100.0, "gpu_max": 0.0
        }
        self.last_top5_time = 0
        self.last_alert_time = 0
        self._proc_cache: dict = {}  # Bug #2 fix: cache Process objects for real cpu_percent delta

        # Thread safety
        self.data_lock = threading.Lock()
        self.gpu_fetcher = GPUFetcher()
        self.cpu_fetcher = CPUTempFetcher()
        
        self._build_overview_ui()
        self._build_cpu_ui()
        self._build_gpu_ui()
        self._build_storage_ui()
        self._build_settings_ui()

        # Initialize tracking vars
        self.last_disk_io = psutil.disk_io_counters(perdisk=True) or {}  # guard: None on some systems
        raw_net = psutil.net_io_counters()
        self.last_net_io = raw_net  # net_io_counters() can also return None
        if self.last_net_io is None:
            # Create a zero-value sentinel using a simple namespace
            import types
            self.last_net_io = types.SimpleNamespace(bytes_recv=0, bytes_sent=0)
        self.last_time = time.time()

        self._window_active = True   # Bug #2/#3: thread-safe flag for UI state
        self._overlay_active = False   # Bug #3: thread-safe flag for overlay state
        self._watchdog_after_id = None

        self.running = True
        self.update_thread = threading.Thread(target=self.fetch_data_loop, daemon=True)
        self.update_thread.start()

        self.protocol("WM_DELETE_WINDOW", self._on_close)  # Bug #6

    def toggle_topmost(self):
        self.is_topmost = bool(self.topmost_switch.get())
        self.attributes("-topmost", self.is_topmost)

    def _on_close(self):
        """Bug #6: Graceful shutdown — stop thread, cancel callbacks, destroy window."""
        self.running = False
        if self._watchdog_after_id:
            try:
                self.after_cancel(self._watchdog_after_id)
            except Exception:
                pass
        if self.overlay_window:
            try:
                self.overlay_window.destroy()
            except Exception:
                pass
        self.destroy()

    def toggle_overlay(self):
        if self.overlay_window is None or not self.overlay_window.winfo_exists():
            self.overlay_window = CompactOverlay(self, self.config_mgr)
            self._overlay_active = True   # Bug #3
            self.hud_btn.configure(text="Close HUD")
        else:
            self.overlay_window.destroy()
            self.overlay_window = None
            self._overlay_active = False  # Bug #3
            self.hud_btn.configure(text="HUD Mode")

    def draw_graph(self, canvas, data, color):
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1 or h <= 1: return
        
        dx = w / 59.0
        points = []
        for i, val in enumerate(data):
            x = i * dx
            y = h - (val / 100.0 * h)
            points.append(x)
            points.append(y)
            
        if len(points) >= 4:
            canvas.create_line(*points, fill=color, width=2)

    def _build_overview_ui(self):
        # CPU
        self.ov_cpu_lbl = ctk.CTkLabel(self.tab_overview, text="CPU Usage: --%", font=ctk.CTkFont(size=14, weight="bold"))
        self.ov_cpu_lbl.pack(anchor="w", padx=10, pady=(10,0))
        self.ov_cpu_canvas = tk.Canvas(self.tab_overview, bg="#2b2b2b", highlightthickness=0, height=60)
        self.ov_cpu_canvas.pack(fill="x", padx=10, pady=5)
        
        # RAM
        self.ov_ram_lbl = ctk.CTkLabel(self.tab_overview, text="RAM Usage: --%", font=ctk.CTkFont(size=14, weight="bold"))
        self.ov_ram_lbl.pack(anchor="w", padx=10, pady=(10,0))
        self.ov_ram_canvas = tk.Canvas(self.tab_overview, bg="#2b2b2b", highlightthickness=0, height=60)
        self.ov_ram_canvas.pack(fill="x", padx=10, pady=5)

        # GPU
        self.ov_gpu_lbl = ctk.CTkLabel(self.tab_overview, text="GPU Usage: --%", font=ctk.CTkFont(size=14, weight="bold"))
        self.ov_gpu_lbl.pack(anchor="w", padx=10, pady=(10,0))
        if self.gpu_fetcher.is_valid():
            self.ov_gpu_canvas = tk.Canvas(self.tab_overview, bg="#2b2b2b", highlightthickness=0, height=60)
            self.ov_gpu_canvas.pack(fill="x", padx=10, pady=5)
        else:
            l = ctk.CTkLabel(self.tab_overview, text="No Supported GPU detected", font=ctk.CTkFont(size=12, slant="italic"))
            l.pack(anchor="w", padx=20, pady=5)

        # Stats & Top 5 Frame
        self.ov_bottom_frame = ctk.CTkFrame(self.tab_overview, fg_color="transparent")
        self.ov_bottom_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.stats_lbl = ctk.CTkLabel(self.ov_bottom_frame, text="Statistics (Session)\nCPU: Min -- | Max -- | Avg --\nGPU: Min -- | Max -- | Avg --", justify="left")
        self.stats_lbl.pack(side="left", anchor="nw")
        
        self.top5_lbl = ctk.CTkLabel(self.ov_bottom_frame, text="Top 5 Processes\n(Disabled in Settings)", justify="left", font=ctk.CTkFont(family="Consolas", size=11))
        self.top5_lbl.pack(side="right", anchor="ne")


    def _build_cpu_ui(self):
        self.cpu_frame = ctk.CTkScrollableFrame(self.tab_cpu)
        self.cpu_frame.pack(fill="both", expand=True)
        
        self.sys_title = ctk.CTkLabel(self.cpu_frame, text="💻 System", font=ctk.CTkFont(size=16, weight="bold"))
        self.sys_title.pack(anchor="w", padx=10, pady=(5, 0))
        self.uptime_lbl = ctk.CTkLabel(self.cpu_frame, text="Uptime: --", font=ctk.CTkFont(size=14))
        self.uptime_lbl.pack(anchor="w", padx=20, pady=(0, 15))

        cpu_name = platform.processor() or "Unknown CPU"
        self.cpu_title = ctk.CTkLabel(self.cpu_frame, text=f"⚙️ CPU: {cpu_name}", font=ctk.CTkFont(size=16, weight="bold"))
        self.cpu_title.pack(anchor="w", padx=10, pady=(5, 0))
        
        self.cpu_usage_lbl = ctk.CTkLabel(self.cpu_frame, text="Total Usage: -- %", font=ctk.CTkFont(size=14))
        self.cpu_usage_lbl.pack(anchor="w", padx=20)
        self.cpu_prog = ctk.CTkProgressBar(self.cpu_frame)
        self.cpu_prog.set(0)
        self.cpu_prog.pack(fill="x", padx=20, pady=(5, 10))
        
        self.cpu_temp_lbl = ctk.CTkLabel(self.cpu_frame, text="Temp: -- °C", font=ctk.CTkFont(size=14))
        self.cpu_temp_lbl.pack(anchor="w", padx=20)
        self.cpu_freq_lbl = ctk.CTkLabel(self.cpu_frame, text="Clock: -- MHz", font=ctk.CTkFont(size=14))
        self.cpu_freq_lbl.pack(anchor="w", padx=20, pady=(0, 10))

        self.cores_grid = ctk.CTkFrame(self.cpu_frame, fg_color="transparent")
        self.cores_grid.pack(fill="x", padx=20, pady=5)
        self.core_labels = []
        num_cores = psutil.cpu_count(logical=True) or 0
        for i in range(num_cores):
            lbl = ctk.CTkLabel(self.cores_grid, text=f"C{i:02d}: --%", font=ctk.CTkFont(size=12))
            lbl.grid(row=i//5, column=i%5, padx=10, pady=2, sticky="w")
            self.core_labels.append(lbl)

    def _build_gpu_ui(self):
        self.gpu_scroll = ctk.CTkScrollableFrame(self.tab_gpu)
        self.gpu_scroll.pack(fill="both", expand=True)

        self.gpu_title = ctk.CTkLabel(self.gpu_scroll, text="🎮 GPU", font=ctk.CTkFont(size=16, weight="bold"))
        self.gpu_title.pack(anchor="w", padx=10, pady=(5, 0))
        
        if not self.gpu_fetcher.is_valid():
            l = ctk.CTkLabel(self.gpu_scroll, text="No Supported GPU detected.", font=ctk.CTkFont(size=12, slant="italic"))
            l.pack(anchor="w", padx=20, pady=5)
            return

        self.gpu_name_lbl = ctk.CTkLabel(self.gpu_scroll, text="Model: --", font=ctk.CTkFont(size=14))
        self.gpu_name_lbl.pack(anchor="w", padx=20, pady=(0,10))
        
        self.gpu_usage_lbl = ctk.CTkLabel(self.gpu_scroll, text="Usage: -- %", font=ctk.CTkFont(size=14))
        self.gpu_usage_lbl.pack(anchor="w", padx=20)
        self.gpu_prog = ctk.CTkProgressBar(self.gpu_scroll)
        self.gpu_prog.set(0)
        self.gpu_prog.pack(fill="x", padx=20, pady=(5, 10))

        self.gpu_temp_lbl = ctk.CTkLabel(self.gpu_scroll, text="Temp: -- °C (Fan: --)", font=ctk.CTkFont(size=14))
        self.gpu_temp_lbl.pack(anchor="w", padx=20)
        self.gpu_mem_lbl = ctk.CTkLabel(self.gpu_scroll, text="VRAM: -- MB", font=ctk.CTkFont(size=14))
        self.gpu_mem_lbl.pack(anchor="w", padx=20)
        self.gpu_power_lbl = ctk.CTkLabel(self.gpu_scroll, text="Power: -- W / -- W", font=ctk.CTkFont(size=14))
        self.gpu_power_lbl.pack(anchor="w", padx=20)
        self.gpu_clock_lbl = ctk.CTkLabel(self.gpu_scroll, text="Core/Mem: -- / -- MHz", font=ctk.CTkFont(size=14))
        self.gpu_clock_lbl.pack(anchor="w", padx=20, pady=(0, 5))

    def _build_storage_ui(self):
        self.st_scroll = ctk.CTkScrollableFrame(self.tab_storage)
        self.st_scroll.pack(fill="both", expand=True)

        self.ram_title = ctk.CTkLabel(self.st_scroll, text="🧠 Memory", font=ctk.CTkFont(size=16, weight="bold"))
        self.ram_title.pack(anchor="w", padx=10, pady=(5, 0))
        
        self.ram_usage_lbl = ctk.CTkLabel(self.st_scroll, text="RAM: -- % ( -- / -- GB )", font=ctk.CTkFont(size=14))
        self.ram_usage_lbl.pack(anchor="w", padx=20)
        self.ram_prog = ctk.CTkProgressBar(self.st_scroll)
        self.ram_prog.set(0)
        self.ram_prog.pack(fill="x", padx=20, pady=(5, 10))

        self.swap_usage_lbl = ctk.CTkLabel(self.st_scroll, text="Swap: -- %", font=ctk.CTkFont(size=14))
        self.swap_usage_lbl.pack(anchor="w", padx=20, pady=(0, 15))

        self.disk_title = ctk.CTkLabel(self.st_scroll, text="💾 Storage & I/O", font=ctk.CTkFont(size=16, weight="bold"))
        self.disk_title.pack(anchor="w", padx=10, pady=(5, 0))
        
        self.disk_widgets = {}
        partitions = psutil.disk_partitions(all=False)
        for p in partitions:
            try:
                psutil.disk_usage(p.mountpoint)
                drive_letter = p.mountpoint.replace('\\', '')
                
                lbl = ctk.CTkLabel(self.st_scroll, text=f"{drive_letter}: -- % (Free: -- GB)", font=ctk.CTkFont(size=14))
                lbl.pack(anchor="w", padx=20)
                prog = ctk.CTkProgressBar(self.st_scroll)
                prog.set(0)
                prog.pack(fill="x", padx=20, pady=(2, 5))
                
                self.disk_widgets[drive_letter] = {"lbl": lbl, "prog": prog, "mount": p.mountpoint}
            except Exception as e:
                print(f"[Disk init] Skipping {p.mountpoint}: {e}")
                
        self.global_io_lbl = ctk.CTkLabel(self.st_scroll, text="Global Disk I/O - Read: -- MB/s | Write: -- MB/s", font=ctk.CTkFont(size=12))
        self.global_io_lbl.pack(anchor="w", padx=20, pady=(5, 15))

        self.net_title = ctk.CTkLabel(self.st_scroll, text="🌐 Network", font=ctk.CTkFont(size=16, weight="bold"))
        self.net_title.pack(anchor="w", padx=10, pady=(5, 0))
        
        self.net_dl_lbl = ctk.CTkLabel(self.st_scroll, text="DL Speed: -- KB/s", font=ctk.CTkFont(size=14))
        self.net_dl_lbl.pack(anchor="w", padx=20)
        self.net_ul_lbl = ctk.CTkLabel(self.st_scroll, text="UL Speed: -- KB/s", font=ctk.CTkFont(size=14))
        self.net_ul_lbl.pack(anchor="w", padx=20)
        self.net_total_lbl = ctk.CTkLabel(self.st_scroll, text="Total: DL -- GB | UL -- GB", font=ctk.CTkFont(size=14))
        self.net_total_lbl.pack(anchor="w", padx=20, pady=(0, 5))
    def _build_settings_ui(self):
        self.set_scroll = ctk.CTkScrollableFrame(self.tab_settings)
        self.set_scroll.pack(fill="both", expand=True)

        # 1. HUD SECTION
        lbl = ctk.CTkLabel(self.set_scroll, text="HUD Overlay Options", font=ctk.CTkFont(size=16, weight="bold"))
        lbl.pack(anchor="w", padx=10, pady=(5, 10))

        self.metric_vars = {}
        available_metrics = ["cpu_usage", "cpu_temp", "cpu_freq", "gpu_usage", "gpu_temp", "vram_usage", "ram_usage", "swap_usage", "net_speed", "disk_io"]
        for p in psutil.disk_partitions(all=False):
            available_metrics.append(f"disk_usage_{p.mountpoint.replace(chr(92), '').replace('/', '')}")

        enabled = self.config_mgr.get_overlay_conf().get("enabled_metrics", [])

        hud_grid = ctk.CTkFrame(self.set_scroll, fg_color="transparent")
        hud_grid.pack(fill="x", padx=20, pady=5)
        for i, m in enumerate(available_metrics):
            var = ctk.BooleanVar(value=(m in enabled))
            self.metric_vars[m] = var
            cb = ctk.CTkCheckBox(hud_grid, text=m, variable=var, command=self._save_settings)
            cb.grid(row=i//3, column=i%3, padx=10, pady=2, sticky="w")

        self.ct_var = ctk.BooleanVar(value=self.config_mgr.get_overlay_conf().get("click_through", False))
        self.ct_cb = ctk.CTkCheckBox(self.set_scroll, text="Click-Through Mode (HUD ignores mouse clicks)", variable=self.ct_var, command=self._save_settings)
        self.ct_cb.pack(anchor="w", padx=20, pady=5)

        self.hud_opac_lbl = ctk.CTkLabel(self.set_scroll, text=f"Background Opacity: {self.config_mgr.get_overlay_conf().get('transparency', 0.85):.2f}")
        self.hud_opac_lbl.pack(anchor="w", padx=20, pady=(5, 0))
        self.hud_opac_slider = ctk.CTkSlider(self.set_scroll, from_=0.1, to=1.0, command=self._update_opacity_lbl)
        self.hud_opac_slider.set(self.config_mgr.get_overlay_conf().get("transparency", 0.85))
        self.hud_opac_slider.pack(fill="x", padx=20, pady=(0, 10))

        # --- HUD CUSTOMIZATION ---
        cust_frame = ctk.CTkFrame(self.set_scroll, fg_color="transparent")
        cust_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(cust_frame, text="Layout Mode:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.hud_layout_var = ctk.StringVar(value=self.config_mgr.get_overlay_conf().get("layout", "RTSS Compact"))
        self.hud_layout_menu = ctk.CTkOptionMenu(cust_frame, values=["Classic (List)", "RTSS Compact"], variable=self.hud_layout_var, command=lambda x: self._save_settings())
        self.hud_layout_menu.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        ctk.CTkLabel(cust_frame, text="Color Theme:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.hud_theme_var = ctk.StringVar(value=self.config_mgr.get_overlay_conf().get("theme", "Cyan"))
        self.hud_theme_menu = ctk.CTkOptionMenu(cust_frame, values=["Cyan", "Razer Green", "Afterburner Orange", "Pink", "White"], variable=self.hud_theme_var, command=lambda x: self._save_settings())
        self.hud_theme_menu.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        
        self.hud_font_lbl = ctk.CTkLabel(cust_frame, text=f"Font Size: {self.config_mgr.get_overlay_conf().get('font_size', 12)}")
        self.hud_font_lbl.grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.hud_font_slider = ctk.CTkSlider(cust_frame, from_=8, to=20, number_of_steps=12, command=self._update_font_lbl)
        self.hud_font_slider.set(self.config_mgr.get_overlay_conf().get("font_size", 12))
        self.hud_font_slider.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        
        # 2. FEATURES SECTION
        feat_conf = self.config_mgr.get_features_conf()
        
        lbl_f = ctk.CTkLabel(self.set_scroll, text="Core Features", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_f.pack(anchor="w", padx=10, pady=(20, 10))

        self.feat_top5_var = ctk.BooleanVar(value=feat_conf.get("top5_process", False))
        ctk.CTkCheckBox(self.set_scroll, text="Show Top 5 Process (CPU/RAM Consumer)", variable=self.feat_top5_var, command=self._save_settings).pack(anchor="w", padx=20, pady=2)

        self.feat_csv_var = ctk.BooleanVar(value=feat_conf.get("csv_logging", False))
        ctk.CTkCheckBox(self.set_scroll, text="Log Data to CSV", variable=self.feat_csv_var, command=self._save_settings).pack(anchor="w", padx=20, pady=2)
        
        self.feat_startup_var = ctk.BooleanVar(value=feat_conf.get("run_on_startup", False))
        ctk.CTkCheckBox(self.set_scroll, text="Run on Windows Startup", variable=self.feat_startup_var, command=self._save_settings).pack(anchor="w", padx=20, pady=2)

        self.feat_hotkey_var = ctk.BooleanVar(value=feat_conf.get("hotkey_enabled", False))
        ctk.CTkCheckBox(self.set_scroll, text="Enable Global Hotkey (Ctrl+Alt+M to toggle HUD)\n*Requires Run As Administrator*", variable=self.feat_hotkey_var, command=self._save_settings).pack(anchor="w", padx=20, pady=(2, 10))


        # 3. ALERTS SECTION
        lbl_a = ctk.CTkLabel(self.set_scroll, text="Alerts & Thresholds", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_a.pack(anchor="w", padx=10, pady=(20, 10))

        self.alert_en_var = ctk.BooleanVar(value=feat_conf.get("alerts_enabled", False))
        ctk.CTkCheckBox(self.set_scroll, text="Enable Windows Notifications & Sound", variable=self.alert_en_var, command=self._save_settings).pack(anchor="w", padx=20, pady=5)

        temp_frame = ctk.CTkFrame(self.set_scroll, fg_color="transparent")
        temp_frame.pack(fill="x", padx=20, pady=2)
        
        ctk.CTkLabel(temp_frame, text="CPU Alert Temp (°C):").pack(side="left")
        self.alert_cpu_entry = ctk.CTkEntry(temp_frame, width=50)
        self.alert_cpu_entry.insert(0, str(feat_conf.get("alert_cpu_temp", 85)))
        self.alert_cpu_entry.pack(side="left", padx=10)
        
        ctk.CTkLabel(temp_frame, text="GPU Alert Temp (°C):").pack(side="left", padx=(20,0))
        self.alert_gpu_entry = ctk.CTkEntry(temp_frame, width=50)
        self.alert_gpu_entry.insert(0, str(feat_conf.get("alert_gpu_temp", 85)))
        self.alert_gpu_entry.pack(side="left", padx=10)

        ctk.CTkButton(self.set_scroll, text="Save Settings", command=self._save_settings, width=120).pack(anchor="w", padx=20, pady=20)

    def _update_font_lbl(self, val):
        val = int(val)
        self.hud_font_lbl.configure(text=f"Font Size: {val}")

    def _update_opacity_lbl(self, val):
        self.hud_opac_lbl.configure(text=f"Background Opacity: {val:.2f}")
        if self.overlay_window and self.overlay_window.winfo_exists():
            self.overlay_window.attributes("-alpha", val)

    def _save_settings(self):
        # Overlay
        conf = self.config_mgr.get_overlay_conf()
        conf["enabled_metrics"] = [m for m, var in self.metric_vars.items() if var.get()]
        conf["click_through"] = self.ct_var.get()
        conf["transparency"] = self.hud_opac_slider.get()

        conf["layout"] = self.hud_layout_var.get()
        conf["theme"] = self.hud_theme_var.get()
        conf["font_size"] = int(self.hud_font_slider.get())

        
        # Features
        feat = self.config_mgr.get_features_conf()
        feat["top5_process"] = self.feat_top5_var.get()
        feat["csv_logging"] = self.feat_csv_var.get()
        feat["run_on_startup"] = self.feat_startup_var.get()
        feat["hotkey_enabled"] = self.feat_hotkey_var.get()
        self._apply_hotkey()
        feat["alerts_enabled"] = self.alert_en_var.get()
        # Bug #7: Validate threshold range 1-150°C
        try:
            cpu_thresh = int(self.alert_cpu_entry.get())
            feat["alert_cpu_temp"] = max(1, min(150, cpu_thresh))
        except ValueError:
            feat["alert_cpu_temp"] = 85  # silently reset to safe default
        try:
            gpu_thresh = int(self.alert_gpu_entry.get())
            feat["alert_gpu_temp"] = max(1, min(150, gpu_thresh))
        except ValueError:
            feat["alert_gpu_temp"] = 85

        self.config_mgr.save_config()
        self._apply_startup_registry(feat["run_on_startup"])
        
        if self.overlay_window and self.overlay_window.winfo_exists():
            self.overlay_window.rebuild_if_needed()


    def _apply_hotkey(self):
        # Bug #13: unhook_all() is too aggressive; use targeted removal
        try:
            import keyboard
            if hasattr(self, '_hotkey_ref') and self._hotkey_ref is not None:
                try:
                    keyboard.remove_hotkey(self._hotkey_ref)
                except Exception:
                    pass
                self._hotkey_ref = None
            if self.config_mgr.get_features_conf().get("hotkey_enabled"):
                self._hotkey_ref = keyboard.add_hotkey('ctrl+alt+m', lambda: self.after(0, self.toggle_overlay))
        except Exception:
            pass

    def watchdog_check(self):
        if not self.running:  # Bug #5: stop scheduling after close
            return
        if time.time() - self.last_time > 15:
            logger.error("[Watchdog] Thread frozen for >15s. Restarting fetch_data_loop...")
            self.running = False
            try:
                self.update_thread.join(timeout=1.0)  # Bug #4: correct name
            except Exception:
                pass
            self.running = True
            self.update_thread = threading.Thread(target=self.fetch_data_loop, daemon=True)
            self.update_thread.start()

        self._watchdog_after_id = self.after(5000, self.watchdog_check)  # Bug #5: save ID

    def _apply_startup_registry(self, enable):
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "LightMonitor"
        exe_path = os.path.abspath(sys.argv[0])
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Registry] {e}")

    def fetch_data_loop(self):
        while self.running:
            d = SystemData()
            try:
                try:
                    bt = datetime.datetime.fromtimestamp(psutil.boot_time())
                    d.uptime = str(datetime.datetime.now() - bt).split('.')[0]
                except Exception as e: logger.error(f"[Uptime] {e}")

                try:
                    d.cpu_use = psutil.cpu_percent(interval=None)
                    d.cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
                except Exception as e: logger.error(f"[CPU Usage] {e}")
                    
                try: 
                    freq = psutil.cpu_freq()
                    d.cpu_freq = str(round(freq.current)) if freq else "N/A"
                except Exception as e: logger.error(f"[CPU Freq] {e}")
                
                # Always fetch all hardware data
                self.cpu_fetcher.fetch(d)

                try:
                    ram = psutil.virtual_memory()
                    d.ram_pct = ram.percent
                    d.ram_used = ram.used / (1024**3)
                    d.ram_total = ram.total / (1024**3)
                    d.swap_pct = psutil.swap_memory().percent
                except Exception as e: logger.error(f"[Memory] {e}")

                if self.gpu_fetcher.is_valid():
                    self.gpu_fetcher.fetch(d)

                with self.data_lock:
                    current_time = time.time()
                    current_net_io = psutil.net_io_counters()  # Note: None possible on some systems handled below
                    if current_net_io is None:
                        # R3-C: net_io_counters can return None on systems with no network adapters
                        current_net_io = self.last_net_io  # reuse last snapshot; speeds stay 0
                    current_disk_io = psutil.disk_io_counters(perdisk=True) or {}
                    time_diff = current_time - self.last_time

                    for letter, widgets in self.disk_widgets.items():
                        try:
                            usage = psutil.disk_usage(widgets["mount"])
                            d.disk_data[letter] = {"pct": usage.percent, "free": usage.free / (1024**3)}
                        except Exception as e:
                            logger.error(f"[Disk Usage {letter}] {e}")
                            d.disk_data[letter] = None  # Explicit marker: drive unreadable → show '--'


                    d_read = d_write = 0.0
                    if time_diff > 10:
                        self.last_net_io = current_net_io
                        self.last_disk_io = current_disk_io
                        self.last_time = current_time
                        time_diff = 0
                    elif time_diff >= 0.1:
                        # Bug #8: only sum drives present in BOTH snapshots to avoid spike on USB insert
                        common_disks = current_disk_io.keys() & self.last_disk_io.keys()
                        total_read_now = sum(current_disk_io[k].read_bytes for k in common_disks)
                        total_write_now = sum(current_disk_io[k].write_bytes for k in common_disks)
                        total_read_last = sum(self.last_disk_io[k].read_bytes for k in common_disks)
                        total_write_last = sum(self.last_disk_io[k].write_bytes for k in common_disks)
                        
                        d_read = max(0.0, (total_read_now - total_read_last) / time_diff / (1024**2))
                        d_write = max(0.0, (total_write_now - total_write_last) / time_diff / (1024**2))

                        d.dl_speed = max(0.0, (current_net_io.bytes_recv - self.last_net_io.bytes_recv) / time_diff / 1024)
                        d.ul_speed = max(0.0, (current_net_io.bytes_sent - self.last_net_io.bytes_sent) / time_diff / 1024)
                    
                    d.disk_data["GLOBAL_IO"] = {"read": d_read, "write": d_write}
                    d.net_tot_dl = current_net_io.bytes_recv / (1024**3)
                    d.net_tot_ul = current_net_io.bytes_sent / (1024**3)

                    self.last_net_io = current_net_io
                    self.last_disk_io = current_disk_io
                    self.last_time = current_time
                    
                    # Update History
                    self.hist_cpu.append(d.cpu_use)
                    self.hist_ram.append(d.ram_pct)
                    try:
                        self.hist_gpu.append(float(d.gpu_use))
                    except:
                        self.hist_gpu.append(0.0)


                # -- FEATURES LOGIC --
                feat = self.config_mgr.get_features_conf()
                
                # 1. Top 5 Process (every ~5 seconds)
                if feat.get("top5_process"):
                    if current_time - self.last_top5_time >= 5:
                        try:
                            # Bug #2 fix: reuse cached Process objects so cpu_percent() has
                            # two time-points and returns real usage (not always 0%)
                            new_cache = {}
                            procs = []
                            for p in psutil.process_iter(['name', 'pid', 'memory_percent']):
                                try:
                                    pid = p.pid
                                    name = p.info['name']
                                    if not name or name == 'System Idle Process':
                                        continue
                                    # Reuse cached object for cpu_percent delta
                                    cached = self._proc_cache.get(pid, p)
                                    cpu_pct = cached.cpu_percent(interval=None)
                                    mem_pct = p.info['memory_percent'] or 0.0
                                    procs.append({'name': name, 'cpu_percent': cpu_pct, 'memory_percent': mem_pct})
                                    new_cache[pid] = cached
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass
                            self._proc_cache = new_cache
                            top_cpu = sorted(procs, key=lambda x: x['cpu_percent'], reverse=True)[:5]
                            d.top5_cpu = [f"{p['name'][:15]}: {p['cpu_percent']:.1f}%" for p in top_cpu]
                            top_ram = sorted(procs, key=lambda x: x['memory_percent'], reverse=True)[:5]
                            d.top5_ram = [f"{p['name'][:15]}: {p['memory_percent']:.1f}%" for p in top_ram]
                        except Exception as e:
                            logger.error(f"[Top5] {e}")
                        self.last_top5_time = current_time

                # 2. CSV Logging
                if feat.get("csv_logging"):
                    try:
                        csv_path = os.path.join(self.config_mgr.app_dir, "log.csv")
                        # R3-E: Atomic open with 'a' avoids TOCTOU; write header only if file is empty
                        with open(csv_path, "a", newline='') as f:
                            write_header = f.tell() == 0
                            writer = csv.writer(f)
                            if write_header:
                                writer.writerow(["Time", "CPU_Use", "CPU_Temp", "GPU_Use", "GPU_Temp", "RAM_Use"])
                            writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), d.cpu_use, d.cpu_temp, d.gpu_use, d.gpu_temp, d.ram_pct])
                    except Exception as e:
                        logger.error(f"[CSV Log] {e}")
                        
                # R3-D: Guard against scheduling UI update after window closes
                if self.running:
                    self.after(0, self.update_ui, d)

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"[Main Loop] CRASH:\n{tb}")
                # Show error in UI so user can see it without terminal
                try:
                    self.after(0, self.stats_lbl.configure,
                               {"text": f"[ERROR] Loop crash:\n{type(e).__name__}: {e}\nCek error_log.txt"})
                except Exception:
                    pass
            
            time.sleep(2) 

    def update_ui(self, d: SystemData):
        # COLORS

        # Stats Update
        self.stats["cpu_sum"] += d.cpu_use
        self.stats["cpu_count"] += 1
        if d.cpu_use < self.stats["cpu_min"]: self.stats["cpu_min"] = d.cpu_use
        if d.cpu_use > self.stats["cpu_max"]: self.stats["cpu_max"] = d.cpu_use
        
        try:
            gu = float(d.gpu_use)
            self.stats["gpu_sum"] += gu
            self.stats["gpu_count"] += 1
            if gu < self.stats["gpu_min"]: self.stats["gpu_min"] = gu
            if gu > self.stats["gpu_max"]: self.stats["gpu_max"] = gu
        except: pass
        
        c_avg = self.stats["cpu_sum"] / self.stats["cpu_count"]
        g_avg = (self.stats["gpu_sum"] / self.stats["gpu_count"]) if self.stats["gpu_count"] > 0 else 0.0
        
        self.stats_lbl.configure(text=f"Statistics (Session)\nCPU: Min {self.stats['cpu_min']}% | Max {self.stats['cpu_max']}% | Avg {c_avg:.1f}%\nGPU: Min {self.stats['gpu_min']}% | Max {self.stats['gpu_max']}% | Avg {g_avg:.1f}%")

        feat = self.config_mgr.get_features_conf()
        if feat.get("top5_process"):
            txt = "Top 5 CPU:\n" + "\n".join(d.top5_cpu) + "\n\nTop 5 RAM:\n" + "\n".join(d.top5_ram)
            self.top5_lbl.configure(text=txt)
        else:
            self.top5_lbl.configure(text="Top 5 Processes\n(Disabled in Settings)")

        # Alerts
        if feat.get("alerts_enabled"):
            now = time.time()
            if now - self.last_alert_time >= 60: # Cooldown 60s
                try:
                    cpu_t = float(d.cpu_temp)
                    if cpu_t >= feat.get("alert_cpu_temp", 85):
                        self._trigger_alert("CPU", cpu_t)
                        self.last_alert_time = now
                except: pass
                try:
                    gpu_t = float(d.gpu_temp)
                    if gpu_t >= feat.get("alert_gpu_temp", 85):
                        self._trigger_alert("GPU", gpu_t)
                        self.last_alert_time = now
                except: pass

        c_cpu = get_color_by_value(d.cpu_use, "usage")
        t_cpu = get_color_by_value(d.cpu_temp, "temp")
        c_ram = get_color_by_value(d.ram_pct, "usage")
        c_gpu = get_color_by_value(d.gpu_use, "usage")
        t_gpu = get_color_by_value(d.gpu_temp, "temp")

        # OVERVIEW TAB
        self.ov_cpu_lbl.configure(text=f"CPU Usage: {d.cpu_use}%", text_color=c_cpu)
        self.draw_graph(self.ov_cpu_canvas, self.hist_cpu, c_cpu)
        
        self.ov_ram_lbl.configure(text=f"RAM Usage: {d.ram_pct}%", text_color=c_ram)
        self.draw_graph(self.ov_ram_canvas, self.hist_ram, c_ram)

        if self.gpu_fetcher.is_valid():
            self.ov_gpu_lbl.configure(text=f"GPU Usage: {d.gpu_use}%", text_color=c_gpu)
            self.draw_graph(self.ov_gpu_canvas, self.hist_gpu, c_gpu)

        # CPU TAB
        self.uptime_lbl.configure(text=f"Uptime: {d.uptime}")
        self.cpu_usage_lbl.configure(text=f"Total Usage: {d.cpu_use}%", text_color=c_cpu)
        self.cpu_prog.set(d.cpu_use / 100.0)
        self.cpu_prog.configure(progress_color=c_cpu)
        self.cpu_temp_lbl.configure(text=f"Temp: {d.cpu_temp} °C", text_color=t_cpu)
        self.cpu_freq_lbl.configure(text=f"Clock: {d.cpu_freq} MHz")
        
        for i, core_val in enumerate(d.cpu_cores):
            if i < len(self.core_labels):
                self.core_labels[i].configure(text=f"C{i:02d}: {core_val}%", text_color=get_color_by_value(core_val, "usage"))

        # GPU TAB
        if self.gpu_fetcher.is_valid() and d.gpu_name != "--":
            self.gpu_name_lbl.configure(text=f"Model: {d.gpu_name}")
            self.gpu_usage_lbl.configure(text=f"Usage: {d.gpu_use}%", text_color=c_gpu)
            try:
                self.gpu_prog.set(float(d.gpu_use) / 100.0)
                self.gpu_prog.configure(progress_color=c_gpu)
            except: pass
            
            fan_str = d.gpu_fan + "%" if "N/A" not in d.gpu_fan else "N/A"
            self.gpu_temp_lbl.configure(text=f"Temp: {d.gpu_temp} °C (Fan: {fan_str})", text_color=t_gpu)
            self.gpu_mem_lbl.configure(text=f"VRAM: {d.gpu_mem} MB")
            self.gpu_power_lbl.configure(text=f"Power: {d.gpu_pow} W / {d.gpu_pow_limit} W")
            self.gpu_clock_lbl.configure(text=f"Core/Mem: {d.gpu_c_clock} / {d.gpu_m_clock} MHz")
        
        # STORAGE TAB
        self.ram_usage_lbl.configure(text=f"RAM: {d.ram_pct}% ({d.ram_used:.1f} / {d.ram_total:.1f} GB)", text_color=c_ram)
        self.ram_prog.set(d.ram_pct / 100.0)
        self.ram_prog.configure(progress_color=c_ram)
        self.swap_usage_lbl.configure(text=f"Swap (Pagefile): {d.swap_pct}%", text_color=get_color_by_value(d.swap_pct, "usage"))

        for letter, w in self.disk_widgets.items():
            if letter in d.disk_data:
                v = d.disk_data[letter]
                if v is None:
                    # Drive unreadable — show '--' and reset bar
                    w["lbl"].configure(text=f"{letter}: -- (tidak terbaca)", text_color="gray")
                    w["prog"].set(0)
                    w["prog"].configure(progress_color="gray")
                else:
                    c_disk = get_color_by_value(v['pct'], "usage")
                    w["lbl"].configure(text=f"{letter}: {v['pct']}% (Free: {v['free']:.1f} GB)", text_color=c_disk)
                    w["prog"].set(v['pct'] / 100.0)
                    w["prog"].configure(progress_color=c_disk)
                
        if "GLOBAL_IO" in d.disk_data:
            g_io = d.disk_data["GLOBAL_IO"]
            self.global_io_lbl.configure(text=f"Global Disk I/O - Read: {g_io['read']:.1f} MB/s | Write: {g_io['write']:.1f} MB/s")

        dl_str = f"{d.dl_speed:.1f} KB/s" if d.dl_speed < 1024 else f"{d.dl_speed/1024:.2f} MB/s"
        ul_str = f"{d.ul_speed:.1f} KB/s" if d.ul_speed < 1024 else f"{d.ul_speed/1024:.2f} MB/s"
        
        self.net_dl_lbl.configure(text=f"DL Speed: {dl_str}")
        self.net_ul_lbl.configure(text=f"UL Speed: {ul_str}")
        self.net_total_lbl.configure(text=f"Total: DL {d.net_tot_dl:.1f} GB | UL {d.net_tot_ul:.1f} GB")
        
        if self.overlay_window and self.overlay_window.winfo_exists():
            self.overlay_window.update_data(d)


    def _trigger_alert(self, hw, temp):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except: pass
        tl = tk.Toplevel(self)
        tl.title("Warning!")
        tl.geometry("250x100")
        tl.attributes("-topmost", True)
        ctk.CTkLabel(tl, text=f"🔥 {hw} Overheating!\nTemp: {temp}°C", text_color="red", font=ctk.CTkFont(size=16, weight="bold")).pack(expand=True)
        tl.after(5000, tl.destroy)

if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = LightMonitorApp()
    app.mainloop()
