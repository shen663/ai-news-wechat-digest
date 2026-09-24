$ErrorActionPreference = 'Stop'

if ((Get-TimeZone).Id -ne 'China Standard Time') {
    throw 'Set Windows timezone to China Standard Time before installing the 10:00 task.'
}

$python = (Get-Command python -ErrorAction Stop).Source
$script = Join-Path $PSScriptRoot 'ai_digest.py'
$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" run' -f $script) -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At 10:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName 'AI Daily Digest' -Action $action -Trigger $trigger -Settings $settings `
    -Description 'Send the daily AI digest to WeChat at 10:00 China time' -Force | Out-Null

Write-Host 'Installed AI Daily Digest. Runs daily at 10:00 China time.'
