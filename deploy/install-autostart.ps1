# 电脑 B：设定「登入 Windows 就启动本系统」（docs/deploy-pc-b.md 第 6 步）。只做一次。
#
# 用法（用平常登入电脑 B 的 Windows 帐号，普通的 PowerShell，不用系统管理员）：
#     .\deploy\install-autostart.ps1          设定
#     .\deploy\install-autostart.ps1 -Remove  拿掉
#
# 工作排程器里的名字：Chatbot_Automation。登入后在背景跑 start-chatbot.ps1（看不到视窗）；
# 停了 1 分钟后自动重开（最多 3 次）；不会因为跑太久被停掉。

param([switch]$Remove)
$ErrorActionPreference = "Stop"
$name = "Chatbot_Automation"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Host "已经拿掉 $name。本系统下次登入不会自己启动。"
    exit 0
}

$script = Resolve-Path (Join-Path $PSScriptRoot "start-chatbot.ps1")
$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Chatbot_Automation（docs/deploy-pc-b.md）" -Force | Out-Null
Write-Host "完成：登入 $user 就会启动本系统。现在就启动：Start-ScheduledTask -TaskName $name"
