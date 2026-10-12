# 停下本系统（docs/deploy-pc-b.md：改了 .env 要重开、第 9 节更新之前、第 8 节演练完清理）。
#
# 用法（普通的 PowerShell，不用系统管理员）：
#     .\deploy\stop-chatbot.ps1
# 再启动：Start-ScheduledTask -TaskName Chatbot_Automation（或重新登入 Windows）
#
# 先停工作排程器里的 start-chatbot.ps1（不然它 1 分钟后又把 uvicorn 开起来），再停 uvicorn：
# 只 Stop-ScheduledTask 的话，uvicorn 可能还在跑（port 8000 还被占着、文件夹改不了名、数据库删不掉）。

$name = "Chatbot_Automation"
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $name
}

# uvicorn：venv 的 python.exe 会再开一个真的 python.exe，两个的命令列都有 app.main:app 和 --port 8000
$servers = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*uvicorn*app.main:app*--port 8000*" })
foreach ($s in $servers) { Stop-Process -Id $s.ProcessId -Force -ErrorAction SilentlyContinue }

# 等 port 8000 空出来（最多 10 秒）
for ($i = 0; $i -lt 10; $i++) {
    $busy = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)
    if ($busy.Count -eq 0) { break }
    Start-Sleep -Seconds 1
}
if ($busy.Count -gt 0) {
    $who = $busy | ForEach-Object {
        $owner = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        "$($owner.ProcessName)（PID $($_.OwningProcess)）"
    }
    Write-Host "port 8000 还有程序在用：$($who -join '、')。不是本系统的话先关掉它；是的话重新开机。"
    exit 1
}
Write-Host "已经停了：停了 $($servers.Count) 个 python.exe，port 8000 空了。再启动：Start-ScheduledTask -TaskName $name"
