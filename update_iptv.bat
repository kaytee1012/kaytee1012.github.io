@echo off
setlocal

REM ====== SỬA 2 DÒNG NÀY CHO ĐÚNG ======
set REPO=D:\kaytee1012.github.io
set CRAWL=D:\kaytee1012.github.io\crawl_to_m3u.py
REM =====================================

set PY=python
set LOG=%REPO%\update_iptv.log

echo ==================================================>> "%LOG%"
echo RUN %date% %time%>> "%LOG%"

cd /d "%REPO%" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Cannot cd to repo: %REPO%>> "%LOG%"
  echo Loi: khong vao duoc thu muc repo. Xem log: %LOG%
  pause
  exit /b 1
)

REM 1) Chạy crawl (script của mày phải ghi output vào %REPO%\quechoa.txt)
%PY% "%CRAWL%" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Crawl script failed.>> "%LOG%"
  echo Loi: script crawl loi. Xem log: %LOG%
  pause
  exit /b 1
)

REM 2) Nếu không có thay đổi thì thôi (đỡ spam commit)
git diff --quiet >> "%LOG%" 2>&1
if %errorlevel%==0 (
  echo No changes -> skip commit/push.>> "%LOG%"
  echo Khong co thay doi, bo qua commit/push.
  exit /b 0
)

REM 3) Add tất cả (bao gồm file bị xoá)
git add -A >> "%LOG%" 2>&1

REM 4) Commit
git commit -m "Auto update IPTV %date% %time%" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Commit failed (check user.name/user.email?).>> "%LOG%"
  echo Loi: commit khong duoc. Mo log: %LOG%
  pause
  exit /b 1
)

REM 5) Push
git push >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Push failed (auth?).>> "%LOG%"
  echo Loi: push khong duoc (thuong la chua login GitHub). Mo log: %LOG%
  pause
  exit /b 1
)

echo DONE. Updated + pushed OK.>> "%LOG%"
echo XONG! Da commit va push len GitHub.
pause
endlocal
