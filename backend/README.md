# Backend（Phase 2：空档 API；Phase 3：本系统的 PostgreSQL；Phase 4a：Admin Platform 的 API；Phase 5a：WhatsApp；Phase 5b：预约提醒；Phase 6a：AI 之前的准备）

- **Phase 2**：把 `sql/check_available_slots.sql` 的计算搬到 Python（FastAPI），让之后的 WhatsApp 和 AI Agent 可以调用。
  **只读** GPiS，计算规则和 SQL 完全一样；改规则时两边要一起改。
- **Phase 3**：本系统自己的 PostgreSQL（读写）：诊所设置（从代码搬进数据库）、WhatsApp 对话、预约请求。
  每张表的说明见 [`docs/architecture.md`](../docs/architecture.md) 第 4 节。
- **Phase 4a**：员工登录 + Admin Platform 要用的 API（`/api/...`）。网页（4b）在 [`frontend/`](../frontend/README.md)。
- **Phase 5a**：接上 WhatsApp Cloud API：收病人的消息（webhook）、员工在 Admin Platform 回复、显示送达状态。开发时只用 Meta 的测试号码。
- **Phase 5b**（第一步）：预约提醒的名单（只看名单）+ *Open in WhatsApp*，见下面「Phase 5b」。
- **资料保留（A10）**：提醒过了预约日期 90 天就删掉、只留每天的数目，见最后的「资料保留（A10）」。
- **Phase 6a-1**：病人传的 IC / 护照号码存之前遮掉后面 6 位（D69），见最后的「Phase 6a-1」。

| 文件 | 内容 |
|---|---|
| `app/clinic_rules.py` | 诊所设置在程序里的样子（`ClinicRules`）；设置本身存在 PostgreSQL |
| `app/availability.py` | 空档计算（= SQL 第 3–7 节），不连接数据库；本系统 `PENDING` 的请求也算占用（A8，Phase 6a-2a） |
| `app/gpis.py` | 读 `Tbl_CAH_Appointment`：只有一条 `SELECT`；数据库名字不是 `GPIS_EXPECTED_DATABASE` 就拒绝 |
| `app/main.py` | API 入口：`GET /availability`、`GET /health`，加上 `app/api/` 的 Admin API |
| `app/auth.py` | 员工登录：Argon2 加密密码、session cookie、ADMIN / STAFF 权限 |
| `app/api/` | Admin API：登录、对话、预约请求、设置（医生、排班、疗程、假期、请假）、员工账号 |
| `app/whatsapp.py` | WhatsApp Cloud API：检查 webhook 签名、看懂 webhook、发文字消息（只发给允许的号码） |
| `app/whatsapp_check.py` | 检查 WhatsApp 的设定：手机传的消息为什么没送到 webhook（`python -m app.whatsapp_check`） |
| `app/reminders.py` | 提醒名单（Phase 5b）：哪几天、哪些要提醒 / 要员工看 / 不是预约、家人合成一条、消息的文字。不连接数据库 |
| `app/api/reminders.py` | `GET /api/reminders`：给 Reminders 页面的名单；*Open in WhatsApp* 的锁（D54）；记录按过 *Open in WhatsApp*、*NO WA*（D58） |
| `app/db/reminders.py` | `reminders` 表、号码的 opt-out：员工对提醒做过的事（名单本身不存） |
| `app/reminders_cli.py` | 在终端印出名单的摘要（没有名字、号码）；`--check-gpis` 检查 GPiS 的栏位 |
| `app/reminder_demo.py` | 提醒的假资料（`REMINDER_SOURCE=demo`），不连 GPiS 也能试画面 |
| `app/redact.py` | 病人传的 IC / 护照号码：存之前遮掉后面 6 位（D69） |
| `app/db/retention.py`、`app/retention.py` | 资料保留（A10、D67）：删掉预约日期过了 90 天的提醒、只留每天的数目（`python -m app.retention`） |
| `app/webhook.py`、`app/webhook_main.py` | 收 WhatsApp webhook 的小程序（port 8001），开发时只有它经 tunnel 放上网 |
| `app/db/create_staff.py` | 建员工账号（第一个 ADMIN 用这个建） |
| `app/db/demo.py` | 放假资料到 `chatbot_dev`，方便看画面（只能用在 `_dev` 数据库） |
| `app/cli.py` | 在终端印出和 SQL 7a / 7b / 7c 一样格式的结果，方便对照；`PENDING` 的请求印在 7d，`--gpis-only` 只看 GPiS |
| `app/phone.py` | 手机号转成国际格式（例 `60123456789`），WhatsApp 的号码和员工输入的号码才能比对 |
| `app/db/models.py` | 本系统的 15 张表（表结构以这里为准；Phase 4 加了 `staff_sessions`，Phase 5 加了消息的送达状态、`reminders`，A10 加了 `reminder_stats`） |
| `app/db/seed.py` | 设置的初始值（= SQL 第 2 节 + 疗程代码）；`python -m app.db.seed` 写入 |
| `app/db/rules.py` | 从 PostgreSQL 读设置 → `ClinicRules` |
| `app/db/conversations.py` | 收 / 发 WhatsApp 消息、转人工、WhatsApp 24 小时规则 |
| `app/db/customers.py` | 病人；用电话找病人（可能找到几位） |
| `app/db/appointment_requests.py` | 预约请求：`PENDING` → `CONFIRMED` / `REJECTED` / `CANCELLED` |
| `migrations/`、`alembic.ini` | Alembic：建表、改表结构的记录 |
| `tests/` | 测试，全部用假数据 |

## 在开发电脑上安装（Windows，只做一次）

1. 安装 **Python 3.11 或以上**（开发电脑是 3.11.9；python.org，安装时勾选 *Add python.exe to PATH*）。
2. 确认有 **ODBC Driver 18 for SQL Server**。在 PowerShell 执行：
   ```powershell
   Get-OdbcDriver | Where-Object Name -like "*SQL Server*" | Select-Object Name
   ```
   看不到 `ODBC Driver 18 for SQL Server` 的话，到 Microsoft 网站下载安装（搜 "ODBC Driver 18 for SQL Server"）。
3. 在仓库的 `backend` 文件夹里：
   ```powershell
   cd <仓库位置>\backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   copy .env.example .env
   ```
   PowerShell 不让执行 `Activate.ps1` 的话，先跑 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`。
4. 打开 `.env` 检查 `SERVER=`：SSMS 连接时用的服务器名字是什么就填什么（通常是 `localhost\SQLEXPRESS`）。
   `.env` 不会进仓库。

## 安装 PostgreSQL（Phase 3，Windows，只做一次）

1. 到 <https://www.postgresql.org/download/windows/> 下载安装程序（EDB），选 **PostgreSQL 17 或更新的版本**。
2. 安装时：
   - 组件选 *PostgreSQL Server*、*pgAdmin 4*、*Command Line Tools*（*Stack Builder* 不用）。
   - 管理员账号 `postgres` 的密码记在自己的密码管理器里，**不要写进仓库**。
   - Port 用默认的 `5432`。
   - Windows 防火墙如果问要不要让 PostgreSQL 联网，不要勾选"公用网络"：只在自己电脑上用。
3. 开始菜单打开 **SQL Shell (psql)**，前面几项直接按 Enter，再输入 `postgres` 的密码，然后执行
   （密码换成自己想的一个，**只用英文字母和数字**）：
   ```sql
   CREATE ROLE chatbot LOGIN PASSWORD '换成你的密码';
   CREATE DATABASE chatbot_dev OWNER chatbot;
   CREATE DATABASE chatbot_test OWNER chatbot;
   \q
   ```
   `chatbot_dev` 给系统用；`chatbot_test` 给测试用，**每次跑测试都会被清空**。
4. 打开 `backend\.env`，照 `.env.example` 加上 `DATABASE_URL`、`TEST_DATABASE_URL`，`CHANGE_ME` 换成 `chatbot` 的密码。
5. 在 `backend` 文件夹里（先 `.\.venv\Scripts\Activate.ps1`）：
   ```powershell
   pip install -r requirements-dev.txt    # 新的套件：SQLAlchemy、Alembic、psycopg
   alembic upgrade head                   # 在 chatbot_dev 建表
   python -m app.db.seed                  # 写入初始设置
   ```
   `seed` 第一次会印出 `clinic_settings: 新增 1 行`、`doctor_schedules: 新增 14 行`、`doctors: 新增 2 行`、`services: 新增 26 行`。
   再执行一次会说"没有新增"：它只补上没有的设置，不会覆盖员工改过的值。
   以后 `seed.py` 加了新的设置（例 2026-10-06 补上 `ISSUE CROWN`、`ISSUE BRIDGE`），再执行一次就会补上；
   已经在数据库里的设置不会被改，要在 Admin Platform 上改（*Settings*）。

## 使用

每次打开新的 PowerShell 先 `cd backend` 再 `.\.venv\Scripts\Activate.ps1`。

**测试**：

```powershell
pytest
```

`.env` 里有 `TEST_DATABASE_URL` 才会跑 PostgreSQL 的测试（会清空 `chatbot_test`）；没有的话那些测试显示 `skipped`，其他照跑。

**终端对照**（预约读 `GPiS_Dev`，设置读 `chatbot_dev`）：

```powershell
python -m app.cli 2026-09-02 PHANG S+P
```

**启动 API**：

```powershell
uvicorn app.main:app --reload
```

浏览器打开 <http://127.0.0.1:8000/docs>，点 `GET /availability` → *Try it out*，填 `date`、`doctor`、`service` → *Execute*。
只在自己电脑上用：不要加 `--host 0.0.0.0`。

## API 输出

`GET /availability?date=2026-09-02&doctor=PHANG&service=S%2BP`（网址里 `+` 要写成 `%2B`；`/docs` 页面会自动处理）

| 栏位 | 意思 |
|---|---|
| `day_status` | 和 SQL 一样：`OK`、`NEEDS_REVIEW`、`DOCTOR_NOT_WORKING`、`CLINIC_CLOSED`、`DOCTOR_ON_LEAVE`、`OFFDAY_IN_GPIS`、`UNKNOWN_DOCTOR` |
| `bookable` | `day_status = OK` 才是 `true`；`NEEDS_REVIEW` 空档照算，但 AI 不自动推荐 |
| `patients` | 这天 GPiS 里已约的病人数（和 SQL 一样，不含本系统的请求） |
| `requests` | 这天这位医生本系统还在 `PENDING` 的请求，算进了 `booked`（A8）；加 `requests=false` 只看 GPiS（和 SQL 对照用），这里是 `0` |
| `available_30` / `available_60` | 30 分钟 / 1 hour 预约可以开始的时段 |
| `slots` | 每个时段，栏位和 SQL 7b 一样（`booked`、`cap`、`remaining`、`can_30`、`can_60`），多一栏 `requests`（`booked` 里面有几个是请求） |
| `appointments` | 只有加 `debug=true` 才有：每条预约怎么被解读（= SQL 7c，只有 ID，没有名字和 Remarks） |
| `held_requests` | 只有加 `debug=true` 才有：算进去的请求（请求编号、时段、几格），没有病人资料 |

读 GPiS 或本系统的 PostgreSQL 失败时回 `503`，不会把连接字符串或错误细节回给调用方（细节在终端日志里）。

## Admin Platform 的 API（Phase 4a）

### 更新（Phase 3 已经装好的电脑）

在 `backend` 里（先启用 venv）：

```powershell
pip install -r requirements-dev.txt      # 新的套件：argon2-cffi（密码加密）、holidays（公共假期）
alembic upgrade head                     # 0001 -> 0002：加上登录用的 staff_sessions 表
python -m app.db.create_staff boss "Your Name" --admin     # 第一个 ADMIN 账号，密码会问两次
python -m app.db.demo                    # 放假资料（4 段对话、4 个预约请求），方便看
```

`.env` 可以加上 `COOKIE_SECURE=false`（见 `.env.example`；不加也是 false）。上线用 https 时要改成 `true`。

### 试用

启动 `uvicorn app.main:app --reload`，打开 <http://127.0.0.1:8000/docs>：

1. `POST /api/auth/login` → *Try it out*，填 `{"username": "boss", "password": "…"}` → *Execute*。
   浏览器会记住登录（cookie），之后的 API 都可以直接试。
2. `GET /api/conversations`、`GET /api/requests` 看假资料；`POST /api/closures/import-holidays` 填 `{"year": 2026}` 导入公共假期。

| API | 谁能用 | 做什么 |
|---|---|---|
| `/api/auth/login`、`logout`、`me`、`password` | 所有人 | 登录、登出、看自己、改自己的密码 |
| `GET /api/conversations`（`?mode=`）、`/{id}` | STAFF | 对话列表（最近的在前；不填 mode = 没结束的）、完整对话 |
| `POST /api/conversations/{id}/take-over`、`hand-back`、`close` | STAFF | 接手（AI 停止回复）、交回 AI、结束 |
| `POST /api/conversations/{id}/reply` | STAFF | 经 WhatsApp 回复病人（Phase 5a）；病人最后一条消息 24 小时内才能回 |
| `GET /api/requests`（`?status=`）、`POST /{id}/confirm`、`reject`、`cancel` | STAFF | 预约请求（默认 PENDING，先来的在前）；确认时可以填 GPiS 的 AppointmentID |
| `GET /api/reminders`（`?date=`） | STAFF | 预约提醒的名单（Phase 5b，见下面）；不填日期 = 今天要提醒的日期 |
| `POST /api/reminders/opened`、`not-sent`（`{date, phone}`） | STAFF | 按了 *Open in WhatsApp*（重新读 GPiS 确认还在 Ready）/ 没有发出去 |
| `PUT /api/reminders/opt-out`（`{phone, opted_out}`） | STAFF | 这个号码不要提醒（签名表写 NO WA，D55）/ 改回照常提醒 |
| `GET /api/doctors`、`services`、`closures`、`leaves`、`settings` | STAFF | 看设置 |
| 上面这些设置的 `POST` / `PUT` / `PATCH` / `DELETE` | **ADMIN** | 改医生、排班（一次 7 天）、疗程、休息日、请假、每格上限 |
| `POST /api/closures/import-holidays` | **ADMIN** | 预填一年诊所会休的公共假期（全国 + Johor 里挑出来的 10 种 + 1 月 1 日，替代假不算，D61）；农历新年多休的日子要自己加，回教节日是预估日期要核对 |
| `/api/staff` | **ADMIN** | 员工账号：新增、改权限、停用、重设密码（至少要留一个 ADMIN） |

- 员工回复病人：Phase 5a 加上了（见下面「Phase 5a」）。
- 数据库约束挡下的错误值回 `422`，重复的资料回 `409`，回应里的 `rule` 是哪一条约束。
- 登录：密码只存 Argon2 加密的结果；cookie 是 HttpOnly + SameSite=Strict，12 小时后要重新登录；
  员工停用、重设密码后，已经登录的也马上失效。

## 本系统的数据库（Phase 3）

由数据库保证的规则（就算程序有 bug、两个请求同时到，也不会被违反）：

- 一个 WhatsApp 号码同时只有一段没结束的对话；同一条 WhatsApp 消息只存一次（WhatsApp 有时会送两次）。
- 时间都在 30 分钟的格上；排班的开始 ≤ 最后一格；午休开始 < 午休结束；每格上限只能是 1–3。
- 疗程代码、医生 ID 一律大写（`availability.py` 会把输入转成大写再比对）。

程序里的规则（`app/db/conversations.py`、`app/db/appointment_requests.py`）：

- 员工接手（`HUMAN`）后，AI 不能回复；员工在 `BOT` 模式的对话里回复，就等于接手。
- 预约请求只能 `PENDING` → `CONFIRMED` / `REJECTED` / `CANCELLED`，或 `CONFIRMED` → `CANCELLED`。

### 改表结构的步骤

1. 改 `app/db/models.py`。
2. `alembic revision --autogenerate --rev-id 0002 -m "说明改了什么"`，打开 `migrations/versions/` 里新的文件检查：
   - autogenerate **看不到 CHECK 的改动**，要自己加 `op.create_check_constraint(...)` / `op.drop_constraint(...)`；
   - 新增 enum 栏位时，它会把同一个 CHECK 多写两次（`sa.CheckConstraint("... IN (...)")`）：删掉，
     只留 `sa.Enum(..., create_constraint=True)`。
3. `alembic upgrade head`
4. `pytest`：`tests/test_db_migrations.py` 会比较 migration 建出来的表和 `models.py` 是否一模一样（连 CHECK、index 都比）。

## 对照 Phase 1（Phase 2 完成的条件）

用 `sql/README.md` 测试记录里的日期，同一天分别跑 SQL 和 `python -m app.cli`，两边的 7a、7b、7c 必须完全一样
（Phase 6a-2a 之后：SQL 只读 GPiS，所以对照时在指令后面加 `--gpis-only`，7b 最后一栏 `Requests` 都是 `0`）：

| # | 指令 |
|---|---|
| 0 | `python -m app.cli 2026-10-09 PHANG S+P` |
| T1 | `python -m app.cli 2026-09-01 PHANG S+P` |
| T2 | `python -m app.cli 2026-09-03 GOH S+P` |
| T3 | `python -m app.cli 2026-09-03 PHANG S+P` |
| T4 | `python -m app.cli 2026-09-01 GOH S+P` |
| T6 | `python -m app.cli 2026-09-02 PHANG S+P` |
| T7 | `python -m app.cli 2026-09-02 PHANG C/UP` |
| T8 | `python -m app.cli 2026-09-09 PHANG S+P` |
| T9 | `python -m app.cli 2026-09-18 GOH S+P` |
| T10 | `python -m app.cli 2026-09-30 PHANG S+P` |

7c 会多一栏 `Occupies`（算不算病人），SQL 没有这栏，其余应该一样。
输出没有病人资料，可以直接贴回来；有不一样的地方，贴那一天两边的结果。

## 对照记录（2026-10-05，`GPiS_Dev` = 2026-09-28 的快照）

开发电脑（Windows、Python 3.11.9、ODBC Driver 18）连 `GPiS_Dev`，`python -m app.cli` 的结果和 `sql/README.md` 的 Phase 1 测试记录逐一对照：

| # | 日期 / 医生 / 疗程 | 结果 |
|---|---|---|
| 0 | 2026-10-09 PHANG S+P | ✅ `OK`，2 人；12:00、12:30 `BREAK`；16:30 `can_60 = 1` |
| T1 | 2026-09-01 PHANG | ✅ `DOCTOR_NOT_WORKING`，没有时段 |
| T2 | 2026-09-03 GOH | ✅ `DOCTOR_NOT_WORKING` |
| T3 | 2026-09-03 PHANG S+P | ✅ `OK`，15 人；`can_60` 只在下一格也空时为 1 |
| T4 | 2026-09-01 GOH S+P | ✅ 8 人；午休 12:00、12:30；15:30 `can_60 = 1` |
| T6 | 2026-09-02 PHANG S+P | ✅ 25 人；09:00、11:30、15:30 满 3 人；09:30、11:00、15:00、16:00 `cap = 2` |
| T7 | 2026-09-02 PHANG C/UP | ✅ 全部 `cap = 2` |
| T8 | 2026-09-09 PHANG S+P | ✅ 25 人；16:00、16:30 `LONG APPT`；17:00 有员工另排的 1 人 |
| T9 | 2026-09-18 GOH | ✅ `OFFDAY_IN_GPIS`，全部 `remaining = 0` |
| T10 | 2026-09-30 PHANG S+P | ✅ `NEEDS_REVIEW`，4 人；11:00 的诊所联系人记录不算 |

结论：Python 版和 SQL 版结果一致，Phase 2 完成。

## Phase 3 完成的条件

在开发电脑上：

1. `pytest` → `104 passed`，**没有 skipped**（PostgreSQL 的测试都跑了）。
2. 用上面 10 个测试日期跑 `python -m app.cli`，结果和"对照记录"完全一样：设置改成从 PostgreSQL 读，结果不能变。

云端容器里的记录（2026-10-05，PostgreSQL 16、Python 3.11、只用假数据）：`pytest` 104 个通过；
换成最低版本（SQLAlchemy 2.0、Alembic 1.13、psycopg 3.2）也是 104 个通过。

### Phase 3 对照记录（2026-10-05，开发电脑：Windows、PostgreSQL 18、`GPiS_Dev` = 2026-09-28 的快照）

- `alembic upgrade head` → `alembic current` 显示 `0001 (head)`；`python -m app.db.seed` 写入初始设置。
- `pytest`：**104 passed，没有 skipped**（PostgreSQL 的 40 个测试都在开发电脑上跑过）。
- 10 个测试日期（设置从 `chatbot_dev` 读）的 7a、7b 和 Phase 2 对照记录**完全一样**：

| # | 日期 / 医生 / 疗程 | 结果 |
|---|---|---|
| 0 | 2026-10-09 PHANG S+P | ✅ `OK`，2 人；12:00、12:30 `BREAK`；16:30 `Can60 = 1` |
| T1 | 2026-09-01 PHANG | ✅ `DOCTOR_NOT_WORKING`，没有时段 |
| T2 | 2026-09-03 GOH | ✅ `DOCTOR_NOT_WORKING` |
| T3 | 2026-09-03 PHANG S+P | ✅ `OK`，15 人；`Can60` 只在下一格也空时为 1 |
| T4 | 2026-09-01 GOH S+P | ✅ 8 人；午休 12:00、12:30；15:30 `Can60 = 1` |
| T6 | 2026-09-02 PHANG S+P | ✅ 25 人；09:00、11:30、15:30 满 3 人；09:30、11:00、15:00、16:00 `Cap = 2` |
| T7 | 2026-09-02 PHANG C/UP | ✅ 全部 `Cap = 2` |
| T8 | 2026-09-09 PHANG S+P | ✅ 25 人；16:00、16:30 `LONG APPT`；17:00 有员工另排的 1 人 |
| T9 | 2026-09-18 GOH | ✅ `OFFDAY_IN_GPIS`，全部 `Remaining = 0` |
| T10 | 2026-09-30 PHANG S+P | ✅ `NEEDS_REVIEW`，4 人（诊所联系人 ID 从 PostgreSQL 读出，判断正确） |

结论：设置搬进 PostgreSQL 之后，空档结果和 Phase 2 一致，Phase 3 完成。

## Phase 4a 完成的条件

在开发电脑上：

1. `alembic upgrade head` 之后 `alembic current` 显示 `0002 (head)`。
2. `pytest` → `131 passed`，没有 skipped。
3. 照「试用」登录 `/docs`，看得到假资料；用 STAFF 账号改设置会被拒绝（403）。

云端容器里的记录（2026-10-05，PostgreSQL 16、只用假数据）：`pytest` 131 个通过；在 `chatbot_dev` 实际跑过
升级 → 建 ADMIN → 放假资料 → 用 curl 登录、看对话和请求、导入 2026 年公共假期（23 天）。

### Phase 4a 测试记录（2026-10-05，开发电脑：Windows、PostgreSQL 18）

- `alembic upgrade head` → `0002 (head)`；`create_staff` 建 ADMIN；`demo` 放假资料。
- `pytest`：**131 passed，没有 skipped**。
- `/docs` 试用全部正常：

| # | API | 结果 |
|---|---|---|
| 1 | `POST /api/auth/login` | ✅ 200，`role = ADMIN` |
| 2 | `GET /api/conversations` | ✅ 3 段没结束的假对话（Demo SG 是 HUMAN） |
| 3 | `GET /api/requests` | ✅ 3 个待确认请求（Demo Kid A、Demo Kid B、Demo Patient） |
| 4 | `POST /api/closures/import-holidays`（2026） | ✅ 导入 23 天公共假期 |
| 5 | `GET /api/closures?year=2026` | ✅ 列出导入的假期 |

另外：`POST /api/closures` 的 `closure_date` 只填 `"2026"` 回 `422`（日期格式检查有效）。

结论：Phase 4a 完成。

## Phase 5a：WhatsApp（收消息、员工回复）

```
病人的手机 ──WhatsApp──→ Meta ──webhook（https）──→ tunnel ──→ webhook 小程序（port 8001）──→ PostgreSQL
                                                                                                │
员工 ──Admin Platform（5173）──→ Admin API（port 8000）──Cloud API──→ Meta ──→ 病人的手机        │
                                       └──────────────── 读、写同一个 chatbot_dev ───────────────┘
```

- **开发只用 Meta 的测试号码**（D34）：它只能和自己登记的最多 5 个号码互传，真的病人碰不到它。
  `WHATSAPP_ALLOWED_RECIPIENTS` 只填自己的手机：就算程序有 bug，也发不到别的号码（例 demo 的假号码会被拒绝）。
- **网上只看得到 webhook**（D35）：Meta 要能连到一个公开的 https 网址。用 tunnel 把 **port 8001 的 webhook 小程序**放上网；
  Admin API（8000）、`/availability`（读 `GPiS_Dev`）、`/docs` 都不在这个小程序里。不测的时候把 tunnel 关掉。
- 每个 webhook 都检查 Meta 的签名（`X-Hub-Signature-256`，用 App Secret 算）：不是 Meta 送来的一律不处理。
- 还没有 AI（`AI_REPLIES_ENABLED=false`）：病人的新对话直接交给员工（*Needs staff*），第一个回复的员工负责（D37）。
- 员工回复：先经 WhatsApp 发出，WhatsApp 收下了才存（D36）；之后 *Sending…* → *Sent* → *Delivered* → *Read*，送不到显示原因。
- 病人传的照片、语音、文件先不下载，只显示 `[Image]` 等（D38）。
- 日志不记消息内容和电话号码。

### 更新（Phase 4 已经装好的电脑）

在 `backend` 里（先启用 venv）：

```powershell
pip install -r requirements-dev.txt      # httpx 搬到 requirements.txt（本来就装了）
alembic upgrade head                     # 0002 -> 0003：消息的送达状态
pytest                                   # 应该 183 passed，没有 skipped
```

### 在 Meta 建测试用的 App（只做一次，用自己的 Facebook 帐号，**不要用诊所的**）

Meta 的画面常改，名字可能不完全一样；找不到时看 App Dashboard 里 WhatsApp 的 *Quickstart*。

1. 到 <https://developers.facebook.com/>，用自己的 Facebook 帐号登录，注册成为开发者。
2. *My Apps* → *Create App*，用途选 WhatsApp（*Connect with customers through WhatsApp*）。
   要选 Business portfolio 的话，自己建一个测试用的（例 `Chatbot Test`），**不要用诊所的**（D34）：
   开发和诊所的帐号分开，以后诊所的号码接上时，开发用的 App 碰不到真的病人消息；测试出错也不会连累诊所的帐号。
3. App 里 *WhatsApp* → *API Setup*（2026 年的新画面没有这个名字：左边 *Connect on WhatsApp* → *Basic setup* → **Step 1. Try it out**，下面都叫 *API Setup*）：
   - 同一页有 **WhatsApp Business Account ID**（测试号码所在的 *Test WhatsApp Business Account*，`--waba` 要用的就是它）。
   - 会有一个**测试号码**（*From*），下面是它的 **Phone number ID**。
   - *To* → *Manage phone number list* → 加上**自己的手机号码**（WhatsApp 会传验证码来）。
   - 按 *Send message*，手机应该收到 `hello_world`（确认测试号码能用）。
   - *Generate access token*：很快就失效（2026-10-07 实测大约 1 小时），只用来先试一下；测试时用第 4b 步的 token。
4. *App settings* → *Basic* → *App secret* → *Show*。

   **4b. System User 的 access token**（60 天，D39）：在**自己的测试 Business portfolio**（第 2 步建的，不是诊所的）：
   - <https://business.facebook.com/> → 选测试的 portfolio → *Settings* → *Users* → *System users* → *Add*：
     名字例 `chatbot-dev`，角色选 *Employee*（权限最小；之后 *Generate token* 列不出 App 的话，再改成 *Admin*）。
   - **先** *Assign assets*（**再** *Generate token*，顺序不能反）：这个 System user → *Assign assets*：
     - *Apps* → 测试 App → *Full control* → **Manage app** 打开 → *Assign*；
     - *WhatsApp accounts* → **Test WhatsApp Business Account**（测试号码的那个；ID 和第 3 步的一样）→ *Full control* → *Manage WhatsApp Business Accounts* 打开 → *Assign*。
     只加这两个。System user 的页面上 *Assigned assets* 要看得到这两个。
   - 重新整理页面（F5）→ *Generate token* → 选测试 App → *Token expiration* 选 **60 days**（不要选 *Never*）
     → 只勾 `whatsapp_business_messaging`、`whatsapp_business_management` → *Generate token*。
   - *Generate token* 显示 *No permissions available*（*Assign an app role to the system user*）：System user 在 App 上还没有角色。
     回到上面把 App 的 **Manage app** 打开；还是不行，把 System user 的角色改成 *Admin*，F5 再试。
   - token 只显示一次：直接贴进 `.env` 的 `WHATSAPP_ACCESS_TOKEN`，不要存在别的地方。
   - 60 天后，或怀疑 token 外泄：回到这个 System user 按 *Revoke tokens*，再 *Generate token* 一个新的。
5. 打开 `backend\.env`，照 `.env.example` 加上 WhatsApp 那一段：
   - `WHATSAPP_VERIFY_TOKEN`：自己想一串英文字母和数字（第 7 步要填一样的）。
   - `WHATSAPP_ACCESS_TOKEN`：第 4b 步的 token。
   - `WHATSAPP_APP_SECRET`、`WHATSAPP_PHONE_NUMBER_ID`：第 4、3 步的值。
   - `WHATSAPP_ALLOWED_RECIPIENTS`：**只填自己的手机号码**，例 `60123456789`。
   token、secret 只写在 `.env`，不要贴到对话或截图里（截图时遮住）。
6. 装 tunnel 工具 cloudflared（只做一次）：`winget install --id Cloudflare.cloudflared`，装好后重开 PowerShell。
7. 照下面「使用」开 4 个视窗，复制 cloudflared 印出的 `https://….trycloudflare.com`。
   **先自己用浏览器试**（等 cloudflared 印出网址后 30 秒左右）：
   - `https://….trycloudflare.com/health` → 应该看到 `{"status":"ok"}`（tunnel 和视窗 2 都正常）
   - `https://….trycloudflare.com/webhook?hub.mode=subscribe&hub.verify_token=你的暗号&hub.challenge=hello`
     → 应该只看到 `hello`（暗号和 `.env` 一样）
   两个都对了，再到 Meta App → *WhatsApp* → *Configuration*（或 *Quickstart* 的 *Configure Webhooks*）→ *Edit*：
   - *Callback URL*：`https://….trycloudflare.com/webhook`（**最后一定要有 `/webhook`**）
   - *Verify token*：和 `WHATSAPP_VERIFY_TOKEN` 一样
   - 按 *Verify and save*，再到 *Webhook fields* 把 `messages` 打开（*Subscribe*）。
8. **把 App 发布（Publish / Live）**：App 没发布时，Meta 只送 dashboard 上按 *Test* 的假 webhook，
   **你手机传的消息不会送来**（画面上的黄色提示）。
   - 先要有一个公开的隐私政策网址（*Privacy Policy URL*）：例如把隐私政策的文字放在 GitHub Gist，复制网址。
   - *App settings* → *Basic* → 填 *Privacy Policy URL*（有要求的话也选 *Category*、放 *App icon*）→ *Save changes*。
   - 按画面上的 *Publish*（或把 *App Mode* 从 *Development* 改成 *Live*）。
   - 发布不会让别人碰到测试号码：它仍然只能和你登记的号码互传（D34）。
9. **跑设定检查**（视窗 2、3 开着；在另一个 PowerShell，`cd backend`、启用 venv）：
   ```powershell
   python -m app.whatsapp_check
   ```
   它逐项问 Meta，再经 tunnel 打一次视窗 2，每项印 `[OK]` 或 `[!!]` 和怎么改。输出没有 token、secret，电话号码只留最后 4 位，可以贴到对话里。
   - 最常见的 `[!!]`：**App 没有订阅测试的 WhatsApp Business Account（WABA）**。没订阅时，Meta 只送 dashboard 的 *Test*，手机传的消息不会送来。
     执行 `python -m app.whatsapp_check --subscribe` 帮你订阅（不用自己打 `curl` 指令：PowerShell 会把打过的指令连 token 存进历史纪录）。
   - 全部 `[OK]` 再用手机传一条消息。

### 使用（4 个 PowerShell 视窗）

```powershell
# 1. Admin API（和以前一样）
uvicorn app.main:app --reload

# 2. webhook 小程序（另一个 port）
uvicorn app.webhook_main:app --reload --port 8001

# 3. tunnel：只把 8001 放上网（不要指到 8000）
cloudflared tunnel --url http://localhost:8001

# 4. 网页（在 frontend 里）
npm run dev
```

- 视窗 1、2 都要先 `cd backend`、启用 venv。改了 `.env` 要重开视窗 1、2。
- cloudflared 每次重开，网址都会变：要回到 Meta 的 *Configuration* 改 *Callback URL* 再 *Verify and save*。
- 测完把视窗 3（tunnel）关掉（`Ctrl + C`）。

### 常见问题

先跑 `python -m app.whatsapp_check`（第 9 步），它会说哪一项不对。手机传了消息之后，看视窗 2 的最后几行：

| 视窗 2 显示 | 原因、怎么办 |
|---|---|
| 什么都没有（没有 `POST /webhook`） | Meta 没有送来：App 没订阅 WABA（`--subscribe`）；或 cloudflared 重开过、网址变了（改 *Callback URL*）；或 App 没发布（第 8 步） |
| `POST /webhook … 401` + `webhook 签名不对` | `WHATSAPP_APP_SECRET` 不对，或改了 `.env` 没重开视窗 2 |
| `POST /webhook … 503` | 视窗 2 没读到 `WHATSAPP_APP_SECRET`、`WHATSAPP_PHONE_NUMBER_ID`：填好 `.env`、重开视窗 2 |
| `webhook 是给另一个号码 ID（…）的` | `WHATSAPP_PHONE_NUMBER_ID` 填错（填成电话号码或 WABA ID）：改成 *API Setup* 上的 *Phone number ID*，重开视窗 1、2 |
| `webhook：1 条新消息` + `POST /webhook … 200` | 已经存进数据库：等 15 秒（*Conversations* 的 *Open* 或 *Needs staff* 分页） |
| `POST /webhook … 500` | 看上面的错误；多半是 PostgreSQL 没开 |

手机上的两个灰勾只表示 WhatsApp 收下了，**不表示 Meta 有送 webhook**。视窗 2 的日志不印电话号码和消息内容，暗号（`hub.verify_token`）印成 `***`：可以直接贴到对话里。

| 情况 | 原因、怎么办 |
|---|---|
| Meta：*The callback URL or verify token couldn't be validated* | *Callback URL* 最后少了 `/webhook`；或暗号和 `.env` 不一样；或改了 `.env` 没重开视窗 2。先照第 7 步用浏览器试 |
| 浏览器试 `/health` 看到 Cloudflare 的错误页（例 1033、502） | 视窗 2（port 8001）没开，或 cloudflared 指错 port |
| 试 `/webhook?...` 看到 `Wrong verify token` | 网址里的暗号和 `.env` 不一样；改了 `.env` 要重开视窗 2 |
| 试 `/webhook?...` 看到 `WHATSAPP_VERIFY_TOKEN is not set` | `.env` 没有这一行，或视窗 2 在 `.env` 加好之前就开了 |
| Meta 的 *Test* 按钮送得到，手机传的消息送不到 | App 没订阅 WABA（第 9 步：`python -m app.whatsapp_check --subscribe`）；或 App 还没发布（第 8 步） |
| 视窗 2 出现 `401` | `WHATSAPP_APP_SECRET` 填错（签名对不上） |
| 回复时红字 *There was a problem with the access token or permissions …*、*Authentication Error*（code 190、10、200 等） | 视窗 1 用的 token 过期了或是旧的：视窗 1 只在启动时读 `.env`。换成第 4b 步的 System User token → 更新 `.env` → **重开视窗 1** → 跑 `python -m app.whatsapp_check` → 再回复。*API Setup* 按出来的 token 大约 1 小时就失效 |
| 回复时红字 *… not in allowed list*（code 131030） | 收件人不在 Meta 测试号码的 *To* 名单：*API Setup* → *Manage phone number list* 加上自己的号码 |

### Phase 5a 完成的条件（在开发电脑上测试）

1. `alembic current` → `0003 (head)`；`pytest` → **183 passed**，没有 skipped。
2. `frontend` 里 `npm test` → **35 passed**；`npm run build` 成功。
3. 照「使用」开 4 个视窗，在 Meta 按 *Verify and save* 成功；`python -m app.whatsapp_check` 全部 `[OK]`。
4. 照下面的清单做一次：

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 用手机 WhatsApp 传 `Hi, I want to book scaling` 给测试号码 | 15 秒内 Admin Platform *Conversations* 多一段对话（*Needs staff*），名字是你的 WhatsApp 名字；原因 *AI replies are not turned on yet* |
| 2 | 在这段对话下面输入回复 → *Send* | 手机收到；画面上这条消息显示 *Sending…* → *Delivered*；在手机上打开后变 *Read*；对话显示由你负责 |
| 3 | 输入回复后按 `Ctrl + Enter` | 一样送出 |
| 4 | 用手机传一张照片（加一句说明） | 画面显示 `[Image] 说明` |
| 5 | 把 `.env` 的 `WHATSAPP_ALLOWED_RECIPIENTS=` 暂时改成空的 → 重开视窗 1 → 在你自己的对话回复 `Hello`；做完改回来、再重开视窗 1 | 红字 *This number is not in WHATSAPP_ALLOWED_RECIPIENTS*；手机收不到（允许名单这道保险有效） |
| 6 | 浏览器打开 `https://….trycloudflare.com/docs` 和 `…/api/auth/me` | 都是 `{"detail":"Not Found"}`：网上只看得到 webhook |
| 7 | 视窗 2 的日志 | 只有 `POST /webhook … 200`、`GET /webhook?…hub.verify_token=***…`，没有消息内容、电话号码和暗号 |

截图只用自己手机和假资料的对话；token、secret、App 的画面要遮住。

### 云端容器的测试记录（2026-10-06，PostgreSQL 16、只用假资料、不连 Meta）

- `pytest` → 161 passed（新增 30 个：webhook、签名、发消息、员工回复、送达状态、migration 0003）。
- 在 `chatbot_dev` 跑过整个流程，自己扮演 Meta：
  - 用签了名的假 webhook 送进病人的消息：新对话转给员工，重送的同一条只存一次，签名不对回 `401`、不存。
  - 网页回复时，Cloud API 换成本机假的 Graph API：收到的网址、token、内容都正确。
  - 假的 status webhook 把消息变成 *Read*，*failed* 时显示原因。
  - 不在 allowlist 的号码被拒绝，根本没发出去。
  - webhook 小程序的 `/docs`、`/api/...` 都是 404；日志里没有电话号码和消息内容。

### 云端容器的测试记录（2026-10-07：手机的消息没送到 webhook，加设定检查）

- 用真的 uvicorn（port 8001）+ 签了名的假 webhook 走一次：存成 *Needs staff*；签名不对回 `401`；号码 ID 不对印出警告。本系统这一段没问题，所以是 Meta 的设定或 tunnel。
- 新增 `python -m app.whatsapp_check`：假的 Graph API + 假的 tunnel（后面接真的 webhook 小程序）测了 12 种情况
  （全部正确、没订阅 WABA、`--subscribe`、App secret 错、tunnel 网址变了、网址少 `/webhook`、没订阅 `messages`、号码 ID 错、改了 `.env` 没重开视窗 2、token 失效、`.env` 没填、自我测试不存任何东西）。
- 视窗 2 的 access log 不再印出暗号（`hub.verify_token=***`）。
- `pytest` → 174 passed。

### 云端容器的测试记录（2026-10-07：开发电脑清单第 1 项通过；第 2 项回复被拒，红字是 access token 的问题）

- 原因：发消息的是视窗 1，它只在启动时读 `.env`；设定检查只问 Meta 的读取 API，所以没发现视窗 1 的 token 过期 / 是旧的，或 token 没有发消息的权限。
- 设定检查加上：token 有没有 `whatsapp_business_messaging`、能不能用这个 WABA 发消息、1 小时内会不会失效；提醒换了 token 要重开视窗 1。
- 回复失败的红字加上 Meta 的错误代码（例 `(code 190)`）；token 的问题直接说要换 token、重开 Admin API。
- `pytest` → 180 passed。

### 开发电脑的测试记录（2026-10-07，Windows、PostgreSQL 18、Meta 测试号码 + 自己的手机）

- `alembic current` → `0003 (head)`；`pytest` → 183 passed，没有 skipped；`npm test` → 35 passed；`npm run build` 成功。
- `python -m app.whatsapp_check`：没有 `[!!]`（System User 的 token 没列出 WABA，订阅那一项跳过；手机的消息送得到，表示有订阅）。
- 清单第 1–7 项全部通过：收消息、回复（*Delivered* → *Read*）、`Ctrl + Enter`、照片 → `[Image] 说明`、
  允许名单清空时红字且手机收不到、tunnel 上 `/docs` 和 `/api/auth/me` 都是 Not Found、视窗 2 的日志找不到消息内容、电话号码和暗号。
- *API Setup* 按出来的 token 大约 1 小时就失效（回复显示 *Authentication Error*），所以改用 System User 的 token（第 4b 步，D39）。
- 设定检查：System User 的 token 不能自己问 `debug_token`，改用 App 的身份再问；失效时间超过 2 天显示天数；找不到 WABA 时印出 token 看得到哪些 WABA；token 没列出 WABA（System User 的 token 常常这样）时跳过订阅那一项，不算 `[!!]`。云端 `pytest` → 183 passed。

结论：Phase 5a 完成。

## Phase 5b：预约提醒（第一步：只看名单、Open in WhatsApp）

设计见 [`docs/architecture.md`](../docs/architecture.md) 第 8 节、D40–D54。这一步做的是上线三步里的第 1、2 步（8.1）：

- Admin Platform 多了 **Reminders** 页面：系统从 GPiS 读「明天」的预约（明天放假就连后天，W34），排好名单。
  - **Ready**：可以发的。每个号码一张卡，家人合成一条（`NAME: A & B`，D49），消息照诊所现在的原文（8.5）。
  - **Needs staff**：不确定的，写明原因：没有 `*C`、没有手机号码、固网、状态不明、诊所联系人、那天休息、医生请假、时间在半夜（打错）等（8.3）。
  - **Not appointments**：取消、OFF DAY、`00:00` 的待办，只显示数量。
- **Open in WhatsApp**（D54）：打开 WhatsApp Desktop 里那位病人的对话，消息已经填好，员工按 Enter 发出。
  读 `GPiS_Dev` 或假资料时，**只有 `WHATSAPP_ALLOWED_RECIPIENTS` 里写出来的号码**才有这个按钮（写 `*` 也不算）。
- 还没有做：系统自己发（要 5c）。按过 *Open in WhatsApp* 第一步只记在画面上；**第二步**记进 `reminders` 表、加了 *NO WA*（见下面「Phase 5b 第二步」）。
- 第一步没有改数据库。

### 更新（Phase 5a 已经装好的电脑）

在 `backend` 里（先启用 venv）：

1. `pytest` → **261 passed**（新增 78 个），没有 skipped。
2. 打开 `.env`，照 `.env.example` 加上 `REMINDER_CLINIC_NAME`、`REMINDER_CLINIC_NAME_EN`、`REMINDER_BRANCH`（诊所现在原文里的名字、分行）。
   **只写在 `.env`**，不写进仓库。没有填的话，消息里显示 `<诊所名>` 等。
3. 在 `frontend` 里 `npm test` → **41 passed**；`npm run build` 成功。

### 先检查 GPiS 的栏位（只做一次）

（`--check-gpis` 也会检查连线的帐号是不是只读的，见 `sql/README.md`「只读帐号」、D59。）

手机号码是从 `Qry_CAH_Appointment` 用 `AppointmentID` 对上的（统计 B10、B11 用过它的 `HPNo`），但还没确认这个视图有没有 `AppointmentID`：

```powershell
python -m app.reminders_cli --check-gpis
```

- `[OK] GPiS_Dev 有提醒名单要用的全部栏位。` → 继续。
- `[!!] GPiS 少了这些栏位` → 把那几行贴回来（只有栏位名字，没有病人资料），程序要改。

### 使用

**终端**（输出没有名字、号码、Remarks：号码只印代号 `#1`、`#2`，可以直接贴回来）：

```powershell
python -m app.reminders_cli                 # 今天要提醒的日期
python -m app.reminders_cli 2026-09-02      # 拿 GPiS_Dev 的某一天当「明天」
```

**网页**：开视窗 1（`uvicorn app.main:app --reload`）和网页（`npm run dev`），选单 **Reminders** → *Appointment date* 选日期 → **Show**。

**假资料**（试 *Open in WhatsApp* 用）：

1. `backend/.env` 加一行 `REMINDER_SOURCE=demo`（前面**不要有 `#`**；`.env.example` 里那行是注释掉的）；
   `WHATSAPP_ALLOWED_RECIPIENTS` 填自己的手机（`60` 开头，只写数字）。
2. 视窗 1 按 `Ctrl + C` 停掉，再执行一次 `uvicorn app.main:app --reload`。**`--reload` 只看 `.py`，改 `.env` 不会自己重开。**
3. 检查：`python -m app.reminders_cli` 第一行是 `Source: Demo data`；网页上方写 `read from Demo data`（还是 `GPiS_Dev` = 第 1、2 步没生效）。

每一天都是 Demo Patient A–H：A、B（你的手机）合成一条、C 没有 `*C`、D 有 `*C`、E 固网、F 没有号码、G 取消、H `00:00`。
试完把 `REMINDER_SOURCE` 删掉，同样 `Ctrl + C` 再开视窗 1。

### 注意（病人资料）

- 读 `GPiS_Dev` 时，**页面上是真的病人名字和号码**（只在自己电脑上，和打开 GPiS 一样）。截图要遮住；消息预览里也有名字，不要贴给 AI。终端的摘要可以贴。
- 读 `GPiS_Dev` 时没有 *Open in WhatsApp*（允许名单只填自己的手机，不要填病人的号码）。
- 日志只记数量（`提醒名单：1 天，可以发 2 个号码，要员工看 3 个`），没有名字、号码。

### Phase 5b 第一步完成的条件（在开发电脑上测试）

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | `pytest`；`frontend` 里 `npm test`、`npm run build` | 261 passed、没有 skipped；41 passed；`✓ built` |
| 2 | `python -m app.reminders_cli --check-gpis` | `[OK]`（不是的话贴回 `[!!]` 那几行） |
| 3 | `python -m app.reminders_cli 2026-09-02`（T6，忙的一天），和 GPiS 那天的 Appointment 画面对照 | READY + NEEDS_STAFF 的预约数 = 那天的病人数（不算取消、`00:00`、OFF DAY）；抽 3 个看时间、医生对不对；同一个号码的家人是同一个 `#` |
| 4 | `python -m app.reminders_cli 2026-09-18`（T9） | *Not appointments* 有 `OFF DAY record`；PHANG 的照常在 READY。GOH 那天整天被 OFF DAY 挡住，**没有病人**（和 Phase 2 的 T9 一样）；有的话会在 NEEDS_STAFF：`GPiS has an OFF DAY record for Dr GOH`（单元测试有测） |
| 5 | `python -m app.reminders_cli 2026-09-30`（T10） | 诊所联系人那条（`1130 FIRST APPT`）在 NEEDS_STAFF：`Booked under the clinic's own contact` |
| 6 | `python -m app.reminders_cli 2026-10-09`（快照之后） | 状态是 `Confirmed` |
| 7 | 网页 Reminders → 选 2026-09-02 → Show | 黄色 *Preview only … read from GPiS_Dev*；**没有** *Open in WhatsApp*；*Needs staff* 写明原因 |
| 8 | 假资料（上面「使用」）：Reminders | 上方写 `read from Demo data`；Demo Patient A & B 一张卡、有 *Open in WhatsApp*；D 有 `*C` 在 Ready 但没有按钮（不在允许名单）；C、E、F 在 *Needs staff*；*Not appointments* 2 |
| 9 | 按 A & B 的 *Open in WhatsApp* | WhatsApp Desktop 打开你自己的对话，消息已经填好（不想发就不要按 Enter）；卡片显示 *Opened* |
| 10 | 浏览器的历史记录（`Ctrl + H`） | 找不到 `whatsapp://` 和消息内容（D31） |

把第 3–6 项的终端输出贴回来（没有病人资料），截图要遮住名字和号码。

### 云端容器的测试记录（2026-10-08，PostgreSQL 16、只用假资料、没有 GPiS）

- `pytest` → 255 passed（新增：名单的分类、`*C`、号码种类、家人合并、假期前的日期、*Open in WhatsApp* 的锁、终端摘要没有名字和号码、`GET /api/reminders`）。
- `npm test` → 41 passed；`npm run build` 成功。
- 用 headless Chromium 连 `npm run dev` + `uvicorn` + `chatbot_dev`（`REMINDER_SOURCE=demo`）：Demo Patient A & B 合成一条，消息照原文、英文那段写 *on the date above*；
  只有允许名单的号码有 *Open in WhatsApp*（`whatsapp://send?phone=…&text=…`）；*Needs staff* 显示 `*C`、固网、没有号码；选星期二（PHANG 休息）也正确。
- uvicorn 的日志里没有名字和号码。
- **还没有**连真的 GPiS：`--check-gpis` 和第 3–6 项要在开发电脑上做。

### 开发电脑的测试记录（2026-10-09，`GPiS_Dev` = 9 月 28 日的快照）

| # | 结果 |
|---|---|
| 1 | ✅ `pytest` 257 passed（D56 之后）；`npm test` 41 passed；`npm run build` 成功 |
| 2 | ✅ `[OK] GPiS_Dev 有提醒名单要用的全部栏位`：`Qry_CAH_Appointment` 有 `AppointmentID` |
| 3 | ✅ 09-02：Ready 24 + Needs staff 1 = 25 个预约，和 T6 的「PHANG 25 人」一样；09:00、11:30、15:30 各 3 个；只有 PHANG（星期三）；*Not appointments*：取消 3、`00:00` 1；5 个新加坡号码在 Ready。没有家人共用号码。Needs staff 那 1 条是 `*C`（AppointmentID 129387）：Remarks 是 `C/UP AFTER ISSUE DENTURE`（装好之后的检查）→ 规则改了（D57），以后在 Ready |
| 4 | ✅ 09-18：PHANG 17 人在 Ready；`OFF DAY record` 1、`00:00` 2；GOH 没有病人 |
| 5 | ✅ 09-30：Ready 4（`Confirmed`），和 T10 的「4 人」一样；11:00 的诊所联系人在 Needs staff（`No mobile number in GPiS; Booked under the clinic's own contact`） |
| 6 | ✅ 10-09：2 个，`Confirmed`，和测试 0 的「2 人」一样 |
| 7 | ✅ 网页 09-02：黄色 *Preview only … GPiS_Dev*、没有 *Open in WhatsApp*；Ready 24 / Needs staff 1 / Not appointments 4，和终端一样 |
| 8 | ✅ 假资料：`read from Demo data`；A & B 一张卡、有 *Open in WhatsApp* |
| 9 | ✅ WhatsApp Desktop 打开自己的对话、消息已经填好：`.env` 的诊所名（中文没有乱码）、分行名；`NAME: DEMO PATIENT A & DEMO PATIENT B`、`DATE: 10/10/26`、`TIME: 10:00 AM & 10:30 AM`、`DOCTOR: DR PHANG & DR GOH`；表情符号、换行正常 |
| 10 | ✅ 浏览器历史记录找不到 `whatsapp://` 和消息内容 |

- 看到 GPiS 有的名字后面带 `(P)` → 名单和消息里拿掉最后的 `(P)`、`(G)`（D56），`pytest` 257 个。
- 第 8 项第一次试：页面还是 `read from GPiS_Dev`（可能是改了 `.env` 没重开 uvicorn，或那行前面有 `#`）→ 上面「使用」加了步骤和检查方法。
- 第一次 `reminders_cli` 还是 `GPiS_Dev`：`REMINDER_SOURCE=demo` 要写在 `backend\.env`（不是 `.env.example`），存档、重开视窗。
- 129387 → 戴牙代码前面是 `AFTER` 的不算（D57），`pytest` 261 个。
- **第 1–10 项全部通过。**

## Phase 5b 第二步：`reminders` 表、NO WA

设计见 `docs/architecture.md` 8.4、8.9，D58。

- 按 **Open in WhatsApp** 会记在本系统的数据库（`reminders` 表）：谁、几点按的、填好的消息、包括哪几个 GPiS 预约。
  换页、重新整理、另一位员工打开，卡片都显示 *Opened*，*Ready* 上方写 `Opened in WhatsApp: 3 of 24`。
  - 按的时候后端会**重新读一次 GPiS**：那个号码已经不在 *Ready*（例：员工刚改了 GPiS）→ 显示错误，请员工 *Refresh*。
  - 系统不知道员工最后有没有按 Enter：按错了按 **Mark as not sent**，卡片变成 *Not sent*，可以再按。
  - 按过之后 GPiS 多了 / 少了预约（例：家人刚约了同一天）→ 卡片显示黄色提醒，请员工再看一次。
  - 同一个号码、同一个预约日期只有一条记录（UNIQUE）：再按一次是更新同一条。
- **NO WA: stop reminders**（*Ready*、*Needs staff* 的卡片都有）：病人在签名表的 Remark 写 `NO WA`（D55）→ 员工按一次、确认，
  这个号码（**整个号码，家人也一起**）以后都在 *Needs staff*：`Opted out of reminders`。按 **Allow reminders again** 改回来。
  终端的 `reminders_cli` 也会照这个设定。
- 新的数据库栏位（migration `0004`）：`reminders` 表；`wa_contacts.reminders_opt_out_at`、`_by`（`STAFF` / 以后 5c 的 `PATIENT`）、`_staff_id`。
- `reminders.body` 有病人名字（和 `messages` 一样）：开发时只在自己电脑的 `chatbot_dev`；保留多久见 `architecture.md` A10。
- 日志只记员工 ID 和日期，没有名字、号码。

### 更新（第一步已经装好的电脑）

在 `backend` 里（先启用 venv）：

```powershell
git pull
alembic upgrade head          # 0003 -> 0004：reminders 表、号码的 opt-out
alembic current               # 应该是 0004 (head)
pytest                        # 应该 272 passed，没有 skipped
```

在 `frontend` 里：`npm test` → **44 passed**；`npm run build` 成功。

### Phase 5b 第二步完成的条件（在开发电脑上测试）

用假资料（`.env`：`REMINDER_SOURCE=demo`、`WHATSAPP_ALLOWED_RECIPIENTS` = 自己的手机；改完 `Ctrl + C` 重开视窗 1）。

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 上面的「更新」 | `0004 (head)`；272 passed、没有 skipped；44 passed；`✓ built` |
| 2 | Reminders → 按 A & B 的 *Open in WhatsApp*（WhatsApp 打开后不用按 Enter） | 卡片 *Opened*，下面写 `Opened in WhatsApp by <你的名字> at …`；上方 `Opened in WhatsApp: 1 of 2` |
| 3 | 按 `F5` 重新整理；再用另一个员工帐号（或另一个浏览器）登录看 | 还是 *Opened*、同一个名字和时间 |
| 4 | 按 *Mark as not sent* | 卡片变成 *Not sent*，`Marked as not sent by …`；*Open in WhatsApp* 可以再按 |
| 5 | 按 A & B 的 *NO WA: stop reminders* → 确认 | *Ready (1)*；A & B 在 *Needs staff*：`Opted out of reminders` |
| 6 | `python -m app.reminders_cli` | A & B 那个号码在 NEEDS_STAFF：`Opted out of reminders` |
| 7 | *Needs staff* 里按 *Allow reminders again* → 确认 | 回到 *Ready (2)* |
| 8 | 视窗 1 的 uvicorn 日志 | 没有病人名字、号码 |

测完把 `REMINDER_SOURCE` 删掉，`Ctrl + C` 重开视窗 1。读 `GPiS_Dev` 时没有 *Open in WhatsApp*，但 *NO WA* 可以试（会记在 `chatbot_dev`；试完按 *Allow reminders again* 改回来）。

### 云端容器的测试记录（2026-10-09，PostgreSQL 16、只用假资料、没有 GPiS）

- `pytest` → 272 passed（新增 11 个：`reminders` 的 UNIQUE、opt-out 的约束、按两次只有一条、按过后 GPiS 改了、不在 *Ready* / 不在允许名单拒绝、*Not sent*、*NO WA* 和改回来）。
- `npm test` → 44 passed；`npm run build` 成功。
- 用 headless Chromium 连 `npm run dev` + `uvicorn`（`REMINDER_SOURCE=demo`、migration 0004）：第 2–5、7 项都对；重新整理后还是 *Opened*；uvicorn 日志没有名字和号码。

### 开发电脑的测试记录（2026-10-09）

- 第 1–8 项全部通过：`0004 (head)`、`pytest` 272 passed、`npm test` 44 passed、`npm run build` 成功；假资料的 *Opened*、重新整理和另一个帐号、*Mark as not sent*、*NO WA*、`reminders_cli`、*Allow reminders again* 都正常；日志没有名字和号码。

### 修正：切到 *Needs staff* 再回来，*Opened* 变回 *To send*（2026-10-14）

开发电脑找到的：按了 *Open in WhatsApp*（卡片 *Opened*）→ 按 *Needs staff* 分页 → 再按 *Ready*，卡片又写 *To send*，
上方的 `Opened in WhatsApp: 1 of 2` 却没变；按 *Refresh* 才回到 *Opened*。

- 原因：后端有记下来（所以 *Refresh* 是对的）。错在画面：按过之后后端回来的结果只放在那张卡片里；
  切到别的分页，卡片会拿掉，回到 *Ready* 重新建立，就又用一开始读的名单（那时还没按）。
- 改了：按过的结果放在整个 Reminders 页面（`frontend/src/pages/RemindersPage.tsx`），卡片和上方的数目都读同一份。没有改后端、没有改表。

| # | 做什么（假资料，同上） | 应该看到 |
|---|---|---|
| 1 | `npm test` | **48 passed**（新增 1 个：切分页回来还是 *Opened*） |
| 2 | 按 A & B 的 *Open in WhatsApp* → *Needs staff* → *Ready* | 还是 *Opened*、`Opened in WhatsApp by …`；上方 `1 of 2` |
| 3 | 按 *Mark as not sent* → *Needs staff* → *Ready* | 还是 *Not sent*；上方 `0 of 2` |

云端容器（2026-10-14，假资料）：`npm test` 48 passed（新的测试在旧的程序上会失败）；`npm run build` 成功；
headless Chromium 照上面第 2、3 项点过（PR #23 的版本也重现过这个问题）。

开发电脑（2026-10-14，假资料）：第 1–3 项全部通过（`npm test` 48 passed；切分页回来还是 *Opened* / *Not sent*，上方的数目对）。

## 资料保留（A10）：提醒过了 90 天就删掉

设计见 `docs/decisions.md` D67、`docs/architecture.md` A10。

- `reminders`：预约日期早于「今天 − 90 天」的**整行删掉**（号码、填好的消息、预约 ID、员工都不留）。
  删之前每天的数目加进 `reminder_stats`（一个预约日期一行：`opened`、`not_sent`、`opened_appointments`；没有号码、名字、员工）。
  例：今天是 2026-10-13 → 删掉 2026-07-15 之前的预约（7-15 的留着）。
- `wa_contacts`：按过 *NO WA* 的号码**一直留**；改回照常提醒、又没有对话的号码删掉。
- 全部在一个交易里：中间出错就一条都不删。
- 电脑 B：每次登入 Windows 时，`deploy/start-chatbot.ps1` **先备份、备份成功才清理**，`start.log` 记一行日期和数目；
  开机备份除了留最新 14 份，超过 30 天的也删（`docs/deploy-pc-b.md` 第 6 节）。
- `/api` 的回应都有 `Cache-Control: no-store`：浏览器不把名单（名字、号码）存进硬盘的快取。
- 保留天数是 `app/db/retention.py` 的 `RETENTION_DAYS`（最少 30）。画面没有改。

```powershell
python -m app.retention              # 删掉过了 90 天的提醒（数目留在 reminder_stats）、不用再留的号码
python -m app.retention --dry-run    # 只印会删几条，什么都不删
python -m app.retention --stats      # 每个月的数目（还在的提醒 + 已经删掉只留数目的）
```

输出只有日期和数目，没有名字、号码，可以贴回来。

### 更新（Phase 5b 第二步已经装好的电脑）

在 `backend` 里（先启用 venv）：

```powershell
git pull
alembic upgrade head          # 0004 -> 0005：reminder_stats 表
alembic current               # 应该是 0005 (head)
pytest                        # 应该 316 passed，没有 skipped
```

在 `frontend` 里：`npm test` → **47 passed**；`npm run build` 成功（网页没有改）。

### 资料保留完成的条件（在开发电脑上测试）

只用 `chatbot_dev` 和假资料（号码 `601000000xx`、消息 `DEMO`）。
开发电脑的 `psql` 不在 PATH：每个视窗先设一次 `$psql`，SQL 用 `& $psql -h localhost -U chatbot -d chatbot_dev -c "<SQL>"` 跑（有 pgpass 那一行之后可以加 `-w`，不问密码）：

```powershell
$psql = (Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" | Sort-Object FullName -Descending | Select-Object -First 1).FullName
```

下面的 SQL 用 `CURRENT_DATE`：**过了半夜 12 点**会差一天，跨日的话把 `CURRENT_DATE - 100` 换成那一天的日期（例 `'2026-07-05'`）。

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 上面的「更新」 | `0005 (head)`；316 passed、没有 skipped；47 passed；`✓ built` |
| 2 | psql 加 3 条假的提醒（下面的 SQL 1） | `INSERT 0 3` |
| 3 | `python -m app.retention --dry-run` | `只看、不删：…之前的提醒有 2 条（1 天）`（日期是今天 − 90 天）；不用再留的号码可能不是 0（以前读 `GPiS_Dev` 试过 *NO WA* 又改回来的） |
| 4 | `python -m app.retention`，再跑一次 | 第一次 `删了 2 条（1 天…）`；第二次 `删了 0 条` |
| 5 | psql（下面的 SQL 2） | `reminders` 只剩 10 天前的那条；`reminder_stats` 有 100 天前那天：`opened` 1、`not_sent` 1、`opened_appointments` 2 |
| 6 | `python -m app.retention --stats` | 每个月一行 + `Total`；没有名字、号码 |
| 7 | 开机的脚本（下面的「试 `start-chatbot.ps1`」） | `start.log`：`备份：…dump` → `清理：…删了 1 条…` → `uvicorn 启动`，中文正常；40 天前的假备份不见了，今天的在 |
| 8 | 同上，拿掉 pgpass 那一行再跑一次 | `start.log`：`备份失败…` → `清理：这次不清理（备份没有成功）` → `uvicorn 启动` |
| 9 | 浏览器 `http://localhost:8000` 登入 → Reminders → `F12` → *Network* → 点 `reminders?…` → *Response Headers* | `Cache-Control: no-store` |
| 10 | 清理（下面的 SQL 3、删掉 `%LOCALAPPDATA%\Chatbot`） | 假资料、测试的备份都没了 |

SQL 1（加假资料）：

```sql
INSERT INTO reminders (appointment_date, wa_phone, status, body, gpis_appointment_ids) VALUES
  (CURRENT_DATE - 100, '60100000001', 'OPENED',   'DEMO', ARRAY[1, 2]),
  (CURRENT_DATE - 100, '60100000002', 'NOT_SENT', 'DEMO', ARRAY[3]),
  (CURRENT_DATE - 10,  '60100000001', 'OPENED',   'DEMO', ARRAY[4]);
```

SQL 2（看结果）：

```sql
SELECT appointment_date, status FROM reminders WHERE body = 'DEMO';
SELECT * FROM reminder_stats WHERE appointment_date = CURRENT_DATE - 100;
```

**试 `start-chatbot.ps1`**（第 7、8 项；用 **Windows PowerShell 5.1**，和电脑 B 一样，不用 PowerShell 7）：

1. 关掉平常开发用的 uvicorn（port 8000 要空出来）；`frontend` 已经 `npm run build`（第 1 项）。
2. `%APPDATA%\postgresql\pgpass.conf` 暂时加一行 `localhost:5432:chatbot_dev:chatbot:<chatbot 的密码>`（没有这个档就新建；测完拿掉）。`& $psql -h localhost -U chatbot -d chatbot_dev -w -c "SELECT 1"` 印出 `1` 才对（`no password supplied` = pgpass 没读到，脚本的备份也会失败）。
3. 再加一条要删的假提醒（SQL 1 的第一行），放一个 40 天前的假备份：
   ```powershell
   $bk = "$env:LOCALAPPDATA\Chatbot\backup"; New-Item -ItemType Directory -Force $bk | Out-Null
   Set-Content "$bk\chatbot_dev-20260801-0900.dump" "fake"
   (Get-Item "$bk\chatbot_dev-20260801-0900.dump").LastWriteTime = (Get-Date).AddDays(-40)
   ```
4. 在仓库根目录：`powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\start-chatbot.ps1`（视窗会停在那里，uvicorn 在跑）。
5. 另开一个视窗：`notepad "$env:LOCALAPPDATA\Chatbot\logs\start.log"`；`Get-ChildItem "$env:LOCALAPPDATA\Chatbot\backup"`。
   第 9 项也在这时候做。
   还有 SQL 2：`reminders` 只剩 10 天前那条；`reminder_stats` 那天变成 `2 | 1 | 4`（第 4 项的 `1 | 1 | 2` 加上这次的 `1 | 0 | 2`）。
6. 关掉第 4 步的视窗，再跑 `.\deploy\stop-chatbot.ps1` → `已经停了`。
7. 第 8 项：pgpass 拿掉那一行，重做第 4–6 步。

SQL 3（清理）：

```sql
DELETE FROM reminders WHERE body = 'DEMO';
DELETE FROM reminder_stats WHERE appointment_date = CURRENT_DATE - 100;
```

然后 `Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Chatbot"`（里面的备份是 `chatbot_dev` 的）；pgpass 那一行已经拿掉（第 7 步）。

### 云端容器的测试记录（2026-10-13，PostgreSQL 16、Python 3.11、只用假资料）

- `pytest` → 316 passed（新增 13 个：90 天的界线、每一种状态都有算进统计、删掉和数目、再跑一次不会多算 / 之后再删会累加、`--dry-run` 不删、*NO WA* 的号码留着 / 有对话的留着 / 改回来的删掉、
  统计写不进去就一条都不删、终端输出没有名字和号码、`--stats`、`/api` 有 `no-store`）。
- `npm test` → 47 passed；`npm run build` 成功（网页没有改）。
- 真的跑 `python -m app.retention`（假资料，`0005`）：`--dry-run` 2 条、删了 2 条、再跑 0 条、`--stats` 对；`reminder_stats` 一行 `1 | 1 | 2`；改回照常提醒的假号码删了。
- PowerShell 7（Linux）：`deploy/` 的 4 个脚本语法都没有错误；备份的规则用假档案试 4 种情况（16 份都在 30 天内 → 留 14；有超过 30 天的 → 删掉；最新的一份一定留）；`retention.log` 的中文写进 `start.log` 正常。
  **Windows PowerShell 5.1 没有试**（云端没有）：开发电脑第 7、8 项。
- headless Chromium 登入、读假资料的 `/api/reminders`、关掉浏览器后在设定档里找假名字：改之前 **2 个档案**有，加了 `no-store` 之后 **0 个**。

### 开发电脑的测试记录（2026-10-13，Windows PowerShell 5.1、PostgreSQL 18、`chatbot_dev` + 假资料）

| # | 结果 |
|---|---|
| 1 | ✅ `0005 (head)`；`pytest` 316 passed；`npm test` 47 passed |
| 2–6 | ✅ 删了 100 天前的 2 条、10 天前的留着；`reminder_stats` 那天 `1 | 1 | 2` |
| 8 | ✅ 第一次跑的时候还没有 pgpass 那一行：`备份失败（看 backup-error.log）` → `清理：这次不清理（备份没有成功）` → `uvicorn 启动` |
| 7 | ✅ 加了 pgpass 那一行后：`备份：…chatbot_dev-20261013-2317.dump` → `清理：预约日期在 2026-07-15 之前的提醒删了 1 条（1 天…）；不用再留的号码删了 0 个` → `uvicorn 启动`，中文正常；备份资料夹只剩 `20261013-2317`（40 天前的假档案删了）；`reminders` 只剩 10 天前那条；`reminder_stats` `2 | 1 | 4`（累加） |
| 9 | ✅ `Cache-Control: no-store` |
| 10 | ✅ 假资料、`%LOCALAPPDATA%\Chatbot`、pgpass 那一行都清掉了 |

这次找到的（已经改进上面的清单）：

- 开发电脑的 `psql` 不在 PATH（`The term 'psql' is not recognized`）→ 用 `$psql` 完整路径（`start-chatbot.ps1` 自己找 `pg_dump.exe`，不受影响）。
- 先确认 `psql -w` 连得上，再跑脚本：pgpass 没设好时备份会失败，清理也不会做（第 8 项的情况）。
- 测到半夜 12 点前后：`CURRENT_DATE` 会变，改用写出来的日期。

## Phase 6a-1：遮证件号码（D69）

设计见 `docs/decisions.md` D69、`docs/architecture.md` 11.7。

- 病人在 WhatsApp 传的 **IC / 护照号码**，webhook 收到时**存进数据库之前**先遮掉后面 6 位（`app/redact.py`）。
  数据库、Admin Platform（以后的 AI）都只看得到遮过的。
- 马来西亚 IC 留前面 6 位（生日）：`900101-01-1234` → `900101-**-****`（`-`、空格照留）。
- 新加坡 NRIC / FIN、护照：遮后面 6 个字，`S1234567A` → `S12******`、`A12345678` → `A12******`。
- 前面有 `IC`、`NRIC`、`MyKad`、`passport`、`护照`、`身份证`、`KP` 的号码：格式认不出来也遮后面 6 个字。
- 日期、时间、牙位、疗程代码、普通的电话号码不遮；遮两次结果一样（不会把生日也遮掉）。
- 没有改表、没有改网页；电脑 B 不收 WhatsApp，**不用更新 B**。以前存的消息不会改（开发时只有假资料）。

### 更新（开发电脑）

在 `backend` 里（先启用 venv）：

```powershell
git fetch origin claude/patient-data-retention-a10-e77qwk
git checkout claude/patient-data-retention-a10-e77qwk
git pull
pytest                        # 应该 351 passed，没有 skipped
```

### 6a-1 完成的条件（在开发电脑上测试）

第 2–4 项要用 Phase 5a 的 Meta 测试号码（视窗 1–3：Admin API、webhook、cloudflared，见「Phase 5a」的「使用」）。cloudflared 重开后要改 Meta 的 *Callback URL*；token 有问题先跑 `python -m app.whatsapp_check`。

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 上面的「更新」 | 351 passed、没有 skipped |
| 2 | 用**自己的手机**传给测试号码（**假号码**）：`我的IC是 900101-01-1234，passport A12345678` | — |
| 3 | Admin Platform → *Conversations* → 那段对话 | `我的IC是 900101-**-****，passport A12******` |
| 4 | psql（`$psql`，见「资料保留完成的条件」）：`SELECT count(*) FROM messages WHERE body LIKE '%01-1234%' OR body LIKE '%A12345678%';` | `0` |
| 5 | 视窗 2（webhook）的日志 | 没有消息内容、没有号码 |

### 云端容器的测试记录（2026-10-14，PostgreSQL 16、Python 3.11、只用假资料）

- `pytest` → 351 passed（新增 35 个：IC 有 `-` / 没有 / 空格、马来文和中文的句子、新加坡 NRIC / FIN、护照、各种关键字、两个号码、不该遮的（日期、时间、牙位、疗程代码、电话、`clinic`、太短的）、遮两次结果一样、webhook 存进数据库的是遮过的）。
- 写的时候找到、已经改好：有关键字的规则一开始在格式规则之后跑，会把已经遮过的 `900101-**-****` 的生日也遮掉 → 改成先跑关键字、而且后面接着 `*` 的不再遮。

### 开发电脑的测试记录（2026-10-15，Meta 测试号码 + 自己的手机、假号码）

- 第 1–5 项全部通过：`pytest` 351 passed、没有 skipped；手机传 `我的IC是 900101-01-1234，passport A12345678` → 视窗 2 `webhook：1 条新消息`、`POST /webhook … 200`；
  *Conversations* 显示 `我的IC是 900101-**-****，passport A12******`；数据库找不到完整的号码（`0`）；webhook 的日志没有消息内容、号码。

## Phase 6a-2a：还没录入 GPiS 的请求算占用（A8）

设计见 `docs/architecture.md` 11.6（第 1 项）、`docs/decisions.md` D71。

- 查空档（`GET /availability`、`python -m app.cli`）时，本系统还在 **`PENDING`** 的请求也当作那一格有人，和 GPiS 的预约一起算人数。
  例：PHANG 10:00 GPiS 有 2 人 + 1 个 `PENDING` 的请求 = 3 人（满了），AI 不会再把 10:00 推荐给别人。
- 只算**有医生、有日期、有时段**的请求；60 分钟的请求和 GPiS 的 `1HOUR` 一样，把下一格也封住。
- 变成 `CONFIRMED`、`REJECTED`、`CANCELLED` 就不算。员工在 GPiS 输入之后、按确认之前，同一位病人会被算两次：只是少推荐，不会约重。
- `patients` 还是只算 GPiS（和 SQL 一样）；多了 `requests`。`requests=false`（API）/ `--gpis-only`（终端）= 只看 GPiS，和 SQL 对照时用。
- 输出只有请求编号、时段、几格，**没有病人资料**。
- 没有改表、没有改网页；电脑 B 的提醒名单不受影响（只看 GPiS，D41），**不用更新 B**。
- 还没做的（6a-2b、6a-2c、6a-3）：员工按 *Entered in GPiS ✓* 时当场查 GPiS、ADMIN 的自动确认开关、AI 建请求时锁住再查一次。

### 更新（开发电脑）

在 `backend` 里（先启用 venv）：

```powershell
git fetch origin claude/dazzling-wozniak-xqaz84
git checkout claude/dazzling-wozniak-xqaz84
git pull
pytest                        # 应该 364 passed，没有 skipped
```

### 6a-2a 完成的条件（在开发电脑上测试）

预约读 `GPiS_Dev`，请求读 `chatbot_dev`（里面的请求都是 `python -m app.db.demo` 的假资料）。输出没有病人资料，可以直接贴回来。
**不会改任何资料**（假资料的请求留给 6a-2b 测）。psql 用 `$psql`（见「资料保留完成的条件」）。

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 上面的「更新」 | 364 passed、没有 skipped |
| 2 | `python -m app.cli 2026-09-02 PHANG S+P --gpis-only`、`python -m app.cli 2026-09-09 PHANG S+P --gpis-only` | 7a、7b、7c 和「对照记录」的 T6、T8 一样（7a 后面多 `(GPiS only)`，7b 多一栏 `Requests` 都是 `0`） |
| 3 | `& $psql -h localhost -U chatbot -d chatbot_dev -c "SELECT id, doctor_id, preferred_date, preferred_slot, duration_minutes FROM appointment_requests WHERE status = 'PENDING' ORDER BY id;"` | 还在 `PENDING` 的请求（没有名字）。通常有 PHANG 16:00 一个（Demo Kid B；Demo Kid A 在 Phase 4b 测试时已经确认了）、GOH 10:00 一个（Demo Patient）。PHANG 那一行的日期下面叫 `D`、GOH 的叫 `E`，记下 `id` |
| 4 | `python -m app.cli D PHANG S+P`（`D` 写成 `2026-10-09` 这样） | 7a `Requests=` 第 3 项 PHANG、`D` 那天的行数；7b 16:00 的 `Requests` 一样多；7d 的请求编号和第 3 项的 `id` 一样、`16:00`、`1` |
| 5 | `python -m app.cli D PHANG S+P --gpis-only` | 7a `(GPiS only)`、没有 7d；16:00 的 `Booked` 比第 4 项少了第 4 项的 `Requests` 那么多，其他时段一样 |
| 6 | `python -m app.cli E GOH OR` | 7a `Requests=1`；10:00 的 `Requests` 是 `1`；7d 是 GOH 那一行的 `id` |
| 7 | `python -m app.cli D GOH S+P`（PHANG 的日子查 GOH） | `Requests=0`、没有 7d（别的医生的请求不算） |
| 8 | `uvicorn app.main:app --reload` → <http://127.0.0.1:8000/docs> → `GET /availability`：`date` = `D`、`doctor` = `PHANG`、`service` = `S+P`、`debug` = `true` → *Execute* | `requests` 和第 4 项一样；`held_requests` 只有 `request_id`、`time`、`dur_slots`；整个回应没有 `Demo` |
| 9 | 同上，再把 `requests` 改成 `false` → *Execute* | `requests: 0`、`held_requests: []`，16:00 的 `booked` 和第 5 项一样 |

### 云端容器的测试记录（2026-10-15，PostgreSQL 16、Python 3.11 + `requirements-lock.txt` 和 3.13、只用假资料、没有 GPiS）

- `pytest` → 364 passed（新增 13 个：请求占一个名额、architecture.md 11.6 的例子、60 分钟的请求封住两格、前后一格 3 人时上限 2、医生休息的日子不受影响、没有请求时结果不变；
  数据库只读 `PENDING`、这天、这位医生、有时段的请求（别的医生、别的日子、没有时段、没有医生、已确认、已拒绝、已取消都不算）；
  API 的 `requests`、`requests=false` 不读请求、`debug` 只有编号、读请求失败回 `503` 不露出密码；API 真的从测试数据库读到请求，回应没有病人名字）。
- `python -m app.cli`（GPiS 换成假的：16:00 有 1 人；测试数据库有 2 个 16:00 的请求，一个 30 分钟、一个 60 分钟）：7a `Patients=1  Requests=2`；16:00 `Booked 3`、`Requests 2`，16:00、16:30 变成 `LONG APPT`；7d 列出 2 个请求。加 `--gpis-only`：16:00 `Booked 1`、`Can30 1`，没有 7d。

### 开发电脑的测试记录（2026-10-15，`GPiS_Dev` = 2026-09-28 的快照、`chatbot_dev` 的假资料）

- 第 1–9 项全部通过：`pytest` 364 passed、没有 skipped。
- 第 2 项：`--gpis-only` 的 T6（2026-09-02 PHANG S+P：25 人；09:00、11:30、15:30 满 3 人；09:30、11:00、15:00、16:00 `Cap = 2`）、
  T8（2026-09-09 PHANG S+P：25 人；16:00、16:30 `LONG APPT`；17:00 有 1 人）和「对照记录」一样，`Requests` 栏都是 `0`。
- 第 3 项：`PENDING` 有 2 个：id `2`（PHANG、2026-10-09、16:00、30 分钟）、id `3`（GOH、2026-10-10、10:00、30 分钟）。
- 第 4、5 项（2026-10-09 PHANG S+P）：`Patients=2  Requests=1`；16:00 `Booked 1`、`Requests 1`，7d 是 id `2`；15:30 的 `Can60` 变 `0`（下一格有请求）。
  加 `--gpis-only`：16:00 `Booked 0`、15:30 和 16:00 `Can60 = 1`，其他时段一样。
- 第 6 项（2026-10-10 GOH OR）：`Patients=1  Requests=1`；10:00 `Booked 1`、`Requests 1`，7d 是 id `3`；09:30 的 `Can60` 变 `0`。
- 第 7 项（用 2026-10-09 GOH OR 测）：`Requests=0`、没有 7d（PHANG 的请求不算到 GOH）。
- 第 8、9 项（`/docs`）：`requests: 1`、`held_requests` 只有 `request_id: 2`、`time: 16:00`、`dur_slots: 1`，没有名字；`requests=false` → `requests: 0`、`held_requests: []`、16:00 `booked: 0`。
- 没有改任何资料（id `2`、`3` 还是 `PENDING`，留给 6a-2b 测）。

## Phase 6a-2b：员工按 *Entered in GPiS ✓*（D71 ①、D72）

设计见 `docs/decisions.md` D71、D72，`docs/architecture.md` 11.6。

- *Requests* → *Pending* 的卡片：**Entered in GPiS ✓**（取代以前的 *Confirm* + 自己填 AppointmentID），在**画面中间弹出视窗**（不是新分页；卡片只放主要资料）。名单长的话只有视窗中间那一块上下拉；*Back*、`×`、Esc、点视窗外面都是关掉，什么都不改。
  员工先在 GPiS 输入，再按：系统**当场只读查一次 GPiS**，列出那一天的预约（只有时间、名字、医生；没有 Remarks、号码），
  和请求一样的排最上面（*Same patient* / *Same doctor* / *Same time*）。员工点选 → *Confirm this appointment*：
  后端再读一次 GPiS，那个预约还在才确认。GPiS 里没有 = 不能确认。员工约成别的日期，改上面的 *GPiS date*。
- 确认后系统**马上经 WhatsApp 发确认消息**：`好的哟，已经帮你预约了哦😊` / `Okay, your appointment is booked 😊`，下面列 GPiS 的名字、日期、时间、医生、分行（D73）。
  发不了的放在新的分页 ***To tell patient***，写原因；员工用 *Open in WhatsApp* / *Copy message* / 手机传了，按 ***Patient told ✓***。
- 一个 GPiS 预约只能确认一个请求（已经用过的变灰）；新病人顺便记下 GPiS 的 `ContactID`。
- *Reject*、*Patient cancelled* 按错了：*Rejected* / *Cancelled* 分页按 **Back to pending** 改回来（D73）；确认过又取消的要重新点选。
- **读 `GPiS_Dev` 时不发、也没有 *Open in WhatsApp***（黄色提醒）：名字是真的病人。要试真的发，用 `REMINDER_SOURCE=demo`（假资料）。
- 选单 *Requests* 的数字 = 待确认 + 要通知。
- 改表：migration **`0006`**（`appointment_requests` 多 7 栏 + 部分唯一 index；以前确认的当作已经通知）。
- 电脑 B 还没有请求（没有 AI），**暂时不用更新**；下次更新 B 时要 `alembic upgrade head` 到 `0006`（照 `docs/deploy-pc-b.md` 第 9 节，改表前先备份）。
- 测「确认后自动通知」：`python -m app.db.demo --request-for <自己的手机>`，给自己手机的那段对话加一个 PENDING 请求（Demo Self、S+P、PHANG、下一个星期五 10:00）。

### 更新（开发电脑）

```powershell
# backend（先启用 venv）
git pull
alembic upgrade head          # 0005 -> 0006
alembic current               # 0006 (head)
pytest                        # 应该 390 passed，没有 skipped

# frontend
cd ..\frontend
npm test                      # 应该 50 passed
npm run build                 # ✓ built
```

### 6a-2b 完成的条件（在开发电脑上测试，16 项）

视窗照「Phase 5a」的「使用」（视窗 1 Admin API、视窗 4 网页；B 部分还要视窗 2 webhook、视窗 3 cloudflared）。psql 用 `$psql`。
**A 部分读 `GPiS_Dev`，画面上是真的病人名字：只数行数，不要截图、不要贴名字。**

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 上面的「更新」 | `0006 (head)`；`pytest` 392 passed、没有 skipped；`npm test` 51 passed；`npm run build` 成功 |
| 2 | `& $psql -h localhost -U chatbot -d chatbot_dev -c "SELECT id, status, patient_told_at IS NOT NULL AS told FROM appointment_requests ORDER BY id;"` | id `1`（Phase 4b 确认过的 Demo Kid A）`CONFIRMED`、`told = t`；`2`、`3` `PENDING`、`f`；`4` `CANCELLED`、`f` |
| 3 | 开视窗 1、4，登入 → *Requests* | 分页 *Pending*、*To tell patient*、*Confirmed* …；选单 *Requests* 的数字是 `2`；*To tell patient* 没有数字（Demo Kid A 不在里面） |
| **A** | **读 `GPiS_Dev`**（`.env` 没有 `REMINDER_SOURCE=demo`） | |
| 4 | Demo Kid B → **Entered in GPiS ✓** | *GPiS date* 是 `2026-10-09`；黄色 *The list comes from GPiS_Dev: the patient will not be messaged automatically*；2 行：`11:30`、`13:00`，都是 Dr PHANG（= 6a-2a 第 4 项的 `Patients=2`）；*Confirm this appointment* 要点选之后才能按 |
| 5 | *GPiS date* 改成 `2026-09-02` | Dr PHANG 的有 25 行（= T6 的 `Patients=25`），时间由早到晚 |
| 6 | **Back** | 回到卡片，还是 *Pending*（什么都没改） |
| **B** | **假资料 + 自己的手机**：`.env` 加 `REMINDER_SOURCE=demo` → 重开视窗 1；开视窗 2、3（*Callback URL* 改成新的网址） | |
| 7 | 用**自己的手机**传一条 `test 6a-2b` 给 Meta 测试号码 → `python -m app.db.demo --request-for <自己的手机>` | `Added pending request N: Demo Self, S+P, PHANG, <下一个星期五> 10:00.` |
| 8 | *Requests* → **Refresh** → Demo Self → **Entered in GPiS ✓** | 没有黄色提醒；6 行 Demo Patient A–F（取消的 G、`00:00` 的 H 不列）；第一行 `10:00 DEMO PATIENT A · Dr PHANG Same doctor · Same time` |
| 9 | 点选第一行 → **Confirm this appointment** | 绿色 *Demo Self: confirmed, and the patient was sent the confirmation.*；手机收到 `好的哟，已经帮你预约了哦😊`、`Okay, your appointment is booked 😊`，下面 `NAME: DEMO PATIENT A`、那天的日期、`TIME: 10:00 AM`、`DOCTOR: DR PHANG`；*Conversations* 那段对话最后一条是这则消息（员工接手的对话 → 算你发的） |
| 10 | Demo Kid B → **Entered in GPiS ✓** → *GPiS date* `2026-10-09` → 点选 `11:00 DEMO PATIENT C` → **Confirm this appointment** | 黄色 *confirmed, but the patient was not messaged (More than 24 hours …)*；*To tell patient (1)*；选单数字 `2`（1 个待确认 + 1 个要通知） |
| 11 | *To tell patient* | Demo Kid B 的卡片：黄色原因、*In GPiS* `Fri 09 Oct 2026 11:00 · Dr PHANG`、消息预览（`NAME: DEMO PATIENT C`）；没有 *Open in WhatsApp*（`60120000001` 不在允许名单），有 *Copy message*、*Patient told ✓* |
| 12 | **Patient told ✓** | *Every confirmed patient has been told.*；*Confirmed* 分页的 Demo Kid B 有 *Patient told … (by staff)*，Demo Self 有 *(sent by the system)* |
| 13 | Demo Patient → **Entered in GPiS ✓** → *GPiS date* `2026-10-09` | `11:00 DEMO PATIENT C` 那一行变灰、*already confirms request #<Demo Kid B 的 id>*，不能点选 → **Back** |
| 14 | Demo Patient → **Patient cancelled** → OK → *Cancelled* 分页 → Demo Patient → **Back to pending** → OK | Demo Patient 回到 *Pending*，还是 `GOH`、`Sat 10 Oct 2026 10:00`；选单数字多 1 |
| 15 | `& $psql -h localhost -U chatbot -d chatbot_dev -c "SELECT id, gpis_appointment_id, confirmed_date, confirmed_slot, confirmed_doctor_id, patient_told_by IS NOT NULL AS by_staff, notify_problem FROM appointment_requests WHERE status = 'CONFIRMED' ORDER BY id;"` | Demo Kid B：`2026-10-09`、`11:00:00`、`PHANG`、`by_staff = t`、原因是 *More than 24 hours …*；Demo Self：下一个星期五、`10:00:00`、`PHANG`、`by_staff = f`、原因空的 |
| 16 | 清理：`.env` 拿掉 `REMINDER_SOURCE=demo` → 重开视窗 1；关掉视窗 3（cloudflared） | — |

### 云端容器的测试记录（2026-10-15，PostgreSQL 16、Python 3.11 + `requirements-lock.txt`、Node 22、只用假资料）

- `pytest` → 390 passed（新增 26 个）：点选名单（取消、`Postpone`、`00:00`、诊所联系人、OFF DAY、看不懂的时段都不列，同一个预约不重复，排序、`same_*`，没有 Remarks、号码）；
  再读一次 GPiS 才确认（没有、已取消 → 409，请求还是 PENDING）；一个 GPiS 预约只确认一个请求；员工约成别的日期、医生、时间照点选的发；
  ContactID 只在空的、别人没用的时候记；读 GPiS_Dev 不发、没有 *Open in WhatsApp*；不在允许名单、没设定 WhatsApp、WhatsApp 不接受、超过 24 小时、对话已结束、员工建的请求（没有对话）、发了但存不进去 → 都在 *To tell patient*；
  AI 的对话算 AI 发、员工接手的算员工发；*Patient told* 两次 → 409；确认后取消就不在「要通知」；确认后不再算占用（A8）；
  migration `0006` 把以前确认的当作已经通知；`python -m app.db.demo --request-for`。
- `npm test` → 50 passed（新的流程：点选、换日期、已经用过的变灰、GPiS_Dev 的黄色提醒、没发出去的原因、读 GPiS 失败、*To tell patient* 的 *Open in WhatsApp* / *Patient told*）；`npm run build` 成功。
- headless Chromium（假资料 `REMINDER_SOURCE=demo`、没设定 WhatsApp）照着点过：点选 → 确认 → 黄色 *not messaged (WhatsApp is not set up on this computer)* → *To tell patient (1)* 有 *Open in WhatsApp*（允许名单里的号码）→ *Patient told* → *Confirmed* 显示 *(by staff)*；1366 和 400 宽都排得下；已经用过的预约变灰。
- 写的时候找到、已经改好：点选名单的圆点被全站的 `label` 样式排到文字上面 → 名单的 `label` 改成横排。

### 开发电脑测试时改的（2026-10-17，D73）

- 确认消息改成 `好的哟，已经帮你预约了哦😊` / `Okay, your appointment is booked 😊` + 预约资料（开发者定的）。
- 测试时按错 *Patient cancelled*，请求回不到 *Pending* → 加 **Back to pending**（*Rejected*、*Cancelled* 分页；`POST /api/requests/{id}/reopen`）。
- 云端：`pytest` 392 passed（新增 2 个：取消 / 拒绝之后改回来又算占用、已经是 Pending 或 Confirmed 不能改回；确认过又取消再改回，旧的确认资料清掉、可以再确认一次）；`npm test` 51 passed、`npm run build` 成功。
- 弹出视窗（开发者 2026-10-17 要的）：*Entered in GPiS ✓* 不再把名单塞在卡片里，改成画面中间的视窗（标题有病人、疗程、医生、想要的时间），名单在视窗里面卷动，*Same doctor* 这些标签放在名字下一行。
  云端：`npm test` 51 passed（多测：视窗不在卡片里、Esc 关掉）；headless Chromium 1366 × 768、400 × 760 截图：视窗置中、400 宽时只有中间卷动、Esc 关掉。

### 开发电脑的测试记录（2026-10-17，`GPiS_Dev` = 2026-09-28 的快照、`chatbot_dev` 的假资料、Meta 测试号码 + 自己的手机）

- 全部通过：`0006 (head)`；`pytest` 392 passed；`npm test` 51 passed；`npm run build` 成功。
- 第 2 项：id 1（Demo Kid A，Phase 4b 确认过）`CONFIRMED`、`told = t`；2、3 `PENDING`；4 `CANCELLED`。
- 假资料 + 自己的手机：Demo Self（2026-10-23 10:00）点选 `10:00 DEMO PATIENT A` → 手机收到 `好的哟，已经帮你预约了哦😊` / `Okay, your appointment is booked 😊` + 预约资料；
  Demo Kid B 点选 `15:00 DEMO PATIENT F` → *More than 24 hours* → *To tell patient* → *Patient told ✓*；Demo Patient 看 10-09 时 `15:00 DEMO PATIENT F` 变灰。
- 测试时按错，把确认过的 Demo Kid B 取消了 → 用 *Back to pending* 改回来：`PENDING`、旧的确认资料清掉（D73）。
- 读 `GPiS_Dev`（只看、没有确认）：黄色 *The list comes from GPiS_Dev …*；2026-10-09 有 2 行（`11:30`、`13:00`，都是 Dr PHANG）；2026-09-02 Dr PHANG 25 行（= T6）；按 *Back* 什么都没改。
- 测试时改的：确认消息的写法、*Back to pending*（D73）、弹出视窗。
- Meta 的 *Verify and save* 一次出现 *The callback URL or verify token couldn't be validated*：照「Phase 5a」的视窗顺序重开、网址加 `/webhook` 后通过（不是 access token 的问题）。

## Phase 6a-2c：自动确认（D71 ②、D74）

设计见 `docs/decisions.md` D71、D74，`docs/architecture.md` 11.6 第 3 项。

- *Settings* → **Slots & auto-confirm** → **Confirm matching requests automatically**：**默认关、只有 ADMIN 能改**（STAFF 看得到，不能改）。
- 打开后，Admin API（`uvicorn app.main:app`，电脑 B 上就是自动启动的那个）**营业时间 9:00–17:30 每 3 分钟**只读查一次 GPiS：
  1. 只看还在 *Pending*、病人已经有 GPiS ContactID、有日期 / 时段 / 医生、日期还没过的请求。新病人第一次一定要员工按。
  2. **第一次看到**一个请求时，只记下那天这位病人在 GPiS 已经有没有预约：已经有 → 这个请求只能员工按；没有 → 之后出现的才算。
  3. 同一位病人、同一天、同一个时段、同一位医生、Remarks 有请求的疗程代码、时长一样（`1HOUR` ↔ 60 分钟），
     而且只有一个预约对得上 → 自动 *Confirmed*、马上发确认消息（和员工按的一样；发不了的进 *To tell patient*）。
  4. 对不上的照样留在 *Pending*，员工按 **Entered in GPiS ✓**。
- *Requests* 页面上面一行：自动确认关了 / 开了、**上次成功查 GPiS 的时间**；打开、营业时间、超过 15 分钟没成功 → **红字**。
  读 `GPiS_Dev` 时不跑（黄色提醒）。系统确认的卡片写 *Confirmed by: Auto-confirm (matched GPiS)*。
- 改表：migration **`0007`**（`clinic_settings` 多 3 栏、`appointment_requests.gpis_same_day_before`）。
- 电脑 B：下次更新要 `alembic upgrade head` 到 `0007`（`0006` 也还没装）；开关默认关，B 上**不要打开**（还没有 AI、没有请求）。
- 测试用的指令（在 `backend` 里，先启用 venv；只印请求编号、日期、时间、医生，没有名字）：
  - `python -m app.auto_confirm --dry-run`：读一次 GPiS，只印出会怎么做，不改资料（不管开关、营业时间）。
  - `python -m app.auto_confirm --once`：马上真的跑一次（开关要打开；不管营业时间）。
  - `python -m app.db.demo --auto-confirm-demo <自己的手机>`：给自己手机的对话加一个请求（Demo Auto、ContactID 990001、S+P、PHANG、下一个星期五 11:30），
    用一个假的 GPiS 跑两次：第一次没有 → 假装员工输入了 11:30 → 第二次自动确认、发到自己的手机。

### 更新（开发电脑）

```powershell
# backend（先启用 venv）
git pull
alembic upgrade head          # 0006 -> 0007
alembic current               # 0007 (head)
pytest                        # 应该 427 passed，没有 skipped

# frontend
cd ..\frontend
npm test                      # 应该 58 passed
npm run build                 # ✓ built
```

### 6a-2c 完成的条件（在开发电脑上测试）

视窗照「Phase 5a」的「使用」（视窗 1 Admin API、视窗 4 网页；第 6 项还要视窗 2、3）。改了 `.env` 要重开视窗 1。
**第 3、4 项读 `GPiS_Dev`：只看字，不要截图。**

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 上面的「更新」 | `0007 (head)`；`pytest` 427 passed、没有 skipped；`npm test` 58 passed；`npm run build` 成功 |
| 2 | 用 **STAFF** 帐号登入 → *Settings* → **Slots & auto-confirm** | 有 *Auto-confirm from GPiS*，勾选框没有勾、是灰的（不能改）；*Requests* 上面一行 *Auto-confirm is off: press Entered in GPiS for each request …* |
| 3 | 用 **ADMIN** 帐号 → 勾 *Confirm matching requests automatically* → **Save**（`.env` 没有 `REMINDER_SOURCE=demo`，读 `GPiS_Dev`） | *Saved.*；*Requests* 上面是黄色 *Auto-confirm is on, but it does not run with GPiS_Dev …* |
| 4 | 视窗 5：`python -m app.auto_confirm --dry-run` | `Auto-confirm does not run on GPiS_Dev: it has real patient names (D44). …` |
| 5 | `.env` 加 `REMINDER_SOURCE=demo` → 重开视窗 1 → *Requests* → **Refresh** | 上面一行 *Auto-confirm is on: …*，现在不是 9:00–17:30 的话后面多 *(it checks GPiS 9:00–17:30)*，*Last checked GPiS: never*（或上次的时间） |
| 6 | 用自己的手机传 `test 6a-2c` 给 Meta 测试号码 → 视窗 5：`python -m app.db.demo --auto-confirm-demo <你的手机>` | 印出 3 行：`Added pending request N: Demo Auto, S+P, PHANG, <下一个星期五> 11:30.`、`1) GPiS has nothing yet: first look recorded (… = False).`、`2) Staff entered 11:30 in GPiS: request N confirmed automatically, message sent to the phone.`；手机收到 `好的哟，已经帮你预约了哦😊`、`NAME: DEMO AUTO`、`TIME: 11:30 AM`、`DOCTOR: DR PHANG` |
| 7 | *Requests* → **Refresh** → *Confirmed* | Demo Auto 的卡片：*In GPiS* `<下一个星期五> 11:30 · Dr PHANG`、*Confirmed by* **Auto-confirm (matched GPiS)**、*Patient told … (sent by the system)* |
| 8 | 视窗 5：`python -m app.auto_confirm --once` → *Requests* → **Refresh** | 印出 `Source: Demo data. Pending requests looked at: …`（Demo Auto 已经确认了，不会再出现）；上面一行 *Last checked GPiS:* 变成现在的时间 |
| 9 | （9:00–17:30 才能测）视窗 1 开着、开关打开，等 3–4 分钟 → **Refresh** | *Last checked GPiS* 自己变成刚才的时间（背景每 3 分钟） |
| 10 | 清理：ADMIN 把勾拿掉 → **Save**；`.env` 拿掉 `REMINDER_SOURCE=demo` → 重开视窗 1；关掉视窗 3 | *Requests* 上面回到 *Auto-confirm is off …* |

### 云端容器的测试记录（2026-10-17，PostgreSQL 16、Python 3.11 + `requirements-lock.txt` 和 3.13、Node 22、只用假资料）

- `pytest` → 427 passed（新增 35 个）：疗程代码（`OR` 不配 `ORTHO`、`FOR`；`C/UP AFTER …`、`ISSUE CROWN`、`SCAN B`、`SC` 和 `SCAN B` 分得开）；
  第一次看只记下来、不确认；全部一样才确认；时段 / 医生 / 疗程 / 时长 / 取消 / 诊所联系人 / 日期不一样都不确认；1 hour 要 `1HOUR`；
  已经用过、第一次看就已经有、一个预约对两个请求、一个请求对两个预约都交给员工；营业时间（马来西亚时间 9:00–17:29）；
  跑两次：第一次记下、员工输入后确认、发消息、`handled_by` 空、再跑不会重复；dry-run 不改资料；没有 ContactID、日期过了不看；
  员工在两步之间改了请求就不确认；*Back to pending* 重新看；背景：开关关 / 下班不跑、记下上次成功和失败（不露出密码）、`GPiS_Dev` 不跑；
  员工接手的对话记成员工发的；STAFF 不能开、页面状态（还没查过 / 5 分钟前 / 20 分钟前）；`--auto-confirm-demo`。
- `npm test` → 58 passed（Settings 的开关 ADMIN 能改、STAFF 是灰的；Requests 上面一行的 4 种情况；*Auto-confirm (matched GPiS)*）；`npm run build` 成功。
- 容器的 `chatbot_dev`（假资料）：`alembic upgrade head` → `0007`；`--dry-run`、`--once`（开关关 → 拒绝）、`--auto-confirm-demo`（确认了；假对话超过 24 小时 → 进 *To tell patient*）；
  在「营业时间」跑一次背景的 `tick` → 记下上次查 GPiS 的时间、没有错误；uvicorn 启动时背景开始、日志没有错误。
- headless Chromium：ADMIN 在 *Slots & auto-confirm* 打开 → *Saved.* → *Requests* 上面一行 *Auto-confirm is on … Last checked GPiS: …*；写的时候找到、已经改好：勾选框被表单的样式拉宽。

