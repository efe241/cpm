@echo off
chcp 65001 >nul
echo ============================================================
echo 🚀 CPM Bot - GitHub'a Otomatik Gonderici (Push)
echo ============================================================
git add .
git commit -m "update: Auto commit from local"
git push -u origin main
echo.
echo ✅ Islem tamamlandi!
pause
