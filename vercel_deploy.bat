@echo off
echo ============================================================
echo [INFO] Vercel Deploy Baslatiliyor...
echo ============================================================
echo.
call npx --yes vercel --prod
echo.
echo ============================================================
echo [INFO] Islem Tamamlandi!
echo ============================================================
pause
