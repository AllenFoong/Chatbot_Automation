# 装到柜台电脑 B（Phase 5b 试跑，D53、D62）

柜台有两台电脑：**A**（主机，SQL Server + GPiS 数据库，24 小时开着）、**B**（另一台，下班会关，W54）。
本系统装在 **B**，经局域网用只读帐号读 A 的 GPiS（D52、D60）。**A 上什么都不装**（规则 1）。

**先在开发电脑照这份文件演练一次**（第 8 节），全部通过才去诊所装。

## 1. 这一版做什么、不做什么

| | |
|---|---|
| ✅ 员工在 **B 的浏览器**打开 `http://localhost:8000` | Admin Platform：Reminders 名单（读 A 的实时预约）、*Open in WhatsApp*、*NO WA*、Settings |
| ✅ 按 *Open in WhatsApp* → **B 上的 WhatsApp Desktop** 打开那位病人的对话，消息已经填好，员工按 Enter | 和现在员工一条条发一样，只是名单、`*C`、家人合并由系统做（D54） |
| ✅ 登入 Windows 就自动启动、停了自己重开；每次开机备份本系统的数据库 | `deploy/install-autostart.ps1`、`deploy/start-chatbot.ps1`（停下用 `deploy/stop-chatbot.ps1`） |
| ❌ **只有 B 自己打得开**（`127.0.0.1`），A 或别的电脑、手机都打不开 | 网页里有病人名字和号码；不开放给局域网，就不用 https（D62） |
| ❌ 不收 WhatsApp 消息（5a 的 webhook、cloudflared 不装） | 要等 5c 接上诊所的号码 |
| ❌ 不装 Node.js、git、SQL Server | 网页在开发电脑 build 好，用 USB 带过去 |

试跑期间员工**照旧手动发**，同时对照系统的名单 1–2 星期（W42）。

## 2. 去诊所之前

**要先知道的**（下次去诊所看 / 问）：

| | 要求 |
|---|---|
| Windows 版本 | Windows 10 或 11，**64 位**（*设定 → 系统 → 关于*） |
| 内存 | 至少 4 GB（8 GB 比较好）；PostgreSQL + Python 大约用 300–500 MB |
| 硬盘 | 至少 5 GB 空的 |
| 帐号 | 员工平常登入 B 的 Windows 帐号（本系统跟着这个帐号启动）；要能装程序（问一下有没有系统管理员密码） |
| WhatsApp | B 上有没有装 WhatsApp Desktop、登入的是不是诊所的号码？员工现在用哪台电脑 / 手机发提醒？（W58） |
| 网络 | B 连得到 A（B 的 GPiS 现在就是经局域网连 A，W51），也连得到网络（装套件要用） |

**在开发电脑准备好**：

1. `git pull`，确认 `main` 是最新的、`pytest`、`npm test` 都通过。
2. 做安装包（在仓库根目录）：
   ```powershell
   .\deploy\make-package.ps1
   ```
   → 桌面上的 `chatbot-<commit>.zip`：程序 + build 好的网页。**不包含** `.env`、密码、资料库、GPiS 的备份。
3. 下载这三个安装程序，和 zip 一起放进 USB：
   - Python **3.11.9**（python.org，Windows installer 64-bit）：和开发电脑一样（演练、测试都是 3.11.9；3.11 最后一个有 Windows 安装程序的版本）
   - PostgreSQL 17 或以上（postgresql.org → Windows → EDB installer）
   - ODBC Driver 18 for SQL Server（Microsoft 网站，x64）
4. 想好 B 要用的两个密码（PostgreSQL 的 `postgres`、`chatbot`），存在**自己的密码管理器**，不写在纸上、不放 USB。
   `postgres` 的密码一定要存好：开发电脑演练时发现没有人记得，要用系统管理员才能重设。
   `chatbot_reader` 的密码在 B 上产生（第 5 步）。

## 3. 在 B 上安装程序（只做一次）

用员工平常登入的 Windows 帐号。

1. **Python**：执行安装程序，勾选 *Add python.exe to PATH*。装好后开 PowerShell：`python --version` → `Python 3.11.9`。
2. **ODBC Driver 18**：执行安装程序。确认：
   ```powershell
   Get-OdbcDriver | Where-Object Name -like "*SQL Server*" | Select-Object Name
   ```
   → 有 `ODBC Driver 18 for SQL Server`（GPiS 用的旧版 driver 也会在，不要动它）。
3. **PostgreSQL**：组件只选 *PostgreSQL Server*、*Command Line Tools*（不用 pgAdmin、Stack Builder）；
   `postgres` 的密码用第 2 节准备的；port `5432`；Windows 防火墙问的话**不要**允许公用网络。
   开始菜单 → *SQL Shell (psql)* → 一路 Enter → 打 `postgres` 的密码：
   ```sql
   CREATE ROLE chatbot LOGIN PASSWORD '换成 chatbot 的密码';
   CREATE DATABASE chatbot OWNER chatbot;
   \q
   ```
   B 上的数据库叫 `chatbot`（开发电脑是 `chatbot_dev`）。B 上**不建** `chatbot_test`，不在 B 上跑测试。
4. **备份用的密码档**（`start-chatbot.ps1` 的 `pg_dump` 会读）：
   ```powershell
   New-Item -ItemType Directory -Force "$env:APPDATA\postgresql" | Out-Null
   notepad "$env:APPDATA\postgresql\pgpass.conf"
   ```
   记事本问要不要建新档 → 是。写一行（换成 `chatbot` 的密码），存档：
   ```
   localhost:5432:chatbot:chatbot:换成chatbot的密码
   ```
   确认（`-w` = 不问密码，只靠 pgpass）：
   ```powershell
   & "C:\Program Files\PostgreSQL\<版本>\bin\psql.exe" -h localhost -U chatbot -d chatbot -w -c "SELECT current_database();"
   ```
   → `chatbot`。`no password supplied` / `authentication failed` = 那一行写错（档名也要是 `pgpass.conf`，不是 `.txt`）。
5. **本系统**：把 zip 解压到 `C:\Chatbot_Automation`（这个位置以后更新也用一样的）。
   ```powershell
   cd C:\Chatbot_Automation\backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1          # 不让执行的话先跑：Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   pip install -r requirements-lock.txt  # 演练测过的版本（固定版本、不装测试工具）
   copy .env.example .env
   notepad .env
   ```

## 4. B 的 `.env`

先用**假资料**确认装好（第 5 步），之后才接 A：

```ini
GPIS_CONNECTION_STRING=DRIVER={ODBC Driver 18 for SQL Server};SERVER=<主机A的IP>\SQLEXPRESS;DATABASE=GPiS;UID=chatbot_reader;PWD=<第 5 步产生的密码>;TrustServerCertificate=yes;ApplicationIntent=ReadOnly
GPIS_EXPECTED_DATABASE=GPiS
DATABASE_URL=postgresql+psycopg://chatbot:<chatbot 的密码>@localhost:5432/chatbot
COOKIE_SECURE=false
AI_REPLIES_ENABLED=false
REMINDER_CLINIC_NAME=<照诊所现在的原文>
REMINDER_CLINIC_NAME_EN=<照诊所现在的原文>
REMINDER_BRANCH=<照诊所现在的原文>
REMINDER_SOURCE=demo
```

- `COOKIE_SECURE=false`：只在 B 自己用 `http://localhost`，没有 https（D62）。
- WhatsApp 那几行（`WHATSAPP_*`）留着 `CHANGE_ME`、`WHATSAPP_ALLOWED_RECIPIENTS` 留空：这一版不用 Cloud API 发消息。
- `TEST_DATABASE_URL` 删掉（B 上不跑测试）。
- `.env` 有密码：只在 B 上，不复制、不拍照、不贴给 AI（规则 6）。

## 5. 建表、帐号、假期

在 `C:\Chatbot_Automation\backend`（venv 启用中）。先确认 `.env` 指到哪个数据库（演练时 `DATABASE_URL` 还指着 `chatbot_dev`，是这样查到的）：

```powershell
python -c "from app.config import get_database_url; print(get_database_url().rsplit('/', 1)[1])"   # 要是 chatbot
alembic upgrade head                                  # 建表（最后一行是 0004）
python -m app.db.seed                                 # 初始设置：医生、排班、疗程
python -m app.db.create_staff boss "Your Name" --admin  # ADMIN 帐号（密码会问两次）
python -m app.db.create_staff staff1 "员工名字"        # 每位员工一个 STAFF 帐号
python -m app.reminders_cli 2026-10-12                # REMINDER_SOURCE=demo：应该印出假资料的名单
```

**不要**跑 `python -m app.db.demo`（假的对话、预约请求，B 上不要有）。

接主机 A（诊所同意、病人少的时候）：

1. 照 [`sql/README.md`](../sql/README.md)「只读帐号」**第二步**：在 B 产生密码 → 写进 `.env` 的 `PWD=` → 在 A 上跑 `create_readonly_login.sql`（`ReadableTablesAndViews = 2`、`OtherDatabasePermissions = 0`）。
2. `.env` 拿掉 `REMINDER_SOURCE=demo` 那一行。
3. `python -m app.reminders_cli --check-gpis` → 两个 `[OK]`（读的是 `GPiS`，帐号不是只读的话系统会拒绝，D59）。
4. `python -m app.reminders_cli` → 明天的名单；和 GPiS 的 Appointment 画面对照人数。

## 6. 登入就自动启动

```powershell
cd C:\Chatbot_Automation
.\deploy\install-autostart.ps1
Start-ScheduledTask -TaskName Chatbot_Automation
```

等 10 秒，浏览器打开 <http://localhost:8000> → 登入画面。把这个网址加进书签 / 桌面捷径。

- 日志：`%LOCALAPPDATA%\Chatbot\logs\`（`start.log` 每次启动、备份、重开的记录；`uvicorn-日期-时间.log` 每次启动的程序日志，留最新 14 个）。
- 备份：`%LOCALAPPDATA%\Chatbot\backup\chatbot-日期.dump`，每次开机一份，留最新 14 份。
  **里面有病人名字和号码**：只留在 B，不复制到 USB、网盘（规则 4）。
- uvicorn 停了（当掉、被关掉）：`start-chatbot.ps1` 等 1 分钟自己重开，最多 3 次。
- 停下本系统（改了 `.env` 要重开、更新之前）：`.\deploy\stop-chatbot.ps1` → `已经停了`；再启动：`Start-ScheduledTask -TaskName Chatbot_Automation`。
  只用 `Stop-ScheduledTask` 不够：uvicorn 可能还在跑。
- 拿掉自动启动：`.\deploy\install-autostart.ps1 -Remove`（会先停下本系统）。

## 7. 装好之后的检查（在 B 上）

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 重新开机，登入 Windows，打开 <http://localhost:8000> | 登入画面（不用开任何视窗） |
| 2 | `start.log` | `备份：…dump`、`uvicorn 启动` |
| 3 | 用 ADMIN 登入 → *Settings → Clinic closures* → *Import public holidays for 2026*，再换 2027 | 各 *Added 11 day(s)*；和 `clinic-workflow.md` 第 1 节的表对照；核对 Hari Raya 的日期 |
| 4 | *Reminders* → 明天 | 名单的人数和 GPiS 一样；家人合并、`*C` 的规则对 |
| 5 | 挑一行按 *Open in WhatsApp* | WhatsApp Desktop 打开**那位病人**的对话、消息已经填好。**不要按 Enter**（试跑期间员工照旧手动发）→ 关掉 |
| 6 | 另一台电脑（例如 A）的浏览器打 `http://<B的IP>:8000` | **打不开**（只听 `127.0.0.1`，D62） |
| 7 | 用 STAFF 帐号登入 | 看得到名单；*Settings* 不能改 |

## 8. 先在开发电脑演练

和 B 一样，只是读 `GPiS_Dev`、用另一个文件夹和数据库，不影响平常开发：

1. **关掉**平常开发用的 uvicorn（port 8000 要空出来）。
2. 照第 2 节做安装包，解压到 `D:\ChatbotRehearsal`（不是仓库的文件夹）。
3. 第 3 节的 3–5 步（但 `pip install -r requirements.txt`：装当时最新的版本来测；全部通过后用这个 venv 的 `pip freeze` 更新 `backend/requirements-lock.txt`）：数据库改叫 `chatbot_rehearsal`（psql：`CREATE DATABASE chatbot_rehearsal OWNER chatbot;`，开发电脑已经有 `chatbot` 这个 role）；
   `pgpass.conf` 的那一行写 `localhost:5432:chatbot_rehearsal:chatbot:密码`（`start-chatbot.ps1` 照 `.env` 的 `DATABASE_URL` 备份哪个数据库）。
4. `.env`：`GPIS_CONNECTION_STRING` 用开发电脑的 `chatbot_reader`（`SERVER=localhost\SQLEXPRESS;DATABASE=GPiS_Dev`）、`GPIS_EXPECTED_DATABASE=GPiS_Dev`、`DATABASE_URL` 指到 `chatbot_rehearsal`。
5. 第 5、6 步（不用接主机 A；`2026-09-02` 当「明天」）。
6. 第 7 节的检查：第 4 项用 `2026-09-02` → Ready 25；第 5 项读 `GPiS_Dev` 时**没有** *Open in WhatsApp*（D44）：`.env` 暂时改 `REMINDER_SOURCE=demo`、`WHATSAPP_ALLOWED_RECIPIENTS=<自己的号码>` → `stop-chatbot.ps1`、`Start-ScheduledTask` → 只有自己号码那一组有按钮 → 试完改回来、再重开一次；第 6 项：`Test-NetConnection <开发电脑的IP> -Port 8000` → `False`、`127.0.0.1` → `True`，手机连同一个 Wi-Fi 打 `http://<开发电脑的IP>:8000` → 打不开。
7. 停止、重开、还原：`Stop-ScheduledTask` 之后 port 8000 **还在**（所以要用 `stop-chatbot.ps1`）；`stop-chatbot.ps1` → port 空了；启动后只关掉 uvicorn（`Stop-Process`）→ 1 分钟后自己回来（`start.log`）；照第 10 节用最新的备份还原 → 备份之后改的资料不见了，其他都在。
8. 演练完（先关掉开在 `D:\ChatbotRehearsal` 里的 PowerShell 和**从那里打开的记事本**，不然文件夹删不掉）：`.\deploy\install-autostart.ps1 -Remove`（会先停下本系统）、`dropdb -h localhost -U chatbot chatbot_rehearsal`（主人是 `chatbot`，不用 `postgres`）、用 `Remove-Item -Recurse -Force` 删掉 `D:\ChatbotRehearsal`、`%LOCALAPPDATA%\Chatbot`（里面的备份有 `GPiS_Dev` 的病人名字；`Remove-Item` 不经过资源回收筒）、`pgpass.conf` 那一行（演练前没有这个档就整个删掉）、桌面的 zip。

### 演练记录（2026-10-12，开发电脑）

Windows PowerShell 5.1、Python 3.11.9、PostgreSQL 18.6、`GPiS_Dev`（`chatbot_reader`）；安装包 `chatbot-36a3fe6.zip`（这个分支的第一个 commit）。

| 步骤 | 结果 |
|---|---|
| 安装包 | ✅ `make-package.ps1` 在 PowerShell 5.1 做出 zip；解压后有 `frontend\dist\index.html`、`backend\.env.example`，**没有** `.env`、备份、资料档 |
| 数据库、pgpass | ✅ `chatbot_rehearsal`；没有 pgpass 时 `psql -w` 被拒（`no password supplied`），加了那一行就连得上 |
| venv、套件 | ✅ `requirements.txt` 装当天最新的版本；`pip freeze` → `backend/requirements-lock.txt`（37 个，都有 Windows + 3.11 的安装档） |
| 建表、帐号 | ✅ `0004`；seed 1 / 14 / 2 / 26 行；`boss`（ADMIN）、`staff1`（STAFF）；假资料名单 Ready 2 个号码 / 3 个预约、Needs staff 3、取消 1、`00:00` 1 |
| 读 `GPiS_Dev` | ✅ `--check-gpis` 两个 `[OK]`；`2026-09-02` Ready 25 / Needs staff 0 |
| 自动启动 | ✅ `install-autostart.ps1` 不用系统管理员；`Running`；**只听** `127.0.0.1:8000`；`start.log` 3 行（中文正常）；备份 42 KB；网页登入成功；PowerShell 视窗只闪一下，没有留着 |
| 只用 `Stop-ScheduledTask` | ⚠️ 工作排程器 `Ready`，但 port 8000 **还在**、还有 1 个 `python.exe`（跑 uvicorn 的那个），网页照样打得开 → 要用 `stop-chatbot.ps1` |
| `stop-chatbot.ps1` | ✅ 停了 1 个 `python.exe`，port 8000 空了，网页打不开 |
| 当掉自己重开 | ✅ 关掉 uvicorn → 11:31:10 `uvicorn 停了` → 11:32:10 `uvicorn 启动`（新的日志档） |
| 第 7 节 1、2 | ✅ 重开机、不开任何视窗 → 登入画面；`start.log` 3 行、新的备份 |
| 3 | ✅ 2026、2027 各 *Added 11 day(s)*，和 `clinic-workflow.md` 第 1 节一样（新装的 `holidays` 0.106） |
| 4 | ✅ `2026-09-02` Ready 25 |
| 5 | ✅ 假资料 + 自己的号码：只有那一组有 *Open in WhatsApp*，WhatsApp Desktop 打开自己的对话、消息填好；改回 `GPiS_Dev` 后没有按钮 |
| 6 | ✅ `Test-NetConnection <局域网IP> -Port 8000` → `False`，`127.0.0.1` → `True`；手机连同一个 Wi-Fi 打不开 |
| 7 | ✅ `staff1` 看得到名单，*Settings* 不能改 |
| 还原（第 10 节） | ✅ 停下 → `pg_restore --clean` 开机那份 → `0` → 之后导入的假期不见了，帐号、名单都在 → 再导入 |
| 清理 | ✅ `-Remove`（停了 1 个 `python.exe`、拿掉排程）；`dropdb` → 查 `chatbot_rehearsal` 是 0；`%LOCALAPPDATA%\Chatbot`、`pgpass.conf`、zip 删掉；`D:\ChatbotRehearsal` 第一次删不掉（还有从那里打开的视窗占着 `backend`），关掉再删 |

演练时找到、已经改好的：

- **只用 `Stop-ScheduledTask` 停不干净**（上表）：加 `deploy/stop-chatbot.ps1`，`install-autostart.ps1 -Remove` 也先停；第 6、8、9 节改用它（D63）。
- **uvicorn 停了要自己重开**：原来靠工作排程器的「失败时重新启动」，它不一定会因为程序停了而重开 → `start-chatbot.ps1` 自己 1 分钟后重开，最多 3 次；每次启动一个日志档，不会盖掉停下来的原因；`PYTHONUTF8=1`，日志的中文存成 UTF-8（D63）。这两项在演练前先改了，演练测过。
- **Python 版本**：文件写 3.12 以上，开发电脑和所有测试其实都是 3.11.9 → B 装 3.11.9；套件装 `requirements-lock.txt`（D63）。
- **备份没有还原的步骤** → 加第 10 节，演练测过。
- 第 3 节第 4 步加 pgpass 的检查；第 5 节先确认 `.env` 指到哪个数据库（演练时 `DATABASE_URL` 还是 `chatbot_dev`，跑之前查到）。
- 开发电脑的 `postgres` 一开始不用密码就连得上（不是 pgpass；`pg_hba.conf` 的档案是正常的），重新读设定后要密码了，但**没有人知道 `postgres` 的密码**：演练不需要它（`chatbot` 自己能删 `chatbot_rehearsal`），之后用系统管理员重设。B 装好后也确认 `postgres` 要密码。

## 9. 以后更新

1. 开发电脑：新的 `chatbot-<commit>.zip`（第 2 节）。
2. B：`C:\Chatbot_Automation\deploy\stop-chatbot.ps1` → `已经停了`；`cd C:\`（PowerShell 在那个文件夹里就改不了名），
   把 `C:\Chatbot_Automation` 改名成 `C:\Chatbot_Automation.old`（要退回时用）。
3. 解压新的到 `C:\Chatbot_Automation`；把旧的 `backend\.env` 复制过来；重新建 venv、`pip install -r requirements-lock.txt`。
4. `alembic upgrade head`（最近一次启动时的备份就是改表之前的那一份；要退回见第 10 节）。
5. `Start-ScheduledTask -TaskName Chatbot_Automation`，跑第 7 节的 1、4 项。没问题再删 `.old`。

## 10. 还原备份（更新失败、数据库坏了）

演练测过（2026-10-12）。用 `chatbot` 帐号（pgpass），不用 `postgres`。**备份之后改的资料会不见**（例：那之后按过的 *Open in WhatsApp*、改过的设定）。

```powershell
C:\Chatbot_Automation\deploy\stop-chatbot.ps1                       # → 已经停了
Get-ChildItem "$env:LOCALAPPDATA\Chatbot\backup" | Sort-Object Name -Descending | Select-Object Name, LastWriteTime
$dump = "$env:LOCALAPPDATA\Chatbot\backup\<上面选的档名>"
& "C:\Program Files\PostgreSQL\<版本>\bin\pg_restore.exe" -h localhost -U chatbot -d chatbot -w --clean --if-exists --no-owner $dump
$LASTEXITCODE                                                        # → 0
```

`--clean` = 先拿掉现在的表，再从备份建回来。更新失败要退回的话，程序也要换回旧的（`C:\Chatbot_Automation.old`，第 9 节）：备份是旧版本的表结构。
然后 `Start-ScheduledTask -TaskName Chatbot_Automation`，跑第 7 节的 1、4 项。
