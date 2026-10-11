# 在开发电脑上做「要带去电脑 B 的安装包」（docs/deploy-pc-b.md 第 2 步）。
#
# 用法（在仓库根目录，PowerShell）：
#     .\deploy\make-package.ps1
# 做出来的是桌面上的 chatbot-<commit>.zip：git 里的程序 + frontend/dist（build 好的网页）。
# 不包含 backend/.env、.venv、node_modules、任何资料库或备份（git archive 只拿已经 commit 的档案）。

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

if (git status --porcelain) {
    throw "还有没有 commit 的修改。先 commit（或 git stash），安装包只放 commit 过的程序。"
}
$commit = (git rev-parse --short HEAD).Trim()

Write-Host "1/3 build 网页（frontend）..."
Push-Location frontend
npm ci
if ($LASTEXITCODE -ne 0) { throw "npm ci 失败" }
npm run build
if ($LASTEXITCODE -ne 0) { throw "npm run build 失败" }
Pop-Location

Write-Host "2/3 拿出 commit $commit 的程序..."
$staging = Join-Path $env:TEMP "chatbot-package-$commit"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
$src = "$staging.src.zip"
git archive --format=zip --output $src HEAD
Expand-Archive $src $staging
Remove-Item $src
Copy-Item (Join-Path $repo "frontend\dist") (Join-Path $staging "frontend\dist") -Recurse
Set-Content (Join-Path $staging "VERSION.txt") "commit $commit, $(Get-Date -Format 'yyyy-MM-dd HH:mm')"

Write-Host "3/3 压缩..."
$out = Join-Path ([Environment]::GetFolderPath("Desktop")) "chatbot-$commit.zip"
if (Test-Path $out) { Remove-Item $out }
Compress-Archive (Join-Path $staging "*") $out
Remove-Item $staging -Recurse -Force

Write-Host "完成：$out"
