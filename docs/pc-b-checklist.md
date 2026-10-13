# 去诊所装电脑 B：清单（5b 试跑，D53、D62、D63、D64）

一项一项打勾。**怎么做**照 [`deploy-pc-b.md`](deploy-pc-b.md)（下面的「第 N 节」= 那份文件的第 N 节）和 [`sql/README.md`](../sql/README.md)「只读帐号」第二步；
这份只列要准备、要带、要看、要问、要确认的事，和遇到问题怎么办。

**三个原则**

- **主机 A**：只跑 `create_readonly_login.sql`（建错了才跑 `drop_readonly_login.sql`），其他什么都不跑、不装、不改设定（规则 1）。`.sql` 用 InPrivate 视窗下载（不登入），跑完就删（D64）。
- **B 不合要求**：不硬装、不换没演练过的版本。记下来，回来再决定（D63：测过的版本才知道能用）。
- 病人资料、密码不进 Google Drive、照片、对话、仓库（规则 4、6）。在诊所的电脑上不登入自己的私人帐号（网盘、GitHub、密码管理器的网页版）。

## 0. 密码一览

| 密码 | 谁打 | 存在哪里 |
|---|---|---|
| B 的 Windows 系统管理员 | 诊所的人自己在 UAC 视窗打 | 不问、不记 |
| `postgres`（B 的 PostgreSQL） | 你，装 PostgreSQL 时 | 你的密码管理器（B 上不存） |
| `chatbot`（B 的 PostgreSQL） | 你 | 密码管理器 + B 的 `backend\.env` + B 的 `pgpass.conf` |
| `chatbot_reader`（A 的 SQL Server） | 你，在 B 的 `.env` 和 A 上各打一次 | B 的 `.env`。忘了不要紧：A 上拿掉再建一个 |
| Admin Platform 的帐号 | 每个人自己打（问两次） | 各人自己记；你自己的 ADMIN（有的话）存密码管理器 |

要你打的三个（`postgres`、`chatbot`、`chatbot_reader`）：

- **只用英文字母和数字**：`DATABASE_URL`、`pgpass.conf` 不能有 `@ : / ? # %`；只读帐号的脚本只收字母和数字。
- **大写、小写、数字都要有**：A 的 Windows 密码规则可能要求（脚本用 `CHECK_POLICY = ON`）。
- 20–24 个字，**不用容易看错的 `0 O 1 l I`**：要看着密码管理器一个个打。

产生的方法（密码管理器没有「产生密码」也可以）：在开发电脑的 PowerShell 跑下面几行，印出 20 个字，存进密码管理器；要下一个就再跑最后两行。都存好后 `Remove-Variable p, b`、`cls`。

```powershell
$c = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
do { $b = New-Object byte[] 20; $rng.GetBytes($b); $p = -join ($b | ForEach-Object { $c[$_ % $c.Length] }) } until ($p -cmatch '[A-Z]' -and $p -cmatch '[a-z]' -and $p -match '\d')
$p
```

## 1. 出发前（开发电脑）

**不用 USB**（D64）：zip 和 `.sql` 经 Google Drive 链接带过去（第 2 节）；安装程序到了在 B 上从官网下载。

**和诊所约好**

- [ ] 日期、时间：B 要借 **3–4 小时**（装的时候员工不能在 B 上用 GPiS，中间还要重开机一次）。挑病人少的日子 / 时段
- [ ] 那天有**会打 B 的系统管理员密码**的人在场（装 PostgreSQL、ODBC 一定要）
- [ ] 诊所同意那天在 A 建只读帐号（D52），在病人少的时候
- [ ] 最后留 30 分钟：教员工、一起对照明天的名单

**程序**

- [ ] `git checkout main`、`git pull`；`git log -1 --oneline` 和 GitHub 上的 `main` 一样；`git status` 干净
- [ ] `backend`：`pytest` 全部通过、没有 skipped；`frontend`：`npm test` 通过
- [ ] `.\deploy\make-package.ps1` → 桌面的 `chatbot-<commit>.zip`；记下 `<commit>` 和 hash 的前 8 个字：`(Get-FileHash "$HOME\Desktop\chatbot-*.zip").Hash.Substring(0,8)`
- [ ] 解压到暂时的文件夹看一次：有 `frontend\dist\index.html`、`backend\.env.example`、`backend\requirements-lock.txt`、`deploy\` 的 4 个 `.ps1`、`sql\create_readonly_login.sql`；**没有** `.env`、`.dump`、`.bak`、`.7z`。看完删掉那个暂时的文件夹

**安装程序**（到了在 B 上直接从官网下载；下载后右键 → *内容* → *数位签章*，看发行者对不对）

- [ ] Python **3.11.9**，Windows installer (64-bit)（Python Software Foundation）：`https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe`，**不是** python.org 首页的 *Python install manager*（`.msix`）
- [ ] PostgreSQL **18.x**，Windows x86-64，EDB installer（EnterpriseDB）。和开发电脑、演练一样是 18
- [ ] ODBC Driver **18** for SQL Server，x64（Microsoft）
- [ ] 出问题才下载（第 4 节「遇到问题」）：Visual C++ Redistributable x64（`vc_redist.x64.exe`，ODBC 说少了 Visual C++ 时）、ODBC Driver **17** for SQL Server x64（B 连 A 出现 SSL / TLS 错误时；A 是 SQL Server 2012）
- [ ] B 要连得到网络（2026-10-12 确认过：`pypi.org` 通）

**给 A 的档案**

- [ ] 从最新的 `main` 记下 `sql\create_readonly_login.sql` 的 hash 前 8 个字：`(Get-FileHash .\sql\create_readonly_login.sql).Hash.Substring(0,8)`。`drop_readonly_login.sql` 也记（建错要重来才用）

**密码、笔记**

- [ ] 密码管理器先产生 `postgres`（B）、`chatbot`（B）、`chatbot_reader` 三个（照第 0 节），标清楚是哪一台的哪一个（例：`B-postgres`、`B-chatbot`、`A-chatbot_reader`）
- [ ] 自己的笔记（不进仓库）准备 `.env` 里不是密码的几项：`REMINDER_CLINIC_NAME`、`REMINDER_CLINIC_NAME_EN`、`REMINDER_BRANCH`（照员工现在发的提醒的原文，D47）；`<主机A的IP>`（2026-10-09 在 B 的 `GPiS.exe.config` 看过，到了再看一次）
- [ ] Admin Platform 的帐号名单：谁拿 ADMIN、几位员工、各人的用户名（只有名字；密码各人到时自己打）

**带去看的文件**（手机不连网络也打得开，或印出来；里面没有密码）

- [ ] `docs/deploy-pc-b.md`、`sql/README.md`「只读帐号」、这份清单
- [ ] `docs/clinic-workflow.md` 第 1 节的假期表（第 7 节第 3 项要对照）、W54、W55、W58 的问题（第 7 节）

**顺便**

- [ ] 进度里还没做的：清理网盘中转文件（删除 + 清空回收站）

## 2. 传档案（Google Drive，不用 USB，D64）

- [ ] **只上传这些**，到了诊所、要下载之前才上传：
  - 给 B：`chatbot-<commit>.zip`
  - 给 A：`create_readonly_login.sql`（建错要重来才传 `drop_readonly_login.sql`）
- [ ] 共用设成「知道链接的任何人」、检视者
- [ ] 下载：B / A 的 Edge **InPrivate 视窗**照着打链接 → 下载 → 关掉视窗。**不登入 Google 或任何帐号**
- [ ] 对 hash：`(Get-FileHash <档名>).Hash.Substring(0,8)` 和开发电脑的一样。不一样就不要用，删掉重新下载
- [ ] 下载完**马上**删掉 Drive 里的档案、清空 Drive 的垃圾桶
- [ ] B：zip 解压后 `Unblock-File`（`deploy-pc-b.md` 第 3 节第 5 步），再删掉「下载」里的 zip。A：`.sql` 跑完就删（Shift + Delete）
- [ ] **不能上传**：任何 `.env`；密码；GPiS 的备份（`.bak`、`.7z`）；`GPiS_Dev` 查出来的东西；`%LOCALAPPDATA%\Chatbot\backup` 的 `.dump`（有病人资料）；截图
- [ ] **反过来也不行**：B 的备份、日志、`.env` 都不上传、不复制出来（规则 4、6）

## 3. 到了先看、先问（还没装任何东西）

**问诊所**

- [ ] W54：B 试跑之后可以一直装着本系统吗？下班可以不关机吗？
- [ ] W55：签名表加一句 WhatsApp 的同意（`architecture.md` 8.8）、不同意的在 Remark 写 `NO WA`：可以吗？签名表是谁印的、多久印一次？
- [ ] W58：B 上有没有 WhatsApp Desktop、登入的是诊所的号码吗？员工现在用哪台电脑 / 手机发提醒？
- [ ] 员工平常登入 B 的是哪个 Windows 帐号（本系统跟着那个帐号启动）？
- [ ] 今天可以在 A 建只读帐号吗？几点病人最少？
- [ ] 可以删掉 A 上我们以前做的 `COPY_ONLY` 备份吗（`D:\GPiS_Backup\GPiS_copy.bak` 和那个 `.7z`，只删这两个）？

**看 B**（用员工平常的帐号登入，开普通的 PowerShell）

| 看什么 | 怎么看 | 要求 |
|---|---|---|
| Windows 版本 | `winver`；*设定 → 系统 → 关于* | Windows 10 / 11，**64 位** |
| 内存 | *设定 → 系统 → 关于* | 至少 4 GB（8 GB 比较好） |
| 硬盘 | 档案总管 → `C:` | 至少 5 GB 空的 |
| 能不能装程序 | 问诊所 | 有人会打系统管理员密码 |
| 时间 | 右下角的时间；`Get-TimeZone` | 时间对，时区 `(UTC+08:00) Kuala Lumpur, Singapore`（系统用 UTC 换算「明天」，时间错了名单的日期就错） |
| 网络 | `Test-NetConnection pypi.org -Port 443` | `TcpTestSucceeded : True`（`False` = 下载不了 zip、安装程序、套件） |
| port 8000、5432 | `Get-NetTCPConnection -LocalPort 8000,5432 -State Listen -ErrorAction SilentlyContinue` | 什么都没印 = 空着 |
| 有没有别的 Python、PostgreSQL | `python --version`；`Get-Service postgresql*` | 「找不到 Python」/ 打开 Microsoft Store = 没有；`Get-Service` 什么都没印 = 没有 |
| A 的 IP | B 的 GPiS 文件夹里的 `GPiS.exe.config`，只看 `Database.Server` | 和笔记一样；`sa`、密码那几行不看（规则 5） |
| WhatsApp Desktop | 开始菜单 | 记下有没有、登入的是哪个号码（W58） |

**B 不合要求时**

| 发现 | 怎么办 |
|---|---|
| Windows 7 / 8.1，或 32 位 | **不装**（Python 3.11、PostgreSQL 18、ODBC 18 不支持，或没演练过）。A 的帐号也先不建（没有地方用）。记下规格，回来讨论：D53 的前提不成立，看 `architecture.md` 9.4 的其他方案 |
| 内存不到 4 GB | 不装，同上 |
| 内存刚好 4 GB | 可以装。装好后 GPiS、WhatsApp、浏览器都开着，看 *工作管理员 → 效能 → 记忆体*；常常在 90% 以上就和诊所讨论 |
| `C:` 不到 5 GB | 不要自己删诊所的档案；告诉诊所，下次再装 |
| 没有人会打系统管理员密码 | 今天只看、只问（加上第 4 节 A 的清理，如果诊所同意）；约下次 |
| 没有网络 | 今天不装：zip、安装程序、套件都要从网络下载（D64）。告诉诊所，回来再想 |
| port 8000 或 5432 已经有程序在用 | 停下来。`Get-Process -Id (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess`（5432 一样）记下程序名字，**不要关掉它**。8000 写在 `start-chatbot.ps1`、备份也用 5432，要改程序，回来做 |
| 已经有别的 Python 或 PostgreSQL | 都不要动、不要移除。Python：python.org 的 3.11.9 装在旁边、**不加 PATH**，venv 用完整路径建（`deploy-pc-b.md` 第 3 节第 1、5 步；2026-10-12 的 B 就是这样）。PostgreSQL：停下来，回来问 |
| 时间或时区不对 | 不要自己改（GPiS 也用这个时间）；告诉诊所，改好再装 |
| 没有 WhatsApp Desktop，或登入的不是诊所的号码 | 系统照装（试跑对照名单用不到它）；第 7 节第 5 项跳过、记下。**不用自己的号码登入**。要装的话由诊所用诊所的手机连结（linked device，W58） |
| 防毒软件挡住安装或脚本 | 记下讯息，**不要关掉防毒**；回来问 |

## 4. 在 B、在 A 做的事

顺序：**B 先用假资料装好、检查过 → 才去 A 建帐号 → 回 B 接 A**。B 装不好就不碰 A。

| # | 哪台 | 做什么 | 照 | 大约 |
|---|---|---|---|---|
| 1 | B | 第 3 节看过、问过，都合要求 | 上面 | 15 分钟 |
| 2 | B | 装 python.org 的 Python 3.11.9（B 上已经有别的 Python 就**不勾** *Add python.exe to PATH*）→ `& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" --version` = `Python 3.11.9` | 第 3 节第 1 步 | 5 分钟 |
| 3 | B | 装 ODBC Driver 18 → `Get-OdbcDriver` 看得到它；GPiS 原来的 driver 也还在、不动 | 第 3 节第 2 步 | 5 分钟 |
| 4 | B | 装 PostgreSQL 18（只选 *PostgreSQL Server*、*Command Line Tools*；`postgres` 的密码；port `5432`；防火墙不允许公用网络）→ psql 建 `chatbot` role 和数据库 | 第 3 节第 3 步 | 15–20 分钟 |
| 5 | B | `pgpass.conf` → `psql … -w` 印出 `chatbot` | 第 3 节第 4 步 | 5 分钟 |
| 6 | B | 解压到 `C:\Chatbot_Automation` → **在 `backend` 里**用完整路径建 venv（`sys.base_prefix` 没有 `WindowsApps`）→ `pip install -r requirements-lock.txt` → `.env`（先加 `REMINDER_SOURCE=demo`；`PWD=` 先空着） | 第 3 节第 5 步、第 4 节 | 20–30 分钟 |
| 7 | B | 确认数据库名字是 `chatbot` → `alembic upgrade head`（`0004`）→ seed → ADMIN、STAFF 帐号（各人自己打密码）→ 假资料的名单印得出来。**不跑** `app.db.demo` | 第 5 节 | 15–20 分钟 |
| 8 | B | `notepad .env`，看着密码管理器把 `chatbot_reader` 的密码打在 `PWD=` 后面，存档 | `sql/README.md` 第二步 1 | 5 分钟 |
| 9 | **A** | 下面的「在 A 上」 | `sql/README.md` 第二步 2 | 10–15 分钟 |
| 10 | B | `.env` 拿掉 `REMINDER_SOURCE=demo` → `python -m app.reminders_cli --check-gpis` 两个 `[OK]` → `python -m app.reminders_cli` 明天的名单，和 GPiS 的 Appointment 画面对照人数 | 第 5 节「接主机 A」 | 20–30 分钟 |
| 11 | B | 自动启动 → 第 7 节 1–7 项。第 1 项要重开机：**先请员工关掉 B 上的 GPiS** | 第 6、7 节 | 30–40 分钟 |
| 12 | B | 教员工（第 5 节的「员工」） | | 30 分钟 |

合计大约 3–4 小时（第一次在别人的电脑装，会比演练慢），**留半天**。

**在 A 上**（第 9 步；诊所同意、病人少的时候）

- [ ] A 的 Edge InPrivate 视窗照着打链接，下载 `create_readonly_login.sql`（不登入）→ 关掉视窗 → 开 PowerShell（普通视窗）`cd $HOME\Downloads` → hash 和开发电脑的一样（第 2 节）
- [ ] 照 `sql/README.md` 第二步 2：`$pw = Read-Host …`（看着密码管理器打，和 B 的 `.env` 一样）→ `sqlcmd … -v DatabaseName="GPiS" …` → `Remove-Variable pw` → `cls`（`Read-Host` 打的字会留在画面上）
- [ ] 印出的和开发电脑一样：`GRANT` 3 个、数据库层 `DENY` 14 个 + `SELECT Tbl_User`、`ReadableTablesAndViews = 2`、`OtherDatabasePermissions = 0`、最后 `完成：…`。记下 `DeniedTablesAndViews` 的数目（开发电脑是 201；GPiS 之后加了表的话会不一样）
- [ ] 诊所同意的话，在档案总管删掉 `D:\GPiS_Backup\GPiS_copy.bak` 和那个 `.7z`：选好按 **Shift + Delete**（不经过资源回收筒，不动 A 的资源回收筒）；`D:\GPiS_Backup` 是我们建的（`gpis-database.md` 第 5 节 ⑤），删完是空的就把文件夹也删掉。**只删这两个**
- [ ] 看一下 A 已经登出私人网盘帐号
- [ ] 删掉「下载」里的 `create_readonly_login.sql`（Shift + Delete）→ 关掉 PowerShell；Drive 的档案删了、垃圾桶清空

**遇到问题**

| 第几步 | 看到 | 怎么办 |
|---|---|---|
| 2 | `python --version` 是 3.11.9，但 `(Get-Command python).Source` 有 `WindowsApps` | 那是 Microsoft Store 的 Python，不能用（`deploy-pc-b.md` 第 3 节第 1 步）。装 `python-3.11.9-amd64.exe`，venv 用完整路径建 |
| 2 | 下载到的是 `.msix`，跳出 *Python installation manager configuration helper* | 拿错了档案。问题都答 `N`，*设定 → 应用* 移除 *Python Install Manager*（只移除它），改下载 `python-3.11.9-amd64.exe` |
| 3 | ODBC 装不上，说少了 Visual C++ | 在 B 从 Microsoft 网站下载 `vc_redist.x64.exe` 装，再装一次 ODBC |
| 4 | PostgreSQL 装到一半失败 | 记下讯息，不要换别的版本；回来问 |
| 6 | `Activate.ps1` 不让执行，`Set-ExecutionPolicy` 也被挡 | 不用 activate：之后的指令前面都加 `.\.venv\Scripts\`（例：`.\.venv\Scripts\python.exe -m pip …`、`.\.venv\Scripts\alembic.exe upgrade head`）。自动启动不受影响（它自己用 `-ExecutionPolicy Bypass`） |
| 6 | pip 连不上或很慢 | `Test-NetConnection pypi.org -Port 443`；通的话等一下再装一次，不通就停，回来问 |
| 6 | `Could not open requirements file` | 不在 `backend` 里：`cd C:\Chatbot_Automation\backend`。venv 也要在 `backend\.venv`（建错地方就删掉重建） |
| 6 | pip `UnicodeDecodeError: 'charmap' codec …` | 旧的 `requirements-lock.txt` 有中文说明（2026-10-12 改成只有 ASCII）：先 `$env:PYTHONUTF8 = "1"` 再装 |
| 9 | 脚本第一句就停：`要用有管理权限（sysadmin）的 Windows 帐号` | 这个 Windows 帐号在 SQL Server 不是 sysadmin。以前在 A 用 `-E` 做过 `COPY_ONLY` 备份，所以先试：PowerShell 按右键 *以系统管理员身分执行*（诊所的人打密码），再跑一次。还是不行就停，**不要改用 `sa`**，回来再想 |
| 9 | `Password validation failed` | 密码不够复杂，**还没建任何东西**。密码管理器换一个（大写、小写、数字都有），B 的 `.env` 也改，再跑 |
| 9 | `帐号 chatbot_reader 已经存在` | 不要猜是谁建的：先跑 `drop_readonly_login.sql`（经 Drive 链接下载、对 hash；`-C -f 65001`，`-v DatabaseName="GPiS"`），再跑一次 |
| 9 | 脚本报错：`chatbot_reader 的权限不对` | 帐号建了但权限不对：马上跑 `drop_readonly_login.sql` 拿掉；把印出的权限（没有病人资料）抄下来回来问 |
| 10 | *Login failed for user 'chatbot_reader'* | `.env` 和 A 上打的不一样：A 上跑 `drop_readonly_login.sql`，从第 8 步重来（`sql/README.md` 第二步 4） |
| 10 | SSL / TLS 的错误（`SSL Provider`、`certificate`、`TLS`、`encryption` 之类） | A 是 SQL Server 2012，和 ODBC Driver 18 可能谈不拢加密。**A 什么都不改**，只在 B 试：① 抄下完整的错误讯息（没有密码）；② `.env` 的连线字符串加 `Encrypt=no;`，再 `--check-gpis`（局域网里不加密，和 B 上的 GPiS 现在一样）；③ 还不行：在 B 从 Microsoft 网站下载 ODBC Driver 17 装，`DRIVER={ODBC Driver 17 for SQL Server}`，再试；④ 还不行：停在这里，`.env` 加回 `REMINDER_SOURCE=demo`，告诉员工先不用，回来问。A 的帐号可以留着（只读得到那两个），诊所不想留就跑 `drop_readonly_login.sql`。②、③ 有用的话记下来（回来要写进文件） |
| 10 | 名单的人数和 GPiS 不一样 | 先看是不是 `00:00`、取消的、*Needs staff* 里的（D50、D51、D57）。还是不一样：记下日期、时间、医生、`AppointmentID`（**不记名字、号码**），回来对照 |
| 11 | 重开机后网页打不开 | 看 `%LOCALAPPDATA%\Chatbot\logs\` 的 `start.log`、最新的 `uvicorn-*.log` 最后几行（`backup-error.log` 是备份的）；改了什么就 `stop-chatbot.ps1` → `Start-ScheduledTask -TaskName Chatbot_Automation` |

**中途要放弃时**（B 恢复原样）：`C:\Chatbot_Automation\deploy\install-autostart.ps1 -Remove`（装了的话；会先停下本系统）→ 删掉 `C:\Chatbot_Automation`、`%LOCALAPPDATA%\Chatbot`、`%APPDATA%\postgresql\pgpass.conf`。
Python、PostgreSQL、ODBC 留着不影响 GPiS；诊所要移除的话在 *设定 → 应用程式* 移除。A 的帐号照诊所的意思留着或 `drop_readonly_login.sql`。

## 5. 离开前

**电脑 B**

- [ ] 重开机、登入 Windows，不用开任何视窗，<http://localhost:8000> 是登入画面（第 7 节第 1 项）
- [ ] `start.log` 有今天的 `备份：…dump`、`uvicorn 启动`（第 7 节第 2 项）
- [ ] `postgres` 要密码：`& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -w -c "SELECT 1"` → `no password supplied`（开发电脑演练时发现一开始不用密码，D63 的记录）
- [ ] `--check-gpis` 两个 `[OK]`；明天的名单和 GPiS 对过
- [ ] *Settings → Clinic closures*：2026、2027 各 *Added 11 day(s)*，和 `clinic-workflow.md` 第 1 节一样；Hari Raya 的日期核对过（第 7 节第 3 项）
- [ ] 第 7 节第 5 项按过 *Open in WhatsApp* 的那一行已经按 *Mark as not sent*（不然员工会以为发过了，D58）
- [ ] 第 7 节第 6 项在 B 上做（`Test-NetConnection`），不用 A 的浏览器
- [ ] 第 7 节第 7 项：STAFF 帐号看得到名单、*Settings* 不能改
- [ ] B 的 GPiS 照样打得开、看得到预约（员工确认）；WhatsApp Desktop 照常
- [ ] 浏览器有 `http://localhost:8000` 的书签 / 桌面捷径
- [ ] PowerShell、记事本都关了；B 上写着密码的只有 `.env`、`pgpass.conf`；这两个没有拍照、没有复制

**主机 A**

- [ ] A 的 GPiS 照常（员工确认）
- [ ] A 上没有留下我们的东西：下载的 `.sql` 删了、PowerShell 关了；`COPY_ONLY` 的 `.bak`、`.7z` 删了（诊所同意的话）
- [ ] A 已经登出私人网盘帐号

**员工**

- [ ] 每个人用自己的帐号登入过一次；ADMIN 知道 *Settings* 在哪
- [ ] 试跑 1–2 星期（W42）：**照旧手动发**，同时看系统的名单对照。试跑期间不用 *Open in WhatsApp* 发；不小心按了 → *Mark as not sent*
- [ ] 名单和自己算的不一样：记下日期、时间、医生告诉你。**不写名字、号码，不传有病人名字的截图**（规则 4）
- [ ] 病人说不要 WhatsApp：在名单按 *NO WA*（D55）
- [ ] 诊所临时休息的日子：ADMIN 自己在 *Clinic closures* 加（D61）
- [ ] 网页打不开：先登出、重新登入 Windows；还不行就告诉你，不要自己改档案

**带回来、记下来**（不含密码、IP、病人资料）

- [ ] Google Drive 里的档案删了、垃圾桶清空了
- [ ] B 的规格（Windows 版本、内存、硬盘）、装的版本（Python、PostgreSQL、ODBC）、安装包的 commit
- [ ] A 上脚本的结果：`DeniedTablesAndViews`、`ReadableTablesAndViews`、`OtherDatabasePermissions`
- [ ] 第 7 节 1–7 项的结果；遇到的问题和怎么解决的（例：有没有用 `Encrypt=no`、ODBC 17）
- [ ] W54、W55、W58 的回答
- [ ] 回来后写进 `deploy-pc-b.md`（像第 8 节的演练记录）、`clinic-workflow.md`（W 的回答），更新 `CLAUDE.md` 的进度
