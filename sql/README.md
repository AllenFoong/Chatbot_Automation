# SQL（Phase 1：查空档；Phase 5b：只读帐号）

前两个文件都**只读** GPiS，在开发电脑的 `GPiS_Dev` 上执行（SSMS → 选 `GPiS_Dev` → **Ctrl+T** 文字结果 → **F5**）。
输出不含病人名字、电话、Remarks 原文。

| 文件 | 用途 |
|---|---|
| `check_available_slots.sql` | 输入日期、医生、疗程，算出每个时段还能不能约 |
| `find_test_dates.sql` | 列出一段日期里每天的预约概况，用来挑测试日期 |
| `create_readonly_login.sql` | 建只读帐号 `chatbot_reader`（D52），见下面「只读帐号」 |
| `drop_readonly_login.sql` | 拿掉 `chatbot_reader` |

## `check_available_slots.sql`

改文件开头的三个输入：

```sql
DECLARE @Date     date         = '2026-10-09';
DECLARE @DoctorID nvarchar(20) = N'PHANG';
DECLARE @Service  nvarchar(20) = N'S+P';
```

下面的"设置"（排班、午休、每格上限、能当第 3 人的疗程、公共假期、医生请假）已经搬到本系统的 PostgreSQL（Phase 3，`backend/app/db/`），系统用的是数据库里的设置。SQL 里这一份只是对照用的副本：数据库的设置改了之后，要对照就先把这里改成一样。

### 输出

**7a 总结**：`DayStatus`

| DayStatus | 意思 |
|---|---|
| `OK` | 正常，可以推荐空档 |
| `DOCTOR_NOT_WORKING` | 这位医生这天固定休息（PHANG 星期二；GOH 星期三、四） |
| `CLINIC_CLOSED` | 公共假期等（`@Closures`） |
| `DOCTOR_ON_LEAVE` | 本系统记录了请假（`@DoctorLeaves`） |
| `OFFDAY_IN_GPIS` | GPiS 里有 `OFF DAY` 记录 |
| `NEEDS_REVIEW` | 有诊所联系人的记录或看不懂的时长写法；空档照算，但 AI 不自动推荐，转员工 |
| `UNKNOWN_DOCTOR` | 排班表里没有这位医生 |

**7b 每个时段**

| 栏位 | 意思 |
|---|---|
| `Kind` | `BREAK` 午休、`LONG APPT` 被 1 hour 以上的预约整格占用、`AFTER HOURS` 最后一格之后（只给 1 hour 从最后一格开始用） |
| `Booked` | 已约人数（不算 `00:00`、`Canceled`、`Postpone`、占位、`OFF DAY`） |
| `Cap` | 这格最多几人：能当第 3 人的疗程（`OR`、`S+P`、`F`、`RETAINER`）且前后两格都不是 3 人 → 3，否则 2 |
| `Remaining` | 还剩几个名额 |
| `Can30` | 30 分钟预约能不能约这格 |
| `Can60` | 1 hour 预约能不能从这格开始（这格和下一格都要空、下一格不是午休） |

**7c 每条预约怎么被解读**：`AppointmentID`、时段、状态、占几格（`DurSlots`）、是不是占位 / `OFF DAY` / 看不懂的时长。没有名字和 Remarks，方便对照 GPiS 画面找出算错的那一条。

## 测试清单

先跑 `find_test_dates.sql` 挑日期，再逐一跑 `check_available_slots.sql`，拿 7b 和 GPiS 的 Appointment 画面对照。

| # | 测试 | 预期 |
|---|---|---|
| T1 | PHANG，星期二 | `DOCTOR_NOT_WORKING`，没有时段 |
| T2 | GOH，星期三或星期四 | `DOCTOR_NOT_WORKING` |
| T3 | PHANG，普通的一天 | 9:00–16:30；12:00、12:30 是 `BREAK`；`Booked` 和 GPiS 画面一致 |
| T4 | GOH，星期二 | 午休是 12:00、12:30（不是 13:00） |
| T5 | GOH，星期一 / 五 / 六 / 日 | 午休 13:00、13:30；最后一格 15:30；15:30 的 `Can60` 可以是 1 |
| T6 | 有 3 人格的日子（`MaxPerSlot = 3`） | 那格 `Remaining = 0`；前后格 `Cap = 2` |
| T7 | 同一天把 `@Service` 改成 `C/UP` | 所有格 `Cap = 2` |
| T8 | 有长预约的日子（`LongAppts > 0`） | 7c 那条 `DurSlots = 2`（或 3）；7b 被占的格 `Kind = LONG APPT`、`Remaining = 0` |
| T9 | 有 OFF DAY 的日子（`OffDay = 1`） | `OFFDAY_IN_GPIS` |
| T10 | 有诊所联系人记录的日子（`Placeholder = 1`） | `NEEDS_REVIEW` |
| T11 | 11:30（PHANG）、12:30（GOH 平日） | `Can60 = 0`（会跨进午休） |

结果贴回来之前不用遮任何东西：三个输出都没有病人资料。

## 测试记录（2026-10-04，`GPiS_Dev` = 2026-09-28 的快照）

| # | 日期 / 医生 / 疗程 | 结果 |
|---|---|---|
| 0 | 2026-10-09 PHANG S+P | ✅ `OK`，2 人；12:00、12:30 `BREAK`；16:30 `Can60 = 1` |
| T1 | 2026-09-01 PHANG | ✅ `DOCTOR_NOT_WORKING`；当天 13 条 `00:00` 提醒都判断为不占时段 |
| T2 | 2026-09-03 GOH | ✅ `DOCTOR_NOT_WORKING` |
| T3 | 2026-09-03 PHANG S+P | ✅ `OK`，15 人；`Can60` 只在下一格也空时为 1 |
| T4 | 2026-09-01 GOH S+P | ✅ 星期二午休 12:00、12:30；最后一格 15:30，`Can60 = 1`（W27） |
| T6 | 2026-09-02 PHANG S+P | ✅ 09:00、11:30、15:30 满 3 人；相邻格 `Cap = 2` |
| T7 | 2026-09-02 PHANG C/UP | ✅ 全部 `Cap = 2` |
| T8 | 2026-09-09 PHANG S+P | ✅ 16:00 的 1 hour 预约 `DurSlots = 2`，16:00、16:30 `LONG APPT`（员工另外在 16:00、17:00 多排了人，系统当作已满） |
| T9 | 2026-09-18 GOH | ✅ `OFFDAY_IN_GPIS` |
| T10 | 2026-09-30 PHANG | ✅ `NEEDS_REVIEW`；11:00 的诊所联系人记录不算病人 |

T5、T11 的规则已在 T4、T8、T3 里覆盖。测试后修正了两处显示：不能约的日子 `Remaining` 显示 0；被长预约占住的格 `Cap` 显示空白。

注意：`GPiS_Dev` 是 9 月 28 日的快照，之后新约的病人不在里面（例：09-30 截图有 12 位病人，快照只有 4 位）。正式上线必须读主机的实时数据（`docs/architecture.md` A1）。

## 只读帐号（D52、D59）

本系统读 GPiS 要用一个**只能看预约**的帐号 `chatbot_reader`，不用 `sa`（`sa` 什么都能改，规则 1、3）。

- 只给两个 `SELECT`：`dbo.Tbl_CAH_Appointment`（预约）、`dbo.Qry_CAH_Appointment`（视图，手机号码）。
- 明确 `DENY` `dbo.Tbl_User`（规则 5）。不能写、不能改数据库、不能执行 stored procedure。
- **读主机的 `GPiS` 时，系统每次连线都先检查帐号**：是 `sa` 或能写入就拒绝读取（`app/gpis.py`，D59）。
- 脚本**不改 GPiS 的资料、不改 `sa`、不改 SQL Server 设定、不用重开 SQL Server**。
- 密码不写在任何档案里（规则 6）：执行时传进去，再写进那台电脑的 `backend/.env`。

### 从电脑 B 的 config 看到的（W51，2026-10-09）

柜台有两台电脑：**A**（主机，有 SQL Server 和 GPiS 数据库）、**B**（另一台，本系统要装的地方）。下面是 **B** 的 `GPiS.exe.config`：

- `Database.Server` = `<主机A的IP>\SQLEXPRESS`：另一台的 GPiS 已经经局域网连 A 的 SQL Server（具名实例），
  所以 A 的网络、防火墙、SQL Server 的「SQL 帐号登入」**都已经开着**，只要加帐号，不用改设定、不用重开。
- `Database.User` = `sa`。密码那一行不看、不记录、不解密（规则 5）。

### 第一步：在开发电脑试（`GPiS_Dev`）

**1. 让开发电脑的 SQL Server 接受 SQL 帐号登入**（只做一次；主机 A 本来就开了，不用做）

SSMS → 在服务器名字上按右键 → *Properties* → *Security* → 选 *SQL Server and Windows Authentication mode* → OK
→ 再在服务器名字上按右键 → *Restart*。（只在开发电脑重开。）

**2. 产生密码、建帐号**（PowerShell，在仓库的 `sql` 文件夹里）

```powershell
# 24 个英文字母和数字，随机产生
$pw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
sqlcmd -S .\SQLEXPRESS -E -i create_readonly_login.sql -v DatabaseName="GPiS_Dev" ReaderPassword="$pw"
$pw          # 印出密码，下一步贴进 .env
```

最后印出的权限应该是：`GRANT CONNECT`、`GRANT SELECT` 两个（`Qry_CAH_Appointment`、`Tbl_CAH_Appointment`）、`DENY SELECT`（`Tbl_User`），
然后 `完成：chatbot_reader 只能读 …`。

**3. 改 `backend/.env`**（密码只写在这里）

```ini
GPIS_CONNECTION_STRING=DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost\SQLEXPRESS;DATABASE=GPiS_Dev;UID=chatbot_reader;PWD=<上一步的密码>;TrustServerCertificate=yes;ApplicationIntent=ReadOnly
GPIS_EXPECTED_DATABASE=GPiS_Dev
```

原来那行（`Trusted_Connection=yes`）前面加 `#` 留着，要改回来时用。

**4. 检查**（在 `backend` 里，venv）

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | `python -m app.reminders_cli --check-gpis` | `[OK] GPiS_Dev 有提醒名单要用的全部栏位` 和 `[OK] 帐号 chatbot_reader 是只读的`（有 `[提醒] 读得到 N 个表或视图` 的话贴回来） |
| 2 | `python -m app.reminders_cli 2026-09-02` | 和以前一样：Ready 25（视图读得到 = 手机号码都有） |
| 3 | `python -m app.cli 2026-09-02 PHANG S+P` | 和 Phase 2 的 T6 一样（空档也用这个帐号读） |
| 4 | （和第 2 步同一个 PowerShell 视窗，`$pw` 还在；不然把 `"$pw"` 换成 `.env` 里的密码）`sqlcmd -S .\SQLEXPRESS -U chatbot_reader -P "$pw" -d GPiS_Dev -Q "UPDATE dbo.Tbl_CAH_Appointment SET Remarks = Remarks WHERE 1 = 0"` | 错误 229：*The UPDATE permission was denied*（`WHERE 1 = 0` = 就算有权限也一行都不会改） |
| 5 | 把 `.env` 改回 `Trusted_Connection=yes`，再跑第 1 项 | `[!!] 帐号 … 不是只读的 …`（开发电脑用 Windows 帐号时是正常的），证明检查有效；跑完改回 `chatbot_reader` |
| 6 | 关掉 uvicorn；`sqlcmd -S .\SQLEXPRESS -E -i drop_readonly_login.sql -v DatabaseName="GPiS_Dev"`；再跑第 1 项 | `完成：chatbot_reader 已经拿掉`；第 1 项连不上（*Login failed*）。之后再照第 2 步建回来（新的密码），以后开发都用它 |

**不要**为了测试去 `SELECT` `Tbl_User`（规则 5）：读不到的检查用第 1 项（只看权限，不读资料）。

### 第二步：在主机 A 执行（装到柜台另一台电脑时，诊所同意后）

1. 在**柜台另一台电脑**（本系统要装的地方）照上面第 2 步的第一行产生密码，写进那台的 `backend/.env`：
   ```ini
   GPIS_CONNECTION_STRING=DRIVER={ODBC Driver 18 for SQL Server};SERVER=<主机A的IP>\SQLEXPRESS;DATABASE=GPiS;UID=chatbot_reader;PWD=<密码>;TrustServerCertificate=yes;ApplicationIntent=ReadOnly
   GPIS_EXPECTED_DATABASE=GPiS
   ```
   `<主机A的IP>` 照 `GPiS.exe.config` 的 `Database.Server`。
2. 把 `create_readonly_login.sql` 用 USB 带到**主机 A**，在 A 上开 PowerShell（营业时间也可以，不影响 GPiS；最好在病人少的时候）：
   ```powershell
   $pw = Read-Host "chatbot_reader 的密码"        # 打上一步的密码（不会存进 PowerShell 的历史记录）
   sqlcmd -S .\SQLEXPRESS -E -i create_readonly_login.sql -v DatabaseName="GPiS" ReaderPassword="$pw"
   Remove-Variable pw
   ```
   印出的权限要和开发电脑一样。A 上**不跑别的**（规则 1）。
3. 回到柜台另一台电脑：`python -m app.reminders_cli --check-gpis` → 两个 `[OK]`。
4. 连不上时：
   - *Login failed*：密码打错 → 在 A 上跑 `drop_readonly_login.sql`（`DatabaseName="GPiS"`），再从第 1 步重来。
   - SSL / TLS 的错误：SQL Server 2012 太旧，和 ODBC Driver 18 谈不拢加密。先把错误讯息贴回来再决定（可能要在连线字符串加 `Encrypt=no`：局域网里传的资料不加密，和 GPiS 现在一样）。

