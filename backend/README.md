# Backend（Phase 2：空档 API；Phase 3：本系统的 PostgreSQL；Phase 4a：Admin Platform 的 API；Phase 5a：WhatsApp）

- **Phase 2**：把 `sql/check_available_slots.sql` 的计算搬到 Python（FastAPI），让之后的 WhatsApp 和 AI Agent 可以调用。
  **只读** GPiS，计算规则和 SQL 完全一样；改规则时两边要一起改。
- **Phase 3**：本系统自己的 PostgreSQL（读写）：诊所设置（从代码搬进数据库）、WhatsApp 对话、预约请求。
  每张表的说明见 [`docs/architecture.md`](../docs/architecture.md) 第 4 节。
- **Phase 4a**：员工登录 + Admin Platform 要用的 API（`/api/...`）。网页（4b）在 [`frontend/`](../frontend/README.md)。
- **Phase 5a**：接上 WhatsApp Cloud API：收病人的消息（webhook）、员工在 Admin Platform 回复、显示送达状态。开发时只用 Meta 的测试号码。

| 文件 | 内容 |
|---|---|
| `app/clinic_rules.py` | 诊所设置在程序里的样子（`ClinicRules`）；设置本身存在 PostgreSQL |
| `app/availability.py` | 空档计算（= SQL 第 3–7 节），不连接数据库 |
| `app/gpis.py` | 读 `Tbl_CAH_Appointment`：只有一条 `SELECT`；数据库名字不是 `GPIS_EXPECTED_DATABASE` 就拒绝 |
| `app/main.py` | API 入口：`GET /availability`、`GET /health`，加上 `app/api/` 的 Admin API |
| `app/auth.py` | 员工登录：Argon2 加密密码、session cookie、ADMIN / STAFF 权限 |
| `app/api/` | Admin API：登录、对话、预约请求、设置（医生、排班、疗程、假期、请假）、员工账号 |
| `app/whatsapp.py` | WhatsApp Cloud API：检查 webhook 签名、看懂 webhook、发文字消息（只发给允许的号码） |
| `app/webhook.py`、`app/webhook_main.py` | 收 WhatsApp webhook 的小程序（port 8001），开发时只有它经 tunnel 放上网 |
| `app/db/create_staff.py` | 建员工账号（第一个 ADMIN 用这个建） |
| `app/db/demo.py` | 放假资料到 `chatbot_dev`，方便看画面（只能用在 `_dev` 数据库） |
| `app/cli.py` | 在终端印出和 SQL 7a / 7b / 7c 一样格式的结果，方便对照 |
| `app/phone.py` | 手机号转成国际格式（例 `60123456789`），WhatsApp 的号码和员工输入的号码才能比对 |
| `app/db/models.py` | 本系统的 13 张表（表结构以这里为准；Phase 4 加了 `staff_sessions`，Phase 5 加了消息的送达状态） |
| `app/db/seed.py` | 设置的初始值（= SQL 第 2 节 + 疗程代码）；`python -m app.db.seed` 写入 |
| `app/db/rules.py` | 从 PostgreSQL 读设置 → `ClinicRules` |
| `app/db/conversations.py` | 收 / 发 WhatsApp 消息、转人工、WhatsApp 24 小时规则 |
| `app/db/customers.py` | 病人；用电话找病人（可能找到几位） |
| `app/db/appointment_requests.py` | 预约请求：`PENDING` → `CONFIRMED` / `REJECTED` / `CANCELLED` |
| `migrations/`、`alembic.ini` | Alembic：建表、改表结构的记录 |
| `tests/` | 测试，全部用假数据 |

## 在开发电脑上安装（Windows，只做一次）

1. 安装 **Python 3.12 或以上**（python.org，安装时勾选 *Add python.exe to PATH*）。
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
| `patients` | 这天已约的病人数 |
| `available_30` / `available_60` | 30 分钟 / 1 hour 预约可以开始的时段 |
| `slots` | 每个时段，栏位和 SQL 7b 一样（`booked`、`cap`、`remaining`、`can_30`、`can_60`） |
| `appointments` | 只有加 `debug=true` 才有：每条预约怎么被解读（= SQL 7c，只有 ID，没有名字和 Remarks） |

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
| `GET /api/doctors`、`services`、`closures`、`leaves`、`settings` | STAFF | 看设置 |
| 上面这些设置的 `POST` / `PUT` / `PATCH` / `DELETE` | **ADMIN** | 改医生、排班（一次 7 天）、疗程、休息日、请假、每格上限 |
| `POST /api/closures/import-holidays` | **ADMIN** | 预填一年的全国 + Johor 公共假期；农历新年多休的日子要自己加，回教节日是预估日期要核对 |
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

用 `sql/README.md` 测试记录里的日期，同一天分别跑 SQL 和 `python -m app.cli`，两边的 7a、7b、7c 必须完全一样：

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
pytest                                   # 应该 161 passed，没有 skipped
```

### 在 Meta 建测试用的 App（只做一次，用自己的 Facebook 帐号，**不要用诊所的**）

Meta 的画面常改，名字可能不完全一样；找不到时看 App Dashboard 里 WhatsApp 的 *Quickstart*。

1. 到 <https://developers.facebook.com/>，用自己的 Facebook 帐号登录，注册成为开发者。
2. *My Apps* → *Create App*，用途选 WhatsApp（*Connect with customers through WhatsApp*）。
   要选 Business portfolio 的话，自己建一个测试用的（例 `Chatbot Test`），**不要用诊所的**（D34）：
   开发和诊所的帐号分开，以后诊所的号码接上时，开发用的 App 碰不到真的病人消息；测试出错也不会连累诊所的帐号。
3. App 里 *WhatsApp* → *API Setup*：
   - 会有一个**测试号码**（*From*），下面是它的 **Phone number ID**。
   - *To* → *Manage phone number list* → 加上**自己的手机号码**（WhatsApp 会传验证码来）。
   - 按 *Send message*，手机应该收到 `hello_world`（确认测试号码能用）。
   - *Generate access token*：临时 token，大约 24 小时失效，失效了再按一次。
4. *App settings* → *Basic* → *App secret* → *Show*。
5. 打开 `backend\.env`，照 `.env.example` 加上 WhatsApp 那一段：
   - `WHATSAPP_VERIFY_TOKEN`：自己想一串英文字母和数字（第 7 步要填一样的）。
   - `WHATSAPP_APP_SECRET`、`WHATSAPP_ACCESS_TOKEN`、`WHATSAPP_PHONE_NUMBER_ID`：第 3、4 步的值。
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
9. 发布后手机传的消息还是没有出现在视窗 2：把 App 订阅到测试的 WhatsApp Business Account（WABA）。
   *API Setup* 上有 *WhatsApp Business Account ID*，在 PowerShell 执行（`…` 换成自己的值；token 不要贴到对话里）：
   ```powershell
   curl.exe -X POST "https://graph.facebook.com/v26.0/<WABA ID>/subscribed_apps" -H "Authorization: Bearer <access token>"
   ```
   回 `{"success":true}` 就好了。

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

| 情况 | 原因、怎么办 |
|---|---|
| Meta：*The callback URL or verify token couldn't be validated* | *Callback URL* 最后少了 `/webhook`；或暗号和 `.env` 不一样；或改了 `.env` 没重开视窗 2。先照第 7 步用浏览器试 |
| 浏览器试 `/health` 看到 Cloudflare 的错误页（例 1033、502） | 视窗 2（port 8001）没开，或 cloudflared 指错 port |
| 试 `/webhook?...` 看到 `Wrong verify token` | 网址里的暗号和 `.env` 不一样；改了 `.env` 要重开视窗 2 |
| 试 `/webhook?...` 看到 `WHATSAPP_VERIFY_TOKEN is not set` | `.env` 没有这一行，或视窗 2 在 `.env` 加好之前就开了 |
| Meta 的 *Test* 按钮送得到，手机传的消息送不到 | App 还没发布（第 8 步）；或 App 没订阅 WABA（第 9 步） |
| 视窗 2 出现 `401` | `WHATSAPP_APP_SECRET` 填错（签名对不上） |

### Phase 5a 完成的条件（在开发电脑上测试）

1. `alembic current` → `0003 (head)`；`pytest` → **161 passed**，没有 skipped。
2. `frontend` 里 `npm test` → **35 passed**；`npm run build` 成功。
3. 照「使用」开 4 个视窗，在 Meta 按 *Verify and save* 成功。
4. 照下面的清单做一次：

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 用手机 WhatsApp 传 `Hi, I want to book scaling` 给测试号码 | 15 秒内 Admin Platform *Conversations* 多一段对话（*Needs staff*），名字是你的 WhatsApp 名字；原因 *AI replies are not turned on yet* |
| 2 | 在这段对话下面输入回复 → *Send* | 手机收到；画面上这条消息显示 *Sending…* → *Delivered*；在手机上打开后变 *Read*；对话显示由你负责 |
| 3 | 输入回复后按 `Ctrl + Enter` | 一样送出 |
| 4 | 用手机传一张照片（加一句说明） | 画面显示 `[Image] 说明` |
| 5 | 把 `.env` 的 `WHATSAPP_ALLOWED_RECIPIENTS=` 暂时改成空的 → 重开视窗 1 → 在你自己的对话回复 `Hello`；做完改回来、再重开视窗 1 | 红字 *This number is not in WHATSAPP_ALLOWED_RECIPIENTS*；手机收不到（允许名单这道保险有效） |
| 6 | 浏览器打开 `https://….trycloudflare.com/docs` 和 `…/api/auth/me` | 都是 `{"detail":"Not Found"}`：网上只看得到 webhook |
| 7 | 视窗 2 的日志 | 只有 `POST /webhook … 200`，没有消息内容和电话号码 |

截图只用自己手机和假资料的对话；token、secret、App 的画面要遮住。

### 云端容器的测试记录（2026-10-06，PostgreSQL 16、只用假资料、不连 Meta）

- `pytest` → 161 passed（新增 30 个：webhook、签名、发消息、员工回复、送达状态、migration 0003）。
- 在 `chatbot_dev` 跑过整个流程，自己扮演 Meta：
  - 用签了名的假 webhook 送进病人的消息：新对话转给员工，重送的同一条只存一次，签名不对回 `401`、不存。
  - 网页回复时，Cloud API 换成本机假的 Graph API：收到的网址、token、内容都正确。
  - 假的 status webhook 把消息变成 *Read*，*failed* 时显示原因。
  - 不在 allowlist 的号码被拒绝，根本没发出去。
  - webhook 小程序的 `/docs`、`/api/...` 都是 404；日志里没有电话号码和消息内容。
