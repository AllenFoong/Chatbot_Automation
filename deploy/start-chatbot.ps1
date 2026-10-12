# 电脑 B：登入 Windows 时由「工作排程器」执行（install-autostart.ps1 设定的，docs/deploy-pc-b.md 第 6 步）。
#
# 1. 先备份本系统的 PostgreSQL（每次开机一份，留最新的 14 份）；备份失败也照样启动
# 2. 启动 uvicorn：只听 127.0.0.1（只有电脑 B 自己打得开，D62），不印每个网址（--no-access-log）。
#    停了就等 1 分钟再开，最多重开 3 次（自己重开：程序停了，工作排程器的「失败时重新启动」不一定会重开）
#
# 停下本系统：stop-chatbot.ps1（只 Stop-ScheduledTask 的话，uvicorn 可能还在跑）。
# 日志：%LOCALAPPDATA%\Chatbot\logs\。程序日志不记消息内容和电话号码（D38）。
# 备份：%LOCALAPPDATA%\Chatbot\backup\。里面有病人的名字、号码（reminders 表），只留在电脑 B，
#       不要复制到 USB、网盘、WhatsApp（规则 4）。

$app = Join-Path $env:LOCALAPPDATA "Chatbot"
$logs = Join-Path $app "logs"
$backups = Join-Path $app "backup"
New-Item -ItemType Directory -Force $logs, $backups | Out-Null
$log = Join-Path $logs "start.log"
function Note($text) { Add-Content $log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $text" -Encoding UTF8 }

$backend = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
$python = Join-Path $backend ".venv\Scripts\python.exe"
Note "启动：$backend"
if (-not (Test-Path $python)) {
    Note "找不到 $python：先照 docs/deploy-pc-b.md 第 3 节建 venv"
    exit 1
}

# ---------- 1. 备份 ----------
# 密码在 %APPDATA%\postgresql\pgpass.conf（pg_dump 自己会读；不在这个档案、不在仓库）
# 数据库名字、帐号照 backend\.env 的 DATABASE_URL（电脑 B：chatbot；开发电脑演练：chatbot_rehearsal）
$url = Get-Content (Join-Path $backend ".env") -ErrorAction SilentlyContinue |
    Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
if ($url -match '//([^:@/]+)(:[^@]*)?@[^/]+/([^?\s]+)') { $dbUser, $dbName = $Matches[1], $Matches[3] }
else { $dbUser, $dbName = "chatbot", "chatbot" }
$pgDump = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending | Select-Object -First 1
if ($null -eq $pgDump) {
    Note "备份：找不到 pg_dump.exe，这次不备份"
} else {
    $file = Join-Path $backups "$dbName-$(Get-Date -Format 'yyyyMMdd-HHmm').dump"
    $dump = Start-Process $pgDump.FullName -Wait -PassThru -NoNewWindow `
        -ArgumentList "--host=localhost", "--username=$dbUser", "--no-password", "--format=custom", "--file=`"$file`"", $dbName `
        -RedirectStandardError (Join-Path $logs "backup-error.log")
    if ($dump.ExitCode -eq 0) {
        Note "备份：$file"
        Get-ChildItem $backups -Filter "$dbName-*.dump" | Sort-Object Name -Descending |
            Select-Object -Skip 14 | Remove-Item
    } else {
        Note "备份失败（看 backup-error.log）；系统照样启动"
        Remove-Item $file -ErrorAction SilentlyContinue
    }
}

# ---------- 2. 启动 ----------
Set-Location $backend
$env:PYTHONUTF8 = "1"     # 日志里的中文用 UTF-8 存（不然变成 \uXXXX）
for ($run = 1; $run -le 4; $run++) {
    # 每次启动一个新的日志档：重开时不会盖掉上一次停下来的原因；留最新的 14 个
    $uvicornLog = Join-Path $logs "uvicorn-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
    Note "uvicorn 启动：http://127.0.0.1:8000（日志 $(Split-Path $uvicornLog -Leaf)）"
    $server = Start-Process $python -Wait -PassThru -NoNewWindow `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log" `
        -RedirectStandardError $uvicornLog -RedirectStandardOutput (Join-Path $logs "uvicorn-stdout.log")
    Note "uvicorn 停了（exit code $($server.ExitCode)）"
    Get-ChildItem $logs -Filter "uvicorn-*.log" | Where-Object Name -match '^uvicorn-\d{8}-\d{6}\.log$' |
        Sort-Object Name -Descending | Select-Object -Skip 14 | Remove-Item
    if ($run -lt 4) { Start-Sleep -Seconds 60 }
}
Note "uvicorn 停了 4 次，不再重开：看 uvicorn-*.log。重新登入 Windows（或 Start-ScheduledTask -TaskName Chatbot_Automation）会再启动"
exit 1
