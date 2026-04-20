@echo off
REM Daily dashboard update pipeline
REM Scheduled to run automatically via Windows Task Scheduler

setlocal

REM Set environment variables
set PYTHONIOENCODING=utf-8
set APP_CONFIG=pre_EVT2
set PATH=%PATH%;C:\Users\samlai\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.73.5-windows-amd64

REM Navigate to project directory
cd /d "G:\My Drive\DesktopPC\vscode_projects\dbDashboard"

REM Log start time
echo ========================================>> logs\pipeline.log
echo Pipeline started at %date% %time%>> logs\pipeline.log
echo ========================================>> logs\pipeline.log

REM Run the pipeline (skip ghpages since it requires gh CLI auth)
C:\tools\fb-python\fb-python310\python.exe run_pipeline.py --config pre_EVT2 --skip-ghpages >> logs\pipeline.log 2>&1

REM Log completion
echo Pipeline completed at %date% %time%>> logs\pipeline.log
echo.>> logs\pipeline.log

endlocal
