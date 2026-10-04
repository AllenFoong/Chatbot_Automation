# SQL（Phase 1：查空档）

两个文件都**只读** GPiS，在开发电脑的 `GPiS_Dev` 上执行（SSMS → 选 `GPiS_Dev` → **Ctrl+T** 文字结果 → **F5**）。
输出不含病人名字、电话、Remarks 原文。

| 文件 | 用途 |
|---|---|
| `check_available_slots.sql` | 输入日期、医生、疗程，算出每个时段还能不能约 |
| `find_test_dates.sql` | 列出一段日期里每天的预约概况，用来挑测试日期 |

## `check_available_slots.sql`

改文件开头的三个输入：

```sql
DECLARE @Date     date         = '2026-10-09';
DECLARE @DoctorID nvarchar(20) = N'PHANG';
DECLARE @Service  nvarchar(20) = N'S+P';
```

下面的"设置"（排班、午休、每格上限、能当第 3 人的疗程、公共假期、医生请假）将来会搬到本系统的 PostgreSQL，由员工在 Admin Platform 修改；现在先写在 SQL 里。

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
