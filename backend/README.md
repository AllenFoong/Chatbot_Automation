# Backend（Phase 2：空档 API）

把 `sql/check_available_slots.sql` 的计算搬到 Python（FastAPI），让之后的 WhatsApp 和 AI Agent 可以调用。
**只读** GPiS，计算规则和 SQL 完全一样；改规则时两边要一起改。

| 文件 | 内容 |
|---|---|
| `app/clinic_rules.py` | 设置：排班、午休、每格上限、能当第 3 人的疗程、休息日、请假（= SQL 第 2 节；将来搬到 PostgreSQL） |
| `app/availability.py` | 空档计算（= SQL 第 3–7 节），不连接数据库 |
| `app/gpis.py` | 读 `Tbl_CAH_Appointment`：只有一条 `SELECT`；数据库名字不是 `GPIS_EXPECTED_DATABASE` 就拒绝 |
| `app/main.py` | API：`GET /availability`、`GET /health` |
| `app/cli.py` | 在终端印出和 SQL 7a / 7b / 7c 一样格式的结果，方便对照 |
| `tests/` | 单元测试，全部用假数据，不连接数据库 |

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

## 使用

每次打开新的 PowerShell 先 `cd backend` 再 `.\.venv\Scripts\Activate.ps1`。

**单元测试**（不需要数据库）：

```powershell
pytest
```

**终端对照**（读 `GPiS_Dev`）：

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

读 GPiS 失败时回 `503`，不会把连接字符串或错误细节回给调用方（细节在终端日志里）。

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
