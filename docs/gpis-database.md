# GPiS 数据库

> 本文件**不包含任何病人资料、密码或诊所识别信息**。所有查询都只针对表结构、设置表或统计数字。
> 最后更新：2026-09-30

## 1. GPiS 程序概况

- 手上只有**安装/部署文件夹**，**没有源代码**（找不到 `.vb` / `.cs` / `.vbproj` / `.csproj`）。
- **.NET Framework 3.5 WinForms 桌面程序**，使用 DevExpress v10.1（含 `XtraScheduler` 预约日历）和 Crystal Reports。
- 开发商：GPiS Solutions Sdn Bhd，文件夹内附 `EULA.rtf`。
- **局域网多终端**：每台电脑的 `GPiS.exe.config` 设有 `Room.Name` / `Counter.Name`，并通过 `System Manager.IP` + 端口 `30001` 连接一个 System Manager 服务。

### `GPiS.exe.config` 数据库设置

| Key | 值 | 含义 |
|---|---|---|
| `Database.Server` | `.\SQLEXPRESS` | SQL Server Express，本机实例 |
| `Database.Name` | `GPiS` | 数据库名 |
| `Database.User` | `sa` | 最高权限账号 |
| `Database.Password` | *（已加密，不记录、不解密）* | |

## 2. 主机上的数据库

| 项目 | 值 |
|---|---|
| 版本 | SQL Server **2012** Express（`MSSQL11.SQLEXPRESS`） |
| 数据库名 | `GPiS` |
| 数据文件 | `C:\Program Files\Microsoft SQL Server\MSSQL11.SQLEXPRESS\MSSQL\DATA\GPiS.mdf`（约 454 MB） |
| 日志文件 | 同目录 `GPiS_log.ldf` |
| 逻辑文件名 | `GPiS (<诊所名>)_Data` / `GPiS (<诊所名>)_Log`（用 T-SQL `RESTORE ... WITH MOVE` 时需要；用 SSMS 还原则会自动处理） |
| 历史备份 | 最后一次在 2021 年，放在 `C:\WINDOWS\TEMP\`（随时可能被清掉） |

## 3. 结构概览

共约 200 个表/视图。完整结构导出在本地文件 `gpis_schema.csv`（不放进仓库）。

| 前缀 | 类型 | 数量（约） |
|---|---|---|
| `Tbl_` | 表（真实数据） | 131 |
| `Qry_` | 视图 | 66 |
| `Rpt_` | 报表用视图 | 4 |
| `Delete_` | 旧/删除用表 | 2 |

## 4. 预约相关的表

### `Tbl_CAH_Appointment`（核心预约表）

| 字段 | 类型 | 可空 | 备注 |
|---|---|---|---|
| `AppointmentID` | int | NO | **不是自动编号**（`IsIdentity = 0`） |
| `AppointmentDate` | datetime | NO | 是否带时间待确认 |
| `TimeSlot` | nvarchar(10) | YES | 文字，如 `"10:30"` |
| `ContactID` | int | YES | → `Tbl_CAH_Contact.ContactID` |
| `ContactName` | nvarchar(100) | YES | 病人名字（冗余存储） |
| `DoctorID` | nvarchar(20) | YES | → `Qry_CAH_Resource_Sch.Id` |
| `DoctorName` | nvarchar(100) | YES | |
| `AssignedBy` | nvarchar(100) | YES | 登记的员工 |
| `Status` | nvarchar(20) | YES | → `Tbl_CAH_RefAppointmentStatus` |
| `Remarks` | nvarchar(500) | YES | |
| `Duration` | nvarchar(50) | YES | 文字，格式待确认 |

没有 trigger。

### 其他相关表 / 视图

| 名称 | 用途 |
|---|---|
| `Tbl_CAH_RefTimeSlot` (`TimeSlot`) | 所有可选时段 |
| `Tbl_CAH_RefAppointmentStatus` (`Status`) | 所有预约状态 |
| `Qry_CAH_Resource_Sch` (`Id`, `Caption`) | 医生列表（Scheduler 资源） |
| `Qry_CAH_Appointment` | 预约 + 病人 `HPNo`（手机）、`HouseNo`、`NRIC`，可用于**把 WhatsApp 号码对应到病人** |
| `Qry_CAH_Appointment_Sch` | 给 DevExpress Scheduler 用：`StartDate`、`EndDate`(smalldatetime)、`Duration`、`Subject` 等 |
| `Tbl_CAH_Contact` | 病人主表（`ContactID`、`Name`、`NRIC`、`DOB` 等） |
| `Tbl_CAH_ContactNumbers` | 病人联系方式（`ContactID`、`DisplayName`、`DisplayType`、`DisplayValue`） |
| `Tbl_CAH_Queue` | 当天现场排队（walk-in），与预约分开 |
| `Tbl_User` | 员工账号，`Password` 为 `nvarchar(20)`，**很可能是明文**。本系统**绝不读取** |

### 设置表的实际内容

- **`Tbl_CAH_RefTimeSlot`**：`00:00` 到 `23:30`，每 30 分钟一格，共 48 格。**GPiS 没有营业时间设置。**
- **`Tbl_CAH_RefAppointmentStatus`**：`Waiting`、`Canceled`、`Postpone`、`Closed`、`Rearrange`、`Confirmed`
- **`Qry_CAH_Resource_Sch`（医生）**：`PHANG`、`GOH`、`DOCTOR`（`DOCTOR` 疑似"不指定医生"的通用账号）

- **营业时间**：GPiS 里没有，由诊所提供：9:00–17:00，最后预约 16:30，星期六、日营业（和平日一样），全国 + Johor 公共假期休息；医生排班、午休见 [`clinic-workflow.md`](clinic-workflow.md) 第 1 节。

### 状态是否占用时段（按 staff 实际用法，待统计验证）

员工实际只用 `Confirmed`、`Closed`、`Canceled`（详见 [`clinic-workflow.md`](clinic-workflow.md) 第 5 节）。

| 状态 | 含义 | 占用时段？ |
|---|---|---|
| Confirmed | 预约确定 | ✅ |
| Closed | 病人已到店、已登记（员工手动改） | ✅（当天仍占用医生时间） |
| Canceled | 病人取消 | ❌ |
| Postpone | 很少用（改期是直接改原记录） | ❌ |
| Waiting / Rearrange / 空 | 很少用 | ✅（宁可少推荐，不重复预约） |

另外两种记录**不按状态判断**：`TimeSlot = '00:00'` 是提醒 / 未定时间，**不占用**；联系人是诊所本身的是"占位记录"，要转人工（见 `clinic-workflow.md` 第 4 节）。

## 5. 跑过的 SQL

均使用 Windows 身份验证（`sqlcmd -S .\SQLEXPRESS -E`），只读。①–⑤ 在**主机**上执行。

**① 导出表结构** → `gpis_schema.csv`，结果见第 3、4 节

```sql
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

**② 数据库文件位置** → 结果见第 2 节

```sql
SELECT name, physical_name, size*8/1024 AS SizeMB
FROM sys.master_files WHERE database_id = DB_ID('GPiS');
```

**③ 备份记录** → 最近三次：2021-07-13（两次，`C:\WINDOWS\TEMP\`）、2020-12-14（`D:\`）

```sql
SELECT TOP 5 b.backup_finish_date, m.physical_device_name
FROM msdb.dbo.backupset b
JOIN msdb.dbo.backupmediafamily m ON b.media_set_id = m.media_set_id
WHERE b.database_name = 'GPiS'
ORDER BY b.backup_finish_date DESC;
```

**④ 设置表、自动编号、trigger** → `gpis_ref.txt`，结果见第 4 节

```sql
SELECT * FROM Tbl_CAH_RefTimeSlot;
SELECT * FROM Tbl_CAH_RefAppointmentStatus;
SELECT * FROM Qry_CAH_Resource_Sch;
SELECT COLUMNPROPERTY(OBJECT_ID('Tbl_CAH_Appointment'),'AppointmentID','IsIdentity');  -- 0
SELECT name FROM sys.triggers WHERE parent_id = OBJECT_ID('Tbl_CAH_Appointment');     -- 无
```

**⑤ 备份**（成功）

```sql
BACKUP DATABASE GPiS TO DISK='D:\GPiS_Backup\GPiS_copy.bak' WITH COPY_ONLY, INIT;
```

第一次报 `Operating system error 3`（文件夹不存在），用 `New-Item -ItemType Directory -Path "D:\GPiS_Backup" -Force` 建好后成功。

## 6. 待验证的问题

业务流程方面的问题（W1–W18）在 [`clinic-workflow.md`](clinic-workflow.md) 第 7 节。

| # | 问题 | 目前所知（2026-09-30） | 验证方式 |
|---|---|---|---|
| Q1 | 各状态实际使用多少？哪些占用时段？ | ✅ 统计 A 证实主要用 `Closed` / `Confirmed` / `Canceled`；另有 1 条 `Calling`（不在 `RefAppointmentStatus`，说明状态没有约束） | 统计 A ✅；B13 看未来预约 |
| Q2 | `Duration` 的格式？一个预约会占多个 30 分钟格吗？ | 会。staff 在 Remarks 写 `1 hour`，该病人独占这一格和下一格（员工看情况写，常见于 RCT、IMPLANT、SCAN B、VENEER；没写的就是 30 分钟）；`Duration` 字段可能没用。✅ 统计 A：`Duration` 99.9% 是 `30`（默认值），证实员工不用这个字段 | 统计 A ✅、B5 |
| Q3 | `AppointmentDate` 只有日期还是带时间？ | ✅ 只有日期（时间部分全是 00:00:00），时间只看 `TimeSlot` | 统计 A ✅ |
| Q4 | 诊所实际营业时间？ | ✅ 9:00–17:00，最后预约 16:30；星期六、日营业，公共假期休息（诊所提供）。⚠️ 统计 A：历史上 17:00–20:30 仍有约 1.2 万条预约，和"17:00 下班"不符，可能是以前的夜诊或已离职医生 | 统计 B1、B2 核对（看最近 12 个月）。🔶 B2：最近 12 个月 17:00 以后几乎没有预约，营业时间对得上；但**午休的前半格（PHANG 12:00、GOH 13:00）仍有预约**，GOH 16:00 以后很少（见 B 的结果） |
| Q5 | 同一医生、同一时段是否允许多个预约？ | ✅ 允许，一般 2 人；第 3 人只限 `OR`、`S+P`、`F`、`RETAINER`；相邻两格不能都是 3 人。统计 A 的"同格最多"前 10 名全是每月 1 号的 `00:00`（提醒），没有参考价值 | 统计 B3 看分布（已排除 00:00）。⚠️ B3：每格 1 人 2,433 / 2 人 1,592 / 3 人 641 / **4 人以上 127 格**，和"最多 3 人"不符 | 统计 C2、C3。✅ W22：诊所确认每格最多 3 人，4 人以上是员工多排的 |
| Q6 | 数据是否仍在使用（最新预约日期）？ | ✅ 仍在使用：2017-11-18 ～ 2027-04-30，共 104,537 条 | 统计 A ✅ |
| Q7 | `DOCTOR` 资源代表什么？ | — | 询问诊所 |
| Q8 | GPiS 如何产生新的 `AppointmentID`？ | 诊所说员工不会 `Delete`，改期是 `Edit` 原记录（`AppointmentID` 不变） | 在 `GPiS_Dev` 上观察，或用 SQL Profiler 看 GPiS 发出的 SQL；B9 若空洞很多，说明编号方式不是 MAX+1 或有其他删除来源。⚠️ B9：ID 0 ～ 130,067，**空洞 25,531 个（约 20%）**，说明以前有删除，或 GPiS 会跳号 | W26 |
| Q9 | 手机号格式（有无 `+60`、空格、`-`）？能否可靠匹配 WhatsApp 号码？ | 格式混杂：纯数字、带空格、带 `-`，截图里没见到 `+60`；**有家人共用号码**。✅ B10：约 79% 是 `0` 开头的本地号码（多数带 `-`）；约 2,170 个 `+` 开头（可能是新加坡等外国号码）；`60` 开头只有 8 个；空 434 个。B11：**2,243 个号码**对应多于一位病人 | B10 ✅、B11 ✅；C6 看 `+` 和其他开头的前缀 |

### 统计查询 A（在 `GPiS_Dev` 上执行，只含统计，回答 Q1–Q6）

```sql
SET NOCOUNT ON;
SELECT MIN(AppointmentDate) AS FirstDate, MAX(AppointmentDate) AS LastDate, COUNT(*) AS Total FROM Tbl_CAH_Appointment;
SELECT Status, COUNT(*) AS N FROM Tbl_CAH_Appointment GROUP BY Status;
SELECT Duration, COUNT(*) AS N FROM Tbl_CAH_Appointment GROUP BY Duration;
SELECT DoctorID, COUNT(*) AS N FROM Tbl_CAH_Appointment GROUP BY DoctorID;
SELECT TimeSlot, COUNT(*) AS N FROM Tbl_CAH_Appointment GROUP BY TimeSlot ORDER BY TimeSlot;
SELECT TOP 10 CONVERT(varchar(10), AppointmentDate, 120) AS D, TimeSlot, DoctorID, COUNT(*) AS SameSlot
  FROM Tbl_CAH_Appointment
  GROUP BY CONVERT(varchar(10), AppointmentDate, 120), TimeSlot, DoctorID
  HAVING COUNT(*) > 1 ORDER BY SameSlot DESC;
SELECT TOP 5 CONVERT(varchar(19), AppointmentDate, 120) AS RawDate FROM Tbl_CAH_Appointment;
```

执行：`sqlcmd -S .\SQLEXPRESS -E -d GPiS_Dev -W -s "," -Q "<上面的 SQL>" -o "$HOME\Desktop\gpis_stats.txt"`

#### 统计查询 A 的结果（2026-09-30，已执行）

开发电脑：SQL Server **17.0（2025）** Express，备份还原后改名为 `GPiS_Dev`。（新版本可还原旧备份，但**不能再备份回主机的 2012**。）

| 项目 | 结果 |
|---|---|
| 日期范围 / 总数 | 2017-11-18 ～ 2027-04-30，**104,537** 条 |
| `AppointmentDate` | 时间部分全是 `00:00:00` |
| `Status` | Closed 80,158；Confirmed 17,514；Canceled 6,189；Rearrange 458；Waiting 114；Postpone 103；Calling 1 |
| `Duration` | `30`：104,449（99.9%）；60：59；45：9；15：8；90：6；5：4；120：2 |
| `DoctorID` | 14 个不同的值（多数是以前的医生），PHANG 约占 64%；另有 `admin` 3 条（录入错误） |
| `TimeSlot` | 09:00–16:30 每格 1.5k–8.3k（12:30 明显较少）；17:00–20:30 共约 1.2 万；`00:00` 781；其他凌晨时段各 1–8 条（录入错误） |
| 同医生同时段最多 | 前 10 名全是**每月 1 号**、`00:00`、PHANG，最多 20 条 → 提醒，不是预约（和 `clinic-workflow.md` 4.1 一致） |

### 统计查询 B（在 `GPiS_Dev` 上执行，验证 `clinic-workflow.md` 的业务规则）

只输出统计数字、时段、代码片段，不输出病人名字和号码。**尚未在真实数据库上跑过**，报错就把错误信息带回来。

```sql
SET NOCOUNT ON;
SET DATEFIRST 1;  -- 1 = 星期一 … 7 = 星期日

-- B1 各医生按星期几的预约数（最近 12 个月）→ 验证休息日、周末是否营业
SELECT DoctorID, DATEPART(weekday, AppointmentDate) AS WD, COUNT(*) AS N
FROM Tbl_CAH_Appointment
WHERE AppointmentDate >= DATEADD(month, -12, GETDATE())
  AND ISNULL(Status, '') <> 'Canceled' AND ISNULL(TimeSlot, '') <> '00:00'
GROUP BY DoctorID, DATEPART(weekday, AppointmentDate)
ORDER BY DoctorID, WD;

-- B2 PHANG、GOH 各时段 × 星期几的预约数（最近 12 个月）→ 验证营业时间、午休、休息日
--    改成横向表格（星期一到日是栏位），行数从约 500 行减到约 50 行，方便贴回来
SELECT DoctorID, TimeSlot,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 1 THEN 1 ELSE 0 END) AS Mon,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 2 THEN 1 ELSE 0 END) AS Tue,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 3 THEN 1 ELSE 0 END) AS Wed,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 4 THEN 1 ELSE 0 END) AS Thu,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 5 THEN 1 ELSE 0 END) AS Fri,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 6 THEN 1 ELSE 0 END) AS Sat,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 7 THEN 1 ELSE 0 END) AS Sun
FROM Tbl_CAH_Appointment
WHERE AppointmentDate >= DATEADD(month, -12, GETDATE())
  AND DoctorID IN ('PHANG', 'GOH')
  AND ISNULL(Status, '') <> 'Canceled' AND ISNULL(TimeSlot, '') <> '00:00'
GROUP BY DoctorID, TimeSlot
ORDER BY DoctorID, TimeSlot;

-- B3 同一医生同一时段有几个预约的分布 → 验证"一般 2 人，最多 3 人"
SELECT SameSlot, COUNT(*) AS Slots FROM (
  SELECT CONVERT(varchar(10), AppointmentDate, 120) AS D, TimeSlot, DoctorID, COUNT(*) AS SameSlot
  FROM Tbl_CAH_Appointment
  WHERE AppointmentDate >= DATEADD(month, -12, GETDATE())
    AND ISNULL(Status, '') NOT IN ('Canceled', 'Postpone')
    AND ISNULL(TimeSlot, '') <> '00:00'
  GROUP BY CONVERT(varchar(10), AppointmentDate, 120), TimeSlot, DoctorID
) t
GROUP BY SameSlot ORDER BY SameSlot;

-- B4 00:00 记录的状态分布（诊所说提醒处理完不会改 Closed，W4）
SELECT Status, COUNT(*) AS N FROM Tbl_CAH_Appointment WHERE TimeSlot = '00:00' GROUP BY Status;

-- B5 Remarks 里表示时长的写法（只取关键字前后几个字，出现少于 3 次的不显示）
--    重要：Remarks 写的 1 hour 是判断时长的唯一依据，写法要找齐
SELECT k.Kw, s.Snippet, COUNT(*) AS N
FROM Tbl_CAH_Appointment a
CROSS APPLY (VALUES ('HOUR'), ('HR'), ('1H'), ('MIN')) AS k(Kw)
CROSS APPLY (SELECT CHARINDEX(k.Kw, UPPER(a.Remarks)) AS P) AS p
CROSS APPLY (SELECT SUBSTRING(UPPER(a.Remarks), CASE WHEN p.P > 4 THEN p.P - 4 ELSE 1 END, LEN(k.Kw) + 6) AS Snippet) AS s
WHERE p.P > 0
GROUP BY k.Kw, s.Snippet
HAVING COUNT(*) >= 3
ORDER BY k.Kw, N DESC;

-- B6 占位记录（联系人是诊所本身，名字含 DENTAL）的联系人 ID 和数量
SELECT ContactID, COUNT(*) AS N, MIN(AppointmentDate) AS FirstDate, MAX(AppointmentDate) AS LastDate
FROM Tbl_CAH_Appointment
WHERE ContactName LIKE '%DENTAL%'
GROUP BY ContactID;

-- B7 占位记录的写法（Remarks 是员工写的安排，不是病人资料）
SELECT TOP 50 DoctorID, TimeSlot, Remarks, COUNT(*) AS N
FROM Tbl_CAH_Appointment
WHERE ContactName LIKE '%DENTAL%'
GROUP BY DoctorID, TimeSlot, Remarks
ORDER BY N DESC;

-- B8 没有联系人的预约数（可能是其他占位写法）
SELECT COUNT(*) AS NoContact FROM Tbl_CAH_Appointment WHERE ContactID IS NULL OR ContactID = 0;

-- B9 AppointmentID 的范围和空洞数 → 间接看员工是否常用 Delete（Q8）
SELECT MIN(AppointmentID) AS MinID, MAX(AppointmentID) AS MaxID, COUNT(*) AS Total,
       MAX(AppointmentID) - MIN(AppointmentID) + 1 - COUNT(*) AS Gaps
FROM Tbl_CAH_Appointment;

-- B10 手机号格式（只统计格式，不输出号码）→ Q9
SELECT Prefix, Sep, COUNT(*) AS N FROM (
  SELECT
    CASE WHEN ISNULL(LTRIM(HPNo), '') = '' THEN 'EMPTY'
         WHEN HPNo LIKE '+%'  THEN 'PLUS'
         WHEN HPNo LIKE '60%' THEN '60'
         WHEN HPNo LIKE '0%'  THEN '0'
         ELSE 'OTHER' END AS Prefix,
    CASE WHEN HPNo LIKE '%-%' THEN 'DASH'
         WHEN HPNo LIKE '% %' THEN 'SPACE'
         ELSE 'PLAIN' END AS Sep
  FROM (SELECT DISTINCT ContactID, HPNo FROM Qry_CAH_Appointment) c
) t
GROUP BY Prefix, Sep ORDER BY N DESC;

-- B11 一个号码对应多位病人的数量（家人共用号码）→ Q9
SELECT COUNT(*) AS SharedNumbers FROM (
  SELECT REPLACE(REPLACE(HPNo, '-', ''), ' ', '') AS Num
  FROM Qry_CAH_Appointment
  WHERE ISNULL(LTRIM(HPNo), '') <> ''
  GROUP BY REPLACE(REPLACE(HPNo, '-', ''), ' ', '')
  HAVING COUNT(DISTINCT ContactID) > 1
) t;

-- B12 OFF DAY 记录：用什么联系人、放在哪个时段（W10）
SELECT CASE WHEN ContactName LIKE '%DENTAL%' THEN 'CLINIC' ELSE 'OTHER' END AS Contact,
       TimeSlot, DoctorID, Status, COUNT(*) AS N
FROM Tbl_CAH_Appointment
WHERE Remarks LIKE '%OFF%DAY%'
GROUP BY CASE WHEN ContactName LIKE '%DENTAL%' THEN 'CLINIC' ELSE 'OTHER' END, TimeSlot, DoctorID, Status
ORDER BY N DESC;

-- B13 未来预约（备份日 2026-09-28 之后）的状态分布 → 验证"将来的日期不会出现 Closed"（Q1）
SELECT Status, COUNT(*) AS N FROM Tbl_CAH_Appointment
WHERE AppointmentDate >= '2026-09-28'
GROUP BY Status;
```

#### 统计查询 B 的结果（2026-10-02，已执行）

"最近 12 个月"= 2025-10-02 起，**包含已经约好的未来预约**。

| # | 结果 | 结论 |
|---|---|---|
| B1 | PHANG 星期二只有 6 条，其他每天 870–1,440 条；GOH 星期三 1 条、星期四 5 条，其他每天 127–235 条；**CHER 也有约 310 条**（星期三只有 1 条）；`DOCTOR` 1 条 | 休息日和诊所说的一致；周末照常营业 ✅。**但 CHER 是第三位医生**，诊所只说了 2 位（W19） |
| B2 PHANG | 9:00–16:30 每格 32–120 条；**12:00 每天 15–21 条**；12:30 几乎为 0；17:00 平日 7–13 条，17:30 以后几乎没有 | 实际只有 **12:30 一格**完全空着；12:00 仍有约正常量 1/4 的预约（W20） |
| B2 GOH | 13:00 平日 / 周末每天 9–19 条，**13:30 几乎为 0**；星期二 12:00 有 14 条、**12:30 只有 3 条**；16:00 只有 2–4 条，16:30 几乎为 0 | 实际空着的是**午休的后半格**；GOH 实际 **16:00 以后很少看诊**（W20、W21） |
| B3 | 每格 1 人：2,433；2 人：1,592；3 人：641；4 人：116；5 人：10；6 人：1 | 3 人很常见（约 14%）；**4 人以上 127 格**，和"最多 3 人"不符（W22） |
| B4 | `00:00`：Closed 393、Confirmed 234、Canceled 96、Rearrange 56、Postpone 1、Waiting 1 | 状态混杂，和"提醒不改状态"一致；`00:00` 本来就不占时段 ✅ |
| B5 | 时长写法很多：`1HOUR`、`1 HOUR`、`(1H)`、`1HR`、`*1HOUR*`、`1HOURS`、`1HOUR!!!`；**还有 `1.5 HOUR(S)`、`1.30HOUR`、`1HOURS 30`**；`MIN` 有 `30MIN!!!!`、`20MIN!!!!`、`15MIN`、`10MIN`、`45 MINS` 等 | 要用**正则表达式**判断时长，不能只找 `1 hour`；**1.5 小时 = 占 3 格**（W23）；`xxMIN` 的意思不明（W24）。另外 `REMIND`、`COMING` 也被 `MIN` 匹配到（误报）。⚠️ 片段里出现了**病人名字的一部分** → **Remarks 也算个人资料** |
| B6 | 联系人含 `DENTAL` 的只有 1 个联系人（ContactID 34094），共 10 条（2024-12 ～ 2026-09） | 诊所自己当联系人的记录很少 |
| B7 | 写法：`EAT`（CHER 12:00，3 次）、`AL`、`GO BANK`、`1130 FIRST APPT`、一条马来文备注（crown 还没好）；**也有正常疗程** `1ST C/UP RCT (G)`、`PT COME XLA (G)`、`S+P(C)` | 诊所联系人**不只用来占位**，也用来记真实疗程 → **不能靠联系人判断占位记录**。`(C)` = CHER |
| B8 | 没有联系人的预约：4 条 | 可忽略 |
| B9 | ID 0 ～ 130,067，共 104,537 条，**空洞 25,531** | 以前有删除，或 GPiS 会跳号（W26）；本系统同步时要能处理"预约消失" |
| B10 | `0`+DASH 14,451；`0`+PLAIN 3,515；`0`+SPACE 1,669；`+` 开头约 2,170；OTHER 564；空 434；`60` 开头 8 | 号码标准化：去掉非数字 → `0` 开头改成 `60` 开头；`+` 开头直接用（C6 再确认国家码） |
| B11 | 2,243 个号码对应多于一位病人 | 家人共用号码**非常普遍**，AI 一定要先问是哪一位 ✅ |
| B12 | `OFF DAY` 记录共约 31 条，**联系人都不是诊所**；时段在 `00:00`（多数，GOH）、`13:00`（GOH）、`12:00`（PHANG、GOH、LAU） | 占位记录要**按 Remarks 判断**，不按联系人；`OFF DAY` 记录这么少，**医生请假多数没有记进 GPiS**（W25） |
| B13 | 2026-09-28 之后：Confirmed 167、Closed 16、Canceled 6 | 未来预约主要是 `Confirmed`；Closed 16 条应该是备份当天（9-28）已到店的 ✅ |

#### 对空档规则的影响

1. **1 hour 判断改用正则**：把 Remarks 转大写、去掉空格后匹配 `数字 + H / HR / HOUR(S)`，`1.5` / `1.30` / `1HOURS30` = 90 分钟；占几格 = 分钟数 ÷ 30（无条件进位）。解析不了但有 `HOUR` 字样的，当天转人工。
2. **占位记录按 Remarks 判断**：任何联系人、任何时段（包括 `00:00`）的 Remarks 含 `OFF DAY` → 该医生当天没有空档。
3. **医生请假要在本系统另外记录**：GPiS 里的 `OFF DAY` 太少，不可靠 → Admin Platform 要有"医生请假"功能（W25）。
4. **午休、GOH 的最后时段、每格上限**：等诊所回答 W20–W22 再定；在那之前，按 D15"宁可少推荐"，照原规则封锁整个午休，GOH 的最后时段暂定 16:00。
5. **Remarks 含病人名字**：Remarks 原文不能发给 LLM，也不能写进仓库；只能取出疗程代码和时长后再用。

### 统计查询 C（在 `GPiS_Dev` 上执行，跟进 B 的发现）

只输出统计数字和前缀，不输出名字和号码。C5 会显示 `OFF DAY` 记录的 Remarks，贴回来之前先检查。

```sql
SET NOCOUNT ON;
SET DATEFIRST 1;

-- C1 CHER 最近 24 个月每月的预约数 → 是长期医生、兼职，还是已经离职（W19）
SELECT CONVERT(varchar(7), AppointmentDate, 120) AS YM, COUNT(*) AS N
FROM Tbl_CAH_Appointment
WHERE DoctorID = 'CHER' AND AppointmentDate >= DATEADD(month, -24, GETDATE())
  AND ISNULL(Status, '') <> 'Canceled' AND ISNULL(TimeSlot, '') <> '00:00'
GROUP BY CONVERT(varchar(7), AppointmentDate, 120) ORDER BY YM;

-- C2 一格 4 人以上：哪位医生、哪个时段，其中多少格有 WITH（一起来的家人）（W22）
WITH s AS (
  SELECT CAST(AppointmentDate AS date) AS D, TimeSlot, DoctorID, COUNT(*) AS N,
         SUM(CASE WHEN UPPER(Remarks) LIKE '%WITH%' THEN 1 ELSE 0 END) AS WithN
  FROM Tbl_CAH_Appointment
  WHERE AppointmentDate >= DATEADD(month, -12, GETDATE())
    AND ISNULL(Status, '') NOT IN ('Canceled', 'Postpone') AND ISNULL(TimeSlot, '') <> '00:00'
  GROUP BY CAST(AppointmentDate AS date), TimeSlot, DoctorID)
SELECT DoctorID, TimeSlot, COUNT(*) AS Slots4plus,
       SUM(CASE WHEN WithN > 0 THEN 1 ELSE 0 END) AS SlotsWithWITH
FROM s WHERE N >= 4
GROUP BY DoctorID, TimeSlot ORDER BY Slots4plus DESC;

-- C3 相邻两格都是 3 人以上的次数 → 验证"相邻两格不能都排 3 人"（W2）
WITH s AS (
  SELECT CAST(AppointmentDate AS date) AS D, CAST(TimeSlot AS time) AS T, DoctorID, COUNT(*) AS N
  FROM Tbl_CAH_Appointment
  WHERE AppointmentDate >= DATEADD(month, -12, GETDATE())
    AND ISNULL(Status, '') NOT IN ('Canceled', 'Postpone') AND ISNULL(TimeSlot, '') <> '00:00'
    AND TimeSlot LIKE '[0-2][0-9]:[0-5][0-9]'
  GROUP BY CAST(AppointmentDate AS date), CAST(TimeSlot AS time), DoctorID),
t AS (
  SELECT *, LEAD(N) OVER (PARTITION BY DoctorID, D ORDER BY T) AS NextN,
            LEAD(T) OVER (PARTITION BY DoctorID, D ORDER BY T) AS NextT
  FROM s)
SELECT SUM(CASE WHEN N >= 3 THEN 1 ELSE 0 END) AS Slots3plus,
       SUM(CASE WHEN N >= 3 AND NextN >= 3 AND DATEDIFF(minute, T, NextT) = 30 THEN 1 ELSE 0 END) AS Adjacent3plus
FROM t;

-- C4 最近 12 个月各种时长写法的数量（W23）
SELECT
  SUM(CASE WHEN r LIKE '%1HOUR%' OR r LIKE '%1HR%' OR r LIKE '%(1H)%' THEN 1 ELSE 0 END) AS OneHourAny,
  SUM(CASE WHEN r LIKE '%1.5HOUR%' OR r LIKE '%1.30HOUR%' OR r LIKE '%1HOUR30%' OR r LIKE '%1HOURS30%' THEN 1 ELSE 0 END) AS OneAndHalf,
  SUM(CASE WHEN r LIKE '%2HOUR%' OR r LIKE '%2HR%' THEN 1 ELSE 0 END) AS TwoHours,
  SUM(CASE WHEN r LIKE '%[0-9]MIN%' THEN 1 ELSE 0 END) AS HasMinutes
FROM (SELECT UPPER(REPLACE(Remarks, ' ', '')) AS r
      FROM Tbl_CAH_Appointment
      WHERE AppointmentDate >= DATEADD(month, -12, GETDATE())
        AND ISNULL(Status, '') <> 'Canceled' AND ISNULL(TimeSlot, '') <> '00:00') x;

-- C5 OFF DAY 记录用的联系人 ID 和写法（W25）
SELECT TOP 20 ContactID, DoctorID, TimeSlot, Remarks, COUNT(*) AS N
FROM Tbl_CAH_Appointment
WHERE UPPER(Remarks) LIKE '%OFF%DAY%'
GROUP BY ContactID, DoctorID, TimeSlot, Remarks
ORDER BY N DESC;

-- C6 + 开头和其他开头的号码前缀（只取前 3 位数字，少于 3 次的不显示）
SELECT CASE WHEN HPNo LIKE '+%' THEN 'PLUS' ELSE 'OTHER' END AS T,
       LEFT(REPLACE(REPLACE(REPLACE(HPNo, '+', ''), '-', ''), ' ', ''), 3) AS P3, COUNT(*) AS N
FROM (SELECT DISTINCT ContactID, HPNo FROM Qry_CAH_Appointment) c
WHERE HPNo LIKE '+%'
   OR (ISNULL(LTRIM(HPNo), '') <> '' AND HPNo NOT LIKE '0%' AND HPNo NOT LIKE '60%')
GROUP BY CASE WHEN HPNo LIKE '+%' THEN 'PLUS' ELSE 'OTHER' END,
         LEFT(REPLACE(REPLACE(REPLACE(HPNo, '+', ''), '-', ''), ' ', ''), 3)
HAVING COUNT(*) >= 3
ORDER BY N DESC;
```

#### 统计查询 C 的结果（2026-10-02，已执行）

| # | 结果 | 结论 |
|---|---|---|
| C1 | CHER 2024-10 ～ 2025-10 每月 175–284 条，**2025-11 只有 103 条，2025-12 只有 2 条，之后没有** | CHER **约 2025 年 11 月离职**；现在只有 PHANG、GOH 两位医生，和诊所说的一致（W19 待诊所确认） |
| C2 | 4 人以上的格**全是 PHANG**，分布在 9:00–16:30 各个时段；127 格里只有 28 格有 `WITH` | PHANG 时常排到 4 人以上，**不只是家人一起来**（W22） |
| C3 | 3 人以上的格 768 个，其中 **192 个下一格也是 3 人以上**（25%） | "相邻两格不能都排 3 人"是理想规则，员工常常没有遵守（W22） |
| C4 | 最近 12 个月：写了 1 hour 的 **13 条**、1.5 hour 1 条、2 hours 2 条、带分钟数 57 条 | 长预约**很少**（一年十几条），影响不大，但规则仍要处理 |
| C5 | `OFF DAY` 记录用了 4 个不同的联系人（都不是诊所联系人 34094）；写法：`OFF DAY`、`OFF DAY !!!`、`OFFDAY`、`DR PHANG OFF DAY (MA)`、`**TAHUN BARU CINA OFFDAY (MA)**`（农历新年）、`***CHRISTMAS OFFDAY***(MA)`；时段在 `00:00`、`12:00`、`13:00`；另有一条正常的 `OR` 预约写着 `OFF SUNDAY` | 判断方式：Remarks **去掉空格后含 `OFFDAY`** → 该医生这天休息。这样 `OFF SUNDAY` 不会被误判。`(MA)`、`(Y)` 是**员工的缩写**，不是医生（医生是 `(P)` / `(G)`，以前还有 `(C)`） |
| C6 | `+659` 1,210、`+658` 882、无 `+` 的 `659` / `658` 378 → **新加坡手机号约 2,500 个**（约 12%）；`+601` 28；`016`、`012` 等开头的被算进"其他"，**前面有空格**；还有 `:01`（打错）、8 位数的 `9xx` / `8xx`（新加坡号码没写国家码）；少量 `+44`、`+61`、`+62` | 号码标准化规则见下 |

#### 手机号标准化规则（`get_customer_by_phone` 用）

WhatsApp 给的号码是国际格式、只有数字（例 `60123456789`、`6591234567`）。GPiS 的号码要先转成同样格式再比对：

1. 去掉前后空格，再去掉所有非数字字符（`+`、`-`、空格、`:`）
2. `0` 开头 → 去掉 `0`，前面加 `60`（马来西亚）
3. `60`、`65` 或其他国家码开头（原本有 `+`，或已经是 10–12 位）→ 保留
4. 8 位数、`8` 或 `9` 开头 → 当作新加坡号码，前面加 `65`
5. 其他 → 无法比对，当作新病人，由员工确认

执行：把上面的 SQL 存成 `gpis_stats_b.sql`，然后
`sqlcmd -S .\SQLEXPRESS -E -d GPiS_Dev -W -s "," -i gpis_stats_b.sql -o "$HOME\Desktop\gpis_stats_b.txt"`

结果贴回来之前先扫一眼，确认里面没有病人名字或号码（B7 如果 Remarks 里有名字，先遮掉）。
