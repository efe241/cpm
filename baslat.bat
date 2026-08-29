@echo off
title CPM Checker Discord Bot ^& Web Dashboard
echo ============================================================
echo [INFO] CPM Checker Discord Bot ^& Web Server Baslatiliyor...
echo ============================================================
echo.
python bot.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [HATA] Bot calisirken bir sorun olustu.
    pause
)
