# LightMonitor Pro 🚀
*[🇺🇸 English](#english) | [🇮🇩 Bahasa Indonesia](#bahasa-indonesia)*

---
<a name="english"></a>
## 🇺🇸 English

A modern, highly efficient, and sleek PC System Monitor built with Python and `customtkinter`. LightMonitor provides real-time tracking for your CPU, GPU, RAM, Disk, and Network usage. It is designed to be universally compatible with almost any hardware configuration and features a gaming-inspired **HUD Overlay**.

### 🌟 Key Features
*   **Universal Compatibility:** Automatically detects NVIDIA, AMD, or Intel GPUs. Safely hides GPU tabs if no dedicated hardware is detected.
*   **Gaming HUD Overlay (Compact Mode):** A customizable, borderless, transparent, and always-on-top overlay. Keep an eye on your PC metrics while gaming!
*   **Global Hotkey:** Press `Ctrl+Alt+M` to instantly toggle the HUD Overlay from anywhere, even inside a fullscreen game.
*   **Click-Through Mode:** The HUD can be configured to ignore mouse clicks so it never interrupts your gameplay.
*   **Top 5 Resource Hogs:** Automatically tracks and displays the top 5 applications consuming the most CPU and RAM in real-time.
*   **Overheat Alerts:** Set custom temperature thresholds. If your CPU or GPU overheats, the app will trigger a Windows sound and a visual warning popup.
*   **Smart Stability (Anti-Spike & Watchdog):** Automatically handles Windows "Sleep" states to prevent network/disk speed spikes and includes a background watchdog to prevent the app from freezing.
*   **CSV Data Logging:** Silently log your PC's temperature and usage data into a CSV file for post-gaming performance analysis.
*   **Auto-Start:** Run silently in the background on Windows startup with a single click.

### 📥 How to Download & Run (For Users)
You don't need to install Python to use this app!
1. Go to the **[Releases](../../releases)** tab on the right side of this GitHub page.
2. Download the latest `LightMonitor.exe` file.
3. Move the `.exe` file to your preferred folder (e.g., Desktop) and double-click to run!
> *Note: If you want to use the Global Hotkey feature (`Ctrl+Alt+M`), you must right-click `LightMonitor.exe` and select **Run as Administrator**.*

### 🛠️ How to Build from Source (For Developers)
If you want to modify the code and compile it yourself:
```bash
git clone https://github.com/aziz4212isx/MyMonitor.git
cd MyMonitor
pip install customtkinter psutil keyboard pillow
```
Simply double-click the `build_exe.bat` file to generate the `.exe` inside the `dist/` folder.

---

<a name="bahasa-indonesia"></a>
## 🇮🇩 Bahasa Indonesia

PC System Monitor modern, super ringan, dan elegan yang dibangun menggunakan Python dan `customtkinter`. LightMonitor menyediakan pelacakan waktu-nyata (*real-time*) untuk penggunaan CPU, GPU, RAM, Disk, dan Jaringan Anda. Aplikasi ini didesain agar kompatibel dengan hampir seluruh konfigurasi perangkat keras dan dilengkapi dengan **HUD Overlay** bergaya *gaming*.

### 🌟 Fitur Unggulan
*   **Kompatibilitas Universal:** Otomatis mendeteksi GPU NVIDIA, AMD, ataupun Intel. Tab GPU akan disembunyikan dengan rapi jika tidak ada kartu grafis khusus yang terdeteksi.
*   **Gaming HUD Overlay (Mode Ringkas):** Overlay melayang yang tanpa tepi, transparan, dan selalu berada di atas jendela lain (*always-on-top*). Pantau PC Anda sambil bermain game!
*   **Global Hotkey:** Tekan `Ctrl+Alt+M` kapan saja (bahkan di dalam game layar penuh) untuk memunculkan atau menyembunyikan HUD Overlay seketika.
*   **Mode Tembus Klik (Click-Through):** HUD bisa diatur agar mengabaikan klik *mouse* sehingga tidak akan pernah mengganggu permainan Anda.
*   **Top 5 Aplikasi Berat:** Melacak dan menampilkan 5 aplikasi yang paling rakus menyedot CPU dan RAM Anda secara *real-time*.
*   **Alarm Panas (Overheat Alerts):** Atur sendiri batas suhunya. Jika CPU atau GPU Anda terlalu panas, aplikasi akan membunyikan alarm dan memunculkan pop-up peringatan merah di layar.
*   **Stabilitas Pintar (Anti-Spike & Watchdog):** Menangkal *bug* ketika komputer masuk ke mode *Sleep*, dan memiliki fitur *watchdog* di latar belakang yang memastikan aplikasi tidak akan pernah membeku (*freeze*).
*   **Perekam Data CSV:** Merekam jejak data suhu dan pemakaian PC Anda secara diam-diam ke dalam file CSV untuk Anda analisis setelah bermain game.
*   **Auto-Start:** Bisa menyala secara otomatis di latar belakang saat Windows pertama kali dihidupkan cukup dengan satu klik centang.

### 📥 Cara Download & Mainkan (Untuk Pengguna Biasa)
Anda tidak perlu menginstal Python untuk menggunakan aplikasi ini!
1. Pergi ke bagian **[Releases](../../releases)** di sebelah kanan halaman GitHub ini.
2. Unduh file `LightMonitor.exe` versi paling baru.
3. Pindahkan file `.exe` tersebut ke folder favorit Anda (misalnya Desktop), lalu klik dua kali untuk membukanya!
> *Catatan: Jika Anda ingin memakai fitur Global Hotkey (`Ctrl+Alt+M`), Anda wajib menjalankan aplikasinya dengan cara klik kanan `LightMonitor.exe` lalu pilih **Run as Administrator**.*

### 🛠️ Cara Merakit dari Kode Sumber (Untuk Developer)
Jika Anda ingin memodifikasi kode dan mengkompilasinya sendiri:
```bash
git clone https://github.com/aziz4212isx/MyMonitor.git
cd MyMonitor
pip install customtkinter psutil keyboard pillow
```
Cukup klik dua kali pada file `build_exe.bat` yang sudah disediakan, dan file `.exe` akan otomatis terbuat di dalam folder `dist/`.

---
*Built with ❤️ using Python.*
