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

一项一项打勾的清单（要准备、要带的东西，到了先看先问的事，B 不合要求、连不上 A 怎么办，离开前的确认）：[`pc-b-checklist.md`](pc-b-checklist.md)。

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
   - Python **3.11.9**（python.org，Windows installer 64-bit，档名 `python-3.11.9-amd64.exe`，网址 `https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe`）：和开发电脑一样（演练、测试都是 3.11.9；3.11 最后一个有 Windows 安装程序的版本）。
     **不是** python.org 首页的 *Python install manager*（`.msix`），也不是 Microsoft Store 的 Python
   - PostgreSQL **18**（postgresql.org → Windows → EDB installer）：和开发电脑演练的一样
   - ODBC Driver 18 for SQL Server（Microsoft 网站，x64）
4. 想好 B 要用的两个密码（PostgreSQL 的 `postgres`、`chatbot`），存在**自己的密码管理器**，不写在纸上、不放 USB。
   `postgres` 的密码一定要存好：开发电脑演练时发现没有人记得，要用系统管理员才能重设。
   `chatbot_reader` 的密码在 B 上产生（第 5 步）。

## 3. 在 B 上安装程序（只做一次）

用员工平常登入的 Windows 帐号。

1. **Python**：先在 *设定 → 应用* 搜 `Python`，看 B 本来有没有别的 Python。执行 `python-3.11.9-amd64.exe`：
   - B 上**没有**别的 Python：勾 *Add python.exe to PATH*。
   - B 上**已经有**（电脑 B 本来就有 Microsoft Store 的 Python 3.11 和 Python 3.12.0，第 11 节）：**不勾**，不改别人在用的 `python`；第 5 步用完整路径建 venv。
   - 按 *Install Now*（装在 `%LOCALAPPDATA%\Programs\Python\Python311`）。确认：`& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" --version` → `Python 3.11.9`。
   - `python --version` 是 3.11.9 **不够**：Microsoft Store 的 Python 也是 3.11.9，但它在 `WindowsApps` 里，Python 官方说主要给互动用，写入 AppData 的档案会被转到别的地方。B 要用 python.org 的（演练用的就是它）。
2. **ODBC Driver 18**：执行安装程序。确认：
   ```powershell
   Get-OdbcDriver | Where-Object Name -like "*SQL Server*" | Select-Object Name
   ```
   → 有 `ODBC Driver 18 for SQL Server`（GPiS 用的旧版 driver 也会在，不要动它）。
3. **PostgreSQL**：组件只选 *PostgreSQL Server*、*Command Line Tools*（不用 pgAdmin、Stack Builder）；
   `postgres` 的密码用第 2 节准备的；port `5432`；Windows 防火墙问的话**不要**允许公用网络。
   开始菜单 → *SQL Shell (psql)* → 一路 Enter → 打 `postgres` 的密码：
   ```sql
   CREATE ROLE chatbot LOGIN;
   \password chatbot
   CREATE DATABASE chatbot OWNER chatbot;
   \q
   ```
   `\password` 会问两次 `chatbot` 的密码，画面上不显示（密码不出现在指令里）。安装时 `postgres` 打的不是第 2 节准备的密码的话，先 `\password postgres` 换掉，再重新登入一次确认。
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
5. **本系统**：把 zip 解压到 `C:\Chatbot_Automation`（这个位置以后更新也用一样的），`C:\Chatbot_Automation\backend` 要直接在里面（不要多一层 `chatbot-<commit>`）。
   zip 是从网络下载的（不是 USB 带的）：解压后先跑 `Get-ChildItem C:\Chatbot_Automation -Recurse -File | Unblock-File`，不然 `deploy\` 的脚本会被挡。
   ```powershell
   cd C:\Chatbot_Automation\backend      # venv 一定建在 backend 里（start-chatbot.ps1 找 backend\.venv）
   & "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" -m venv .venv   # 完整路径，不靠 PATH
   .\.venv\Scripts\Activate.ps1          # 不让执行的话先跑：Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   python -c "import sys; print(sys.version); print(sys.base_prefix)"   # 3.11.9；路径是 ...\Programs\Python\Python311，不能有 WindowsApps
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
| 5 | 请员工挑一行按 *Open in WhatsApp* | WhatsApp Desktop 打开**那位病人**的对话、消息已经填好。**不要按 Enter**（试跑期间员工照旧手动发）→ 关掉 → 那一行按 *Mark as not sent*（按过就记成已打开，D58，不改回来员工会以为发过了） |
| 6 | 在 B 上：`Test-NetConnection <B的IP> -Port 8000`、`Test-NetConnection 127.0.0.1 -Port 8000` | 第一个 `False`、第二个 `True`（只听 `127.0.0.1`，D62）。不用 A 的浏览器试：A 上只跑只读帐号的脚本（规则 1） |
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
- 开发电脑的 `postgres` 一开始不用密码就连得上（不是 pgpass；`pg_hba.conf` 的档案是正常的），重新读设定后要密码了，但**没有人知道 `postgres` 的密码**：演练不需要它（`chatbot` 自己能删 `chatbot_rehearsal`）；演练完用系统管理员视窗重设好了（`pg_hba.conf` 最前面暂时加两行只给本机 `postgres` 的 `trust` → 重开服务 → `\password postgres` → 改回原来的档案、重开 → 确认要密码）。B 装好后也确认 `postgres` 要密码。

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

## 11. 安装记录（电脑 B）

### 第一天（2026-10-12）

没有带 USB，所以 A 的只读帐号没有建（`.sql` 要带到 A 上跑，A 不开浏览器下载）；B 先用**假资料**（`REMINDER_SOURCE=demo`）装好。安装包是 `main` 的 `chatbot-<commit>.zip`。

| 步骤 | 结果 |
|---|---|
| 带程序过去 | 开发电脑 `make-package.ps1` → 上传 Google Drive、共用链接 → B 的 Edge InPrivate 视窗照着打链接下载（B 上不登入 Google）。从网络下载的档案要 `Unblock-File`（第 3 节第 5 步） |
| B 的规格 | Windows 10 64 位、内存 64 GB、`C:` 空 243 GB、时区 Singapore Standard Time；员工的 Windows 帐号是系统管理员（UAC 只按「是」）；连得到 `pypi.org`；port 8000、5432 空着；WhatsApp Desktop 登入的是诊所的号码（W58 的一部分） |
| B 本来就有 | Python 3.11（Microsoft Store，2024-05）、Python 3.12.0 64-bit（2024-05）、Python Launcher（2024-01）：都不动 |
| ODBC 18、PostgreSQL 18 | ✅ 先装 ODBC 再装 PostgreSQL；安装时 `postgres` 打的不是准备好的密码 → psql `\password postgres` 换成密码管理器的、重新登入确认；`chatbot` 用 `\password` 设 |
| pgpass | ✅ `psql -w` → `chatbot` |
| Python | ⚠️ `python --version` 是 3.11.9，但那是 Microsoft Store 的（路径有 `WindowsApps`）。下载时先拿到 python.org 首页的 *Python install manager*（`.msix`），它跑了一个设定程序，开了「允许超过 260 个字的路径」（整台电脑，重开机后生效；留着，不影响 GPiS），要把它移除（第二天确认）。改装 `python-3.11.9-amd64.exe`：只给这个帐号、**没有**加 PATH；venv 用完整路径建，`sys.base_prefix` 是 `...\Programs\Python\Python311` |
| venv、套件 | ⚠️ venv 第一次建在 `C:\Chatbot_Automation`（不是 `backend`）→ 删掉重建。`pip install -r requirements-lock.txt` → `UnicodeDecodeError`（cp1252）：档案开头的中文说明，英文 Windows 的 pip 读不了；那次用 `$env:PYTHONUTF8 = "1"` 装好；之后档案改成只有 ASCII，加测试 |
| `.env` | 9 行：GPiS 那行先放着（`PWD=` 空的）、`REMINDER_SOURCE=demo` |
| 建表、设置 | ✅ `0004`；seed 1 / 14 / 2 / 26（和演练一样） |
| 帐号 | 诊所要两个**共用**帐号：`admin`（ADMIN）、`staff`（STAFF）。名单上「谁按的」只显示 `Staff`，分不出是哪位员工（D58）；以后要分开，ADMIN 在网页加 |
| 假资料名单 | ✅ Ready 2 个号码 / 3 个预约、Needs staff 3、取消 1、`00:00` 1（和演练一样） |
| 自动启动 | ✅ `install-autostart.ps1`、`Start-ScheduledTask`；`start.log` 3 行（启动、备份、uvicorn 启动） |
| 第 7 节第 6 项 | ✅ B 的局域网 IP → `False`、`127.0.0.1` → `True` |
| `postgres` 要密码 | ✅ `no password supplied` |
| PowerShell 的中文 | B 是英文 Windows：脚本印的中文显示成 `?`、方块；程序本身正常，网页正常 |

还没做（第二天）：

- 第 7 节第 1、2 项（重开机：先请员工关 B 上的 GPiS）、第 3 项（假期 2026、2027 各 11 天，核对 Hari Raya）、第 7 项（`staff` 登入）
- `Get-Content C:\Chatbot_Automation\VERSION.txt` 和开发电脑的 commit 一样（第一天解压前没有对 hash）
- `start.log` 的时间（23:52）和实际时间一样吗
- *设定 → 应用* 已经没有 *Python Install Manager*
- 清理：B 的「下载」（zip、安装程序、`.msix`）；Google Drive 的 zip 和垃圾桶
- 告诉员工：现在的名单是**假资料**，不能拿来发提醒；试跑等接上 A 才开始

下次带 USB：A 的只读帐号（`sql/README.md` 第二步）→ `.env` 第一行填 A 的 IP 和密码、拿掉 `REMINDER_SOURCE=demo` → `stop-chatbot.ps1`、`Start-ScheduledTask` → `--check-gpis` → 第 7 节第 4、5 项 → 员工开始试跑（W42）。
