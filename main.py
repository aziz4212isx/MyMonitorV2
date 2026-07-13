import sys
import os
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QHBoxLayout, QGridLayout, QPushButton
from PySide6.QtCore import Qt
import pyqtgraph as pg
import collections

# Backend imports
from config_manager import ConfigManager
from cpu_temp_utils import CPUTempFetcher
from gpu_utils import GPUFetcher

from data_worker import SystemData, DataWorker, get_color_by_value
from overlay_qt import CompactOverlay
from PySide6.QtCore import QThread, QTimer

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LightMonitor Pro V2 (Qt)")
        self.resize(600, 750)
        
        # Load stylesheet
        try:
            with open("style.qss", "r") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Error loading QSS: {e}")

        # Central Widget & Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Title & HUD Toggle
        header_layout = QHBoxLayout()
        title_lbl = QLabel("System Monitor")
        title_lbl.setObjectName("TitleLabel")
        header_layout.addWidget(title_lbl)
        
        self.hud_btn = QPushButton("HUD Mode")
        self.hud_btn.setFixedWidth(100)
        self.hud_btn.clicked.connect(self.toggle_overlay)
        header_layout.addWidget(self.hud_btn, alignment=Qt.AlignRight)
        
        layout.addLayout(header_layout)

        # Tab Widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # 5 Tabs
        self.tab_overview = QWidget()
        self.tab_cpu = QWidget()
        self.tab_gpu = QWidget()
        self.tab_storage = QWidget()
        self.tab_settings = QWidget()
        
        self.tabs.addTab(self.tab_overview, "Overview")
        self.tabs.addTab(self.tab_cpu, "CPU")
        self.tabs.addTab(self.tab_gpu, "GPU")
        self.tabs.addTab(self.tab_storage, "Storage & Network")
        self.tabs.addTab(self.tab_settings, "Settings")

        # Placeholder removal
        # Tabs are setup after DataWorker inits

        # Test backend imports
        self.config_mgr = ConfigManager()
        
        # History Data (60 points ~ 2 mins)
        self.hist_cpu = collections.deque([0]*60, maxlen=60)
        self.hist_ram = collections.deque([0]*60, maxlen=60)
        self.hist_gpu = collections.deque([0]*60, maxlen=60)

        # Overlay
        self.overlay = None

        # Setup DataWorker and QThread
        self.worker_thread = QThread()
        self.worker = DataWorker(self.config_mgr)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run_loop)
        self.worker.data_updated.connect(self.on_data_updated)
        self.worker_thread.start()
        
        # Setup Tabs (must be after DataWorker is initialized)
        self.setup_overview_tab()
        self.setup_cpu_tab()
        self.setup_gpu_tab()
        self.setup_storage_tab()
        self.setup_settings_tab()
        
        # System Tray and Hotkey
        self.setup_tray()
        self._hotkey_ref = None
        self.apply_hotkey()
        self.last_alert_time = 0
        
        print("Backend initialized successfully with QThread")

    def toggle_overlay(self):
        if self.overlay and self.overlay.isVisible():
            self.overlay.close()
            self.overlay = None
        else:
            self.overlay = CompactOverlay(self.config_mgr)
            self.overlay.show()

    def setup_tray(self):
        import logging
        from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication, QStyle
        from PySide6.QtGui import QIcon
        import sys, os
        
        # Setup logging for tray
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tray_debug.log")
        logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logger = logging.getLogger("TraySetup")
        
        try:
            logger.info("Starting setup_tray...")
            
            # CEK #4: isSystemTrayAvailable
            if not QSystemTrayIcon.isSystemTrayAvailable():
                logger.error("System tray NOT available on this system! Icon will not show.")
            else:
                logger.info("System tray is available.")

            def resource_path(relative_path):
                try:
                    base_path = sys._MEIPASS
                except Exception:
                    base_path = os.path.abspath(".")
                return os.path.join(base_path, relative_path)
            
            # CEK #1 & #7: Object Lifetime & Threading (main thread, self parent)
            self.tray_icon = QSystemTrayIcon(self)
            
            # CEK #2: ICON KOSONG / INVALID
            icon_path = resource_path("icon.png")
            logger.info(f"Attempting to load icon from: {icon_path}")
            my_icon = QIcon(icon_path)
            
            if my_icon.isNull():
                logger.error("Primary icon failed to load or is invalid! Attempting fallback...")
                my_icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                if my_icon.isNull():
                    logger.error("Fallback icon ALSO failed to load! Icon will be blank/invisible.")
                else:
                    logger.info("Fallback icon loaded successfully.")
            else:
                logger.info("Primary icon loaded successfully.")
                
            self.tray_icon.setIcon(my_icon)
            
            # CEK #1: QMenu local var gets garbage collected! (MUST use self and parent)
            self.tray_menu = QMenu(self)
            
            self.show_action = self.tray_menu.addAction("Show Dashboard")
            self.show_action.triggered.connect(self.showNormal)
            
            self.hud_action = self.tray_menu.addAction("Toggle HUD")
            self.hud_action.triggered.connect(self.toggle_overlay)
            
            self.quit_action = self.tray_menu.addAction("Exit")
            self.quit_action.triggered.connect(self.close_app)
            
            self.tray_icon.setContextMenu(self.tray_menu)
            logger.info("Context menu attached.")
            
            # CEK #3: show() called properly
            self.tray_icon.show()
            logger.info("tray_icon.show() executed.")
            
        except Exception as e:
            # CEK #5: Exception Senyap
            logger.error(f"[Tray] Setup failed with exception: {str(e)}")

    def apply_hotkey(self):
        try:
            import keyboard
            if self._hotkey_ref:
                try: keyboard.remove_hotkey(self._hotkey_ref)
                except: pass
                self._hotkey_ref = None
                
            if self.config_mgr.get_features_conf().get("hotkey_enabled", False):
                # Trigger toggle_overlay safely in main thread using QTimer
                self._hotkey_ref = keyboard.add_hotkey('ctrl+alt+m', lambda: QTimer.singleShot(0, self.toggle_overlay))
        except Exception:
            pass

    def close_app(self):
        self.worker.running = False
        self.worker_thread.quit()
        self.worker_thread.wait(1000)
        if self.overlay:
            self.overlay.close()
        QApplication.quit()

    def closeEvent(self, event):
        # Minimize to tray instead of closing
        event.ignore()
        self.hide()

    def setup_overview_tab(self):
        layout = QVBoxLayout(self.tab_overview)
        
        # Stats Label
        self.stats_lbl = QLabel("Statistics (Session)")
        self.stats_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.stats_lbl)

        # Top 5 label
        self.top5_lbl = QLabel("Top 5 Processes")
        self.top5_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.top5_lbl)

        # Graphs Layout
        graphs_layout = QGridLayout()
        layout.addLayout(graphs_layout)

        # CPU Graph
        self.ov_cpu_lbl = QLabel("CPU Usage: 0%")
        graphs_layout.addWidget(self.ov_cpu_lbl, 0, 0)
        self.cpu_plot = pg.PlotWidget()
        self.cpu_plot.setYRange(0, 100)
        self.cpu_plot.setBackground('#1a1a1a')
        self.cpu_curve = self.cpu_plot.plot(pen=pg.mkPen('#00E5FF', width=2))
        graphs_layout.addWidget(self.cpu_plot, 1, 0)

        # RAM Graph
        self.ov_ram_lbl = QLabel("RAM Usage: 0%")
        graphs_layout.addWidget(self.ov_ram_lbl, 0, 1)
        self.ram_plot = pg.PlotWidget()
        self.ram_plot.setYRange(0, 100)
        self.ram_plot.setBackground('#1a1a1a')
        self.ram_curve = self.ram_plot.plot(pen=pg.mkPen('#2ECC71', width=2))
        graphs_layout.addWidget(self.ram_plot, 1, 1)

        # GPU Graph
        self.ov_gpu_lbl = QLabel("GPU Usage: 0%")
        graphs_layout.addWidget(self.ov_gpu_lbl, 2, 0)
        self.gpu_plot = pg.PlotWidget()
        self.gpu_plot.setYRange(0, 100)
        self.gpu_plot.setBackground('#1a1a1a')
        self.gpu_curve = self.gpu_plot.plot(pen=pg.mkPen('#F1C40F', width=2))
        graphs_layout.addWidget(self.gpu_plot, 3, 0)


    def setup_cpu_tab(self):
        layout = QVBoxLayout(self.tab_cpu)
        
        import platform
        cpu_name = platform.processor() or "Unknown CPU"
        self.cpu_name_lbl = QLabel(f"Processor: {cpu_name}")
        self.cpu_name_lbl.setObjectName("HeaderLabel")
        layout.addWidget(self.cpu_name_lbl)
        
        info_layout = QHBoxLayout()
        self.cpu_temp_lbl = QLabel("Temp: -- °C")
        self.cpu_clock_lbl = QLabel("Clock: -- MHz")
        self.cpu_pow_lbl = QLabel("Power: -- W")
        info_layout.addWidget(self.cpu_temp_lbl)
        info_layout.addWidget(self.cpu_clock_lbl)
        info_layout.addWidget(self.cpu_pow_lbl)
        layout.addLayout(info_layout)
        
        self.cpu_usage_lbl = QLabel("Total Usage: 0%")
        layout.addWidget(self.cpu_usage_lbl)
        
        from PySide6.QtWidgets import QProgressBar
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100)
        self.cpu_progress.setTextVisible(False)
        self.cpu_progress.setFixedHeight(10)
        layout.addWidget(self.cpu_progress)
        
        # Cores grid
        self.cpu_cores_layout = QGridLayout()
        layout.addLayout(self.cpu_cores_layout)
        self.core_labels = []
        layout.addStretch()

    def setup_gpu_tab(self):
        layout = QVBoxLayout(self.tab_gpu)
        if not self.worker.gpu_fetcher.is_valid():
            lbl = QLabel("No Dedicated GPU Detected or Supported.")
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)
            return

        self.gpu_name_lbl = QLabel("Graphics: --")
        self.gpu_name_lbl.setObjectName("HeaderLabel")
        layout.addWidget(self.gpu_name_lbl)

        grid = QGridLayout()
        layout.addLayout(grid)
        
        self.gpu_usage_lbl = QLabel("Usage: --")
        self.gpu_temp_lbl = QLabel("Temp: --")
        self.gpu_mem_lbl = QLabel("VRAM: --")
        self.gpu_pow_lbl = QLabel("Power: --")
        
        self.gpu_cclock_lbl = QLabel("Core Clock: --")
        self.gpu_mclock_lbl = QLabel("Mem Clock: --")
        self.gpu_fan_lbl = QLabel("Fan Speed: --")

        grid.addWidget(self.gpu_usage_lbl, 0, 0)
        grid.addWidget(self.gpu_temp_lbl, 0, 1)
        grid.addWidget(self.gpu_mem_lbl, 1, 0)
        grid.addWidget(self.gpu_pow_lbl, 1, 1)
        grid.addWidget(self.gpu_cclock_lbl, 2, 0)
        grid.addWidget(self.gpu_mclock_lbl, 2, 1)
        grid.addWidget(self.gpu_fan_lbl, 3, 0)
        layout.addStretch()

    def setup_storage_tab(self):
        layout = QVBoxLayout(self.tab_storage)
        
        # Disk IO
        self.disk_io_lbl = QLabel("Disk I/O: Read 0 MB/s | Write 0 MB/s")
        self.disk_io_lbl.setObjectName("HeaderLabel")
        layout.addWidget(self.disk_io_lbl)
        
        self.disks_layout = QVBoxLayout()
        layout.addLayout(self.disks_layout)
        self.disk_widgets = {}
        
        # Network
        self.net_lbl = QLabel("Network: DL 0 KB/s | UL 0 KB/s")
        self.net_lbl.setObjectName("HeaderLabel")
        layout.addWidget(self.net_lbl)
        
        self.net_tot_lbl = QLabel("Total: DL 0 GB | UL 0 GB")
        layout.addWidget(self.net_tot_lbl)
        
        layout.addStretch()

    def setup_settings_tab(self):
        from PySide6.QtWidgets import QScrollArea, QCheckBox, QSlider, QComboBox, QLineEdit, QPushButton, QFormLayout, QGridLayout, QGroupBox
        import string
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        
        layout = QVBoxLayout(self.tab_settings)
        layout.addWidget(scroll)
        
        form = QFormLayout(content)
        
        # Overlay config
        ov_conf = self.config_mgr.get_overlay_conf()
        
        # Metrics Group
        metrics_group = QGroupBox("HUD Metrics")
        metrics_grid = QGridLayout(metrics_group)
        self.metric_checkboxes = {}
        
        available_metrics = [
            "cpu_usage", "cpu_temp", "cpu_freq", "cpu_power",
            "gpu_usage", "gpu_temp", "vram_usage", "gpu_power",
            "ram_usage", "swap_usage", "net_speed",
            "disk_io", "disk_usage_C:"
        ]
        
        enabled_list = ov_conf.get("enabled_metrics", [])
        
        for i, m in enumerate(available_metrics):
            cb = QCheckBox(m)
            cb.setChecked(m in enabled_list)
            self.metric_checkboxes[m] = cb
            metrics_grid.addWidget(cb, i % 4, i // 4)
            
        form.addRow(metrics_group)
        
        self.set_ct = QCheckBox("Click-Through Mode")
        self.set_ct.setChecked(ov_conf.get("click_through", False))
        form.addRow(self.set_ct)
        
        self.set_ghost = QCheckBox("Ghost Mode (Full Transparent Background)")
        self.set_ghost.setChecked(ov_conf.get("ghost_mode", False))
        form.addRow(self.set_ghost)
        
        self.set_opac = QSlider(Qt.Horizontal)
        self.set_opac.setRange(10, 100)
        self.set_opac.setValue(int(ov_conf.get("transparency", 0.85) * 100))
        self.set_opac_lbl = QLabel(f"HUD Opacity: {self.set_opac.value()}%")
        self.set_opac.valueChanged.connect(lambda v: self.set_opac_lbl.setText(f"HUD Opacity: {v}%"))
        form.addRow(self.set_opac_lbl, self.set_opac)
        
        self.set_font = QSlider(Qt.Horizontal)
        self.set_font.setRange(8, 20)
        self.set_font.setValue(ov_conf.get("font_size", 12))
        self.set_font_lbl = QLabel(f"HUD Font Size: {self.set_font.value()}px")
        self.set_font.valueChanged.connect(lambda v: self.set_font_lbl.setText(f"HUD Font Size: {v}px"))
        form.addRow(self.set_font_lbl, self.set_font)
        
        self.set_layout = QComboBox()
        self.set_layout.addItems(["Classic (List)", "RTSS Compact", "Horizontal Bar"])
        self.set_layout.setCurrentText(ov_conf.get("layout", "RTSS Compact"))
        form.addRow("HUD Layout:", self.set_layout)
        
        self.set_theme = QComboBox()
        self.set_theme.addItems(["Cyan", "Razer Green", "Afterburner Orange", "Pink", "White"])
        self.set_theme.setCurrentText(ov_conf.get("theme", "Cyan"))
        form.addRow("HUD Theme:", self.set_theme)
        
        # Features config
        feat_conf = self.config_mgr.get_features_conf()
        
        self.set_top5 = QCheckBox("Show Top 5 Processes")
        self.set_top5.setChecked(feat_conf.get("top5_process", False))
        form.addRow(self.set_top5)
        
        self.set_csv = QCheckBox("Enable CSV Logging")
        self.set_csv.setChecked(feat_conf.get("csv_logging", False))
        form.addRow(self.set_csv)
        
        self.set_startup = QCheckBox("Run on Startup")
        self.set_startup.setChecked(feat_conf.get("run_on_startup", False))
        form.addRow(self.set_startup)
        
        self.set_hotkey = QCheckBox("Global Hotkey (Ctrl+Alt+M)")
        self.set_hotkey.setChecked(feat_conf.get("hotkey_enabled", False))
        form.addRow(self.set_hotkey)
        
        # Alerts config
        alerts_group = QGroupBox("Alerts & Thresholds")
        alerts_layout = QFormLayout(alerts_group)
        
        self.set_alerts = QCheckBox("Enable Overheat Alerts")
        self.set_alerts.setChecked(feat_conf.get("alerts_enabled", False))
        alerts_layout.addRow(self.set_alerts)
        
        self.set_alert_cpu = QLineEdit(str(feat_conf.get("alert_cpu_temp", 85)))
        alerts_layout.addRow("CPU Temp Threshold (°C):", self.set_alert_cpu)
        
        self.set_alert_gpu = QLineEdit(str(feat_conf.get("alert_gpu_temp", 85)))
        alerts_layout.addRow("GPU Temp Threshold (°C):", self.set_alert_gpu)
        
        form.addRow(alerts_group)
        
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.save_settings)
        form.addRow(save_btn)

    def save_settings(self):
        ov = self.config_mgr.get_overlay_conf()
        ov["click_through"] = self.set_ct.isChecked()
        ov["ghost_mode"] = self.set_ghost.isChecked()
        ov["transparency"] = self.set_opac.value() / 100.0
        ov["font_size"] = self.set_font.value()
        ov["layout"] = self.set_layout.currentText()
        ov["theme"] = self.set_theme.currentText()
        
        enabled_m = []
        for m, cb in self.metric_checkboxes.items():
            if cb.isChecked():
                enabled_m.append(m)
        ov["enabled_metrics"] = enabled_m
        
        ft = self.config_mgr.get_features_conf()
        ft["top5_process"] = self.set_top5.isChecked()
        ft["csv_logging"] = self.set_csv.isChecked()
        ft["run_on_startup"] = self.set_startup.isChecked()
        ft["hotkey_enabled"] = self.set_hotkey.isChecked()
        ft["alerts_enabled"] = self.set_alerts.isChecked()
        
        try:
            ft["alert_cpu_temp"] = int(self.set_alert_cpu.text())
            ft["alert_gpu_temp"] = int(self.set_alert_gpu.text())
        except ValueError:
            pass
        
        self.config_mgr.set_overlay_conf(ov)
        self.config_mgr.set_features_conf(ft)
        
        self.apply_hotkey()
        self._apply_startup_registry(ft.get("run_on_startup", False))
        
        if self.overlay and self.overlay.isVisible():
            self.overlay.apply_theme()
            
        print("Settings saved.")


    def on_data_updated(self, d: SystemData):
        # Update history
        self.hist_cpu.append(d.cpu_use)
        self.hist_ram.append(d.ram_pct)
        try:
            self.hist_gpu.append(float(d.gpu_use))
        except ValueError:
            self.hist_gpu.append(0.0)

        # Update labels
        self.ov_cpu_lbl.setText(f"CPU Usage: {d.cpu_use}%")
        self.ov_cpu_lbl.setStyleSheet(f"color: {get_color_by_value(d.cpu_use, 'usage')}; font-weight: bold;")
        
        self.ov_ram_lbl.setText(f"RAM Usage: {d.ram_pct}%")
        self.ov_ram_lbl.setStyleSheet(f"color: {get_color_by_value(d.ram_pct, 'usage')}; font-weight: bold;")
        
        self.ov_gpu_lbl.setText(f"GPU Usage: {d.gpu_use}%")
        self.ov_gpu_lbl.setStyleSheet(f"color: {get_color_by_value(d.gpu_use, 'usage')}; font-weight: bold;")

        # Update curves
        self.cpu_curve.setData(list(self.hist_cpu))
        self.ram_curve.setData(list(self.hist_ram))
        self.gpu_curve.setData(list(self.hist_gpu))
        
        # Alerts
        feat = self.config_mgr.get_features_conf()
        if feat.get("alerts_enabled"):
            import time
            now = time.monotonic()
            if now - self.last_alert_time >= 60:
                try:
                    cpu_t = float(d.cpu_temp)
                    if cpu_t >= feat.get("alert_cpu_temp", 85):
                        self._trigger_alert("CPU", cpu_t)
                        self.last_alert_time = now
                except ValueError: pass
                
                try:
                    gpu_t = float(d.gpu_temp)
                    if gpu_t >= feat.get("alert_gpu_temp", 85):
                        self._trigger_alert("GPU", gpu_t)
                        self.last_alert_time = now
                except ValueError: pass

        # Update Top 5
        if feat.get("top5_process"):
            txt = "Top 5 CPU:\n" + "\n".join(d.top5_cpu) + "\n\nTop 5 RAM:\n" + "\n".join(d.top5_ram)
            self.top5_lbl.setText(txt)
        else:
            self.top5_lbl.setText("Top 5 Processes\n(Disabled in Settings)")
        # Update CPU Tab
        self.cpu_temp_lbl.setText(f"Temp: {d.cpu_temp}°C")
        self.cpu_clock_lbl.setText(f"Clock: {d.cpu_freq} MHz")
        self.cpu_pow_lbl.setText(f"Power: {d.cpu_pow} W")
        self.cpu_usage_lbl.setText(f"Total Usage: {d.cpu_use}%")
        self.cpu_progress.setValue(int(d.cpu_use))
        
        # Rebuild core grid if size changed
        if len(self.core_labels) != len(d.cpu_cores):
            for i in reversed(range(self.cpu_cores_layout.count())):
                widget = self.cpu_cores_layout.itemAt(i).widget()
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()
            self.core_labels.clear()
            cols = 4
            for i in range(len(d.cpu_cores)):
                lbl = QLabel(f"Core {i}: 0%")
                self.cpu_cores_layout.addWidget(lbl, i // cols, i % cols)
                self.core_labels.append(lbl)
        
        for i, val in enumerate(d.cpu_cores):
            self.core_labels[i].setText(f"C{i}: {val}%")
            self.core_labels[i].setStyleSheet(f"color: {get_color_by_value(val, 'usage')};")

        # Update GPU Tab
        if self.worker.gpu_fetcher.is_valid():
            self.gpu_name_lbl.setText(f"Graphics: {d.gpu_name}")
            self.gpu_usage_lbl.setText(f"Usage: {d.gpu_use}%")
            self.gpu_temp_lbl.setText(f"Temp: {d.gpu_temp}°C")
            self.gpu_mem_lbl.setText(f"VRAM: {d.gpu_mem}")
            self.gpu_pow_lbl.setText(f"Power: {d.gpu_pow}W / {d.gpu_pow_limit}W")
            self.gpu_cclock_lbl.setText(f"Core Clock: {d.gpu_c_clock} MHz")
            self.gpu_mclock_lbl.setText(f"Mem Clock: {d.gpu_m_clock} MHz")
            self.gpu_fan_lbl.setText(f"Fan Speed: {d.gpu_fan}%")

        # Update Storage & Network Tab
        io = d.disk_data.get("GLOBAL_IO", {"read": 0, "write": 0})
        self.disk_io_lbl.setText(f"Disk I/O: Read {io['read']:.1f} MB/s | Write {io['write']:.1f} MB/s")
        
        from PySide6.QtWidgets import QProgressBar, QHBoxLayout
        for letter, data in d.disk_data.items():
            if letter == "GLOBAL_IO":
                continue
            if letter not in self.disk_widgets:
                row = QHBoxLayout()
                lbl = QLabel(f"Drive {letter}:")
                lbl.setFixedWidth(60)
                pb = QProgressBar()
                pb.setRange(0, 100)
                pb.setFixedHeight(12)
                pb.setTextVisible(False)
                free_lbl = QLabel("")
                row.addWidget(lbl)
                row.addWidget(pb)
                row.addWidget(free_lbl)
                self.disks_layout.addLayout(row)
                self.disk_widgets[letter] = {"pb": pb, "free_lbl": free_lbl}
            
            w = self.disk_widgets[letter]
            if data is None:
                w["pb"].setValue(0)
                w["free_lbl"].setText("N/A")
            else:
                w["pb"].setValue(int(data["pct"]))
                w["free_lbl"].setText(f"{data['free']:.1f} GB free")

        self.net_lbl.setText(f"Network: DL {d.dl_speed:.1f} KB/s | UL {d.ul_speed:.1f} KB/s")
        self.net_tot_lbl.setText(f"Total: DL {d.net_tot_dl:.2f} GB | UL {d.net_tot_ul:.2f} GB")

        if self.overlay and self.overlay.isVisible():
            self.overlay.update_data(d)

    def _apply_startup_registry(self, enable):
        import winreg
        import sys, os
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

    def _trigger_alert(self, hw, temp):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except: pass
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Warning!")
        msg.setText(f"🔥 {hw} Overheating!\nTemp: {temp}°C")
        # Non-blocking alert
        msg.setWindowModality(Qt.NonModal)
        msg.show()
        # Auto close after 5 seconds
        from PySide6.QtCore import QTimer
        QTimer.singleShot(5000, msg.close)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Keep app running in System Tray when dashboard is closed
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
