# Backend（Phase 2：空档 API；Phase 3：本系统的 PostgreSQL）

- **Phase 2**：把 `sql/check_available_slots.sql` 的计算搬到 Python（FastAPI），让之后的 WhatsApp 和 AI Agent 可以调用。
  **只读** GPiS，计算规则和 SQL 完全一样；改规则时两边要一起改。
- **Phase 3**：本系统自己的 PostgreSQL（读写）：诊所设置（从代码搬进数据库）、WhatsApp 对话、预约请求。
  每张表的说明见 [`docs/architecture.md`](../docs/architecture.md) 第 4 节。

| 文件 | 内容 |
|---|---|
| `app/clinic_rules.py` | 诊所设置在程序里的样子（`ClinicRules`）；设置本身存在 PostgreSQL |
| `app/availability.py` | 空档计算（= SQL 第 3–7 节），不连接数据库 |
| `app/gpis.py` | 读 `Tbl_CAH_Appointment`：只有一条 `SELECT`；数据库名字不是 `GPIS_EXPECTED_DATABASE` 就拒绝 |
| `app/main.py` | API：`GET /availability`、`GET /health` |
| `app/cli.py` | 在终端印出和 SQL 7a / 7b / 7c 一样格式的结果，方便对照 |
| `app/phone.py` | 手机号转成国际格式（例 `60123456789`），WhatsApp 的号码和员工输入的号码才能比对 |
| `app/db/models.py` | 本系统的 12 张表（表结构以这里为准） |
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
   `seed` 第一次会印出 `clinic_settings: 新增 1 行`、`doctor_schedules: 新增 14 行`、`doctors: 新增 2 行`、`services: 新增 24 行`。
   再执行一次会说"没有新增"：它只补上没有的设置，不会覆盖员工改过的值。

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
