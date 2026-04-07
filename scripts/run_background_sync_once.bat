@echo off
cd /d C:\development\projects\open-dota-api
if not exist ".runlogs" mkdir ".runlogs"
".venv\Scripts\python.exe" "scripts\background_sync_worker.py" --player 1233793238 --window-days 365 --detail-batch 12 --parse-batch 4 --interval-seconds 15 --pause-after-429-seconds 30 --once >> ".runlogs\scheduled_background_sync.log" 2>> ".runlogs\scheduled_background_sync.err.log"
