# 电脑 B：登入 Windows 时由「工作排程器」执行（install-autostart.ps1 设定的，docs/deploy-pc-b.md 第 6 步）。
#
# 1. 先备份本系统的 PostgreSQL（每次开机一份，留最新的 14 份）；备份失败也照样启动
# 2. 启动 uvicorn：只听 127.0.0.1（只有电脑 B 自己打得开，D62），不印每个网址（--no-access-log）
#
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
Note "uvicorn 启动：http://127.0.0.1:8000"
# 每次启动重写 uvicorn.log、uvicorn-out.log（只留这次开机的）
$server = Start-Process $python -Wait -PassThru -NoNewWindow `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log" `
    -RedirectStandardError (Join-Path $logs "uvicorn.log") -RedirectStandardOutput (Join-Path $logs "uvicorn-out.log")
Note "uvicorn 停了（exit code $($server.ExitCode)）；工作排程器会在 1 分钟后重开"
exit 1
