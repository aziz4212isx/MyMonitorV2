import platform
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect, QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QFont
from data_worker import SystemData

class CompactOverlay(QWidget):
    def __init__(self, config_mgr):
        super().__init__()
        self.config_mgr = config_mgr
        self.conf = self.config_mgr.get_overlay_conf()
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Click through
        self.click_through = self.conf.get("click_through", False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.click_through)

        # Dragging state
        self._drag_active = False
        self._drag_pos = QPoint()

        # Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10) # Room for shadow
        
        self.container = QWidget(self)
        self.main_layout.addWidget(self.container)
        
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(8, 8, 8, 8)
        self.container_layout.setSpacing(4)
        
        self.metric_labels = {}
        
        self.apply_theme()
        self.restore_position()

    def apply_theme(self):
        self.conf = self.config_mgr.get_overlay_conf()
        
        ghost = self.conf.get("ghost_mode", False)
        alpha = self.conf.get("transparency", 0.85)
        
        theme_name = self.conf.get("theme", "Cyan")
        colors = {
            "Cyan": "#00E5FF",
            "Razer Green": "#00FF00",
            "Afterburner Orange": "#FF7F00",
            "Pink": "#FF00FF",
            "White": "#FFFFFF"
        }
        color = colors.get(theme_name, "#00E5FF")
        
        if ghost:
            self.setWindowOpacity(1.0)
            self.container.setStyleSheet(f"""
                QWidget {{
                    background-color: transparent;
                    border-radius: 8px;
                }}
                QLabel {{ color: {color}; }}
            """)
            self.container.setGraphicsEffect(None)
        else:
            self.setWindowOpacity(alpha)
            self.container.setStyleSheet(f"""
                QWidget {{
                    background-color: #1a1a1a;
                    border: 1px solid #333333;
                    border-radius: 8px;
                }}
                QLabel {{ color: {color}; }}
            """)
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(15)
            shadow.setColor(QColor(0, 0, 0, 180))
            shadow.setOffset(0, 0)
            self.container.setGraphicsEffect(shadow)

        self.click_through = self.conf.get("click_through", False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self.click_through)

    def restore_position(self):
        pos = self.conf.get("position", {"x": 100, "y": 100})
        x, y = pos.get("x", 100), pos.get("y", 100)
        
        # Validate multi-monitor bounds
        screen = QApplication.screenAt(QPoint(x, y))
        if not screen:
            screen = QApplication.primaryScreen()
            x = screen.geometry().center().x() - 100
            y = screen.geometry().center().y() - 100
            
        self.move(x, y)

    def save_position(self):
        pos = self.pos()
        self.conf["position"] = {"x": pos.x(), "y": pos.y()}
        self.config_mgr.save_config()

    def mousePressEvent(self, event):
        if self.click_through:
            return
        if event.button() == Qt.LeftButton:
            self._drag_active = True
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_active and not self.click_through:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_active and event.button() == Qt.LeftButton:
            self._drag_active = False
            self.save_position()
            event.accept()

    def update_data(self, d: SystemData):
        enabled = self.conf.get("enabled_metrics", [])
        font_size = self.conf.get("font_size", 12)
        layout_type = self.conf.get("layout", "RTSS Compact")
        font = QFont("Segoe UI", font_size, QFont.Bold)
        
        # Format individual values
        vals = {}
        for m in enabled:
            if m == "cpu_usage": vals[m] = f"{d.cpu_use}%"
            elif m == "cpu_temp": vals[m] = f"{d.cpu_temp}°C"
            elif m == "cpu_freq": vals[m] = f"{d.cpu_freq} MHz"
            elif m == "cpu_power": vals[m] = f"{d.cpu_pow} W"
            elif m == "gpu_usage": vals[m] = f"{d.gpu_use}%"
            elif m == "gpu_temp": vals[m] = f"{d.gpu_temp}°C"
            elif m == "gpu_power": vals[m] = f"{d.gpu_pow} W"
            elif m == "ram_usage": vals[m] = f"{d.ram_pct}% ({d.ram_used:.1f}GB)"
            elif m == "vram_usage": vals[m] = f"{d.gpu_mem} MB"
            elif m == "swap_usage": vals[m] = f"{d.swap_pct}%"
            elif m == "net_speed": vals[m] = f"{d.dl_speed:.1f} KB/s \u2193 | {d.ul_speed:.1f} KB/s \u2191"
            elif m == "disk_io": 
                io = d.disk_data.get("GLOBAL_IO", {"read": 0, "write": 0})
                vals[m] = f"{io['read']:.1f}MB/s R | {io['write']:.1f}MB/s W"
            elif m.startswith("disk_usage_"):
                drive = m.split("_")[-1].replace(":", "")
                disk_info = d.disk_data.get(drive)
                vals[m] = f"{disk_info['pct']}% ({disk_info['free']:.1f}GB Free)" if disk_info else "N/A"
        
        # Prepare layout keys based on type
        display_lines = []
        if layout_type == "RTSS Compact":
            groups = {"CPU": [], "GPU": [], "RAM": [], "DSK": [], "NET": []}
            for m in enabled:
                if m.startswith("cpu_"): groups["CPU"].append(m)
                elif m.startswith("gpu_") or m == "vram_usage": groups["GPU"].append(m)
                elif m in ["ram_usage", "swap_usage"]: groups["RAM"].append(m)
                elif m == "net_speed": groups["NET"].append(m)
                elif m.startswith("disk_"): groups["DSK"].append(m)
            
            for g_name, g_metrics in groups.items():
                if g_metrics:
                    s = f"{g_name:<4} " + "  ".join(vals[m] for m in g_metrics)
                    display_lines.append((g_name, s))
        elif layout_type == "Horizontal Bar":
            # Combine all metrics into a single line separated by " | "
            labels = {
                "cpu_usage": "CPU", "cpu_temp": "CPU Tmp", "cpu_freq": "CPU Clk", "cpu_power": "CPU Pwr",
                "gpu_usage": "GPU", "gpu_temp": "GPU Tmp", "vram_usage": "VRAM", "gpu_power": "GPU Pwr",
                "ram_usage": "RAM", "swap_usage": "Swap", "net_speed": "Net", "disk_io": "Disk I/O"
            }
            parts = []
            for m in enabled:
                title = labels.get(m, m.replace('disk_usage_', 'Drive '))
                parts.append(f"{title}: {vals[m]}")
            if parts:
                display_lines.append(("horizontal_bar", "  |  ".join(parts)))
        else:
            # Classic Layout
            labels = {
                "cpu_usage": "CPU", "cpu_temp": "CPU Tmp", "cpu_freq": "CPU Clk", "cpu_power": "CPU Pwr",
                "gpu_usage": "GPU", "gpu_temp": "GPU Tmp", "vram_usage": "VRAM", "gpu_power": "GPU Pwr",
                "ram_usage": "RAM", "swap_usage": "Swap", "net_speed": "Net", "disk_io": "Disk I/O"
            }
            for m in enabled:
                title = labels.get(m, m.replace('disk_usage_', 'Drive '))
                display_lines.append((m, f"{title}: {vals[m]}"))

        current_keys = [k for k, v in display_lines]
        existing_keys = list(self.metric_labels.keys())

        # Rebuild layout only if the lines changed
        if current_keys != existing_keys:
            for i in reversed(range(self.container_layout.count())): 
                w = self.container_layout.itemAt(i).widget()
                if w: 
                    w.setParent(None)
                    w.deleteLater()
            self.metric_labels.clear()
            for k, text in display_lines:
                lbl = QLabel("")
                lbl.setFont(font)
                self.container_layout.addWidget(lbl)
                self.metric_labels[k] = lbl

        # Update values
        for k, text in display_lines:
            lbl = self.metric_labels.get(k)
            if lbl:
                lbl.setFont(font)
                lbl.setText(text)
            
        self.adjustSize()
