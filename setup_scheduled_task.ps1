# Run this script as Administrator to create the scheduled task
# Right-click PowerShell > Run as Administrator > then run this script

$taskName = "dbDashboard_DailyUpdate"
$batPath = "G:\My Drive\DesktopPC\vscode_projects\dbDashboard\run_daily_pipeline.bat"

# Create the scheduled task
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batPath`""
$trigger = New-ScheduledTaskTrigger -Daily -At 6:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Daily update of SFR dashboard from Google Drive data" -Force
    Write-Host "✓ Scheduled task '$taskName' created successfully!" -ForegroundColor Green
    Write-Host "  - Runs daily at 6:00 AM"
    Write-Host "  - Logs saved to: G:\My Drive\DesktopPC\vscode_projects\dbDashboard\logs\pipeline.log"
    Write-Host ""
    Write-Host "To test manually, run:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
} catch {
    Write-Host "✗ Failed to create scheduled task: $_" -ForegroundColor Red
    Write-Host "Make sure you're running PowerShell as Administrator" -ForegroundColor Yellow
}
