@echo off
setlocal
cd /d D:\kaytee1012.github.io

REM ====== (1) Chạy crawler ======
python crawl_to_m3u.py

REM ====== (2) Commit & push nếu có thay đổi ======
git add -A
git diff --cached --quiet
if %errorlevel%==0 (
  echo No changes. %date% %time%
  exit /b 0
)

git commit -m "auto: update iptv"
git push

echo Done. %date% %time%
endlocal