@echo off
title LightMonitor EXE Builder
echo ===================================================
echo   LightMonitor to EXE Compiler (PyInstaller)
echo ===================================================
echo.
echo Menginstal PyInstaller (jika belum tersedia)...
pip install pyinstaller
pip install keyboard

echo.
echo Menutup aplikasi jika sedang berjalan agar file tidak terkunci...
taskkill /f /im LightMonitor.exe >nul 2>&1

echo.
echo Membersihkan cache kompilasi sebelumnya...
if exist "LightMonitor.spec" del /f /q "LightMonitor.spec"
if exist "build" rmdir /s /q "build"

echo.
echo Mulai mengkompilasi LightMonitor.py dan semua modul pendukungnya...
echo (Ini mungkin memakan waktu 1-2 menit, mohon jangan tutup jendela ini)
echo.

:: --clean: clear pyinstaller cache
:: --noconfirm: overwrite existing build
:: --onefile: bundle everything into a single .exe
:: --windowed: hide the console window when running the app
:: --icon: set the app logo
:: --add-data: include the icon inside the executable bundle
python -m PyInstaller --clean --noconfirm --onefile --windowed --icon="icon.ico" --add-data "icon.png;." --add-data "icon.ico;." --name "LightMonitor" main.py

echo.
echo ===================================================
echo KOMPILASI SELESAI!
echo ===================================================
echo Anda bisa menemukan file aplikasinya (LightMonitor.exe) 
echo di dalam folder "dist" yang baru saja dibuat.
echo.
pause
