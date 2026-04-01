@echo off
title Tenbury Farm Supplies - Price Lookup App
echo.
echo  =====================================================
echo   Tenbury Farm Supplies - Price Lookup App
echo  =====================================================
echo.
echo  Starting app...
echo.
echo  Admin (this PC):  http://localhost:5000/admin
echo  Staff lookup:     http://farmprices.local:5000
echo  (or use the IP shown below after startup)
echo.
echo  Default password: farm2024
echo  Change it in Admin - Settings after first login.
echo.
echo  Press Ctrl+C to stop the app.
echo  =====================================================
echo.

cd /d "%~dp0"
python app.py

pause
