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

- **营业时间**：GPiS 里没有，由诊所提供：9:00–17:00，最后预约 16:30，星期六、日营业，马来西亚公共假期休息；医生排班、午休见 [`clinic-workflow.md`](clinic-workflow.md) 第 1 节。

### 状态是否占用时段（按 staff 实际用法，待统计验证）

员工实际只用 `Confirmed`、`Closed`、`Canceled`（详见 [`clinic-workflow.md`](clinic-workflow.md) 第 5 节）。

| 状态 | 含义 | 占用时段？ |
|---|---|---|
| Confirmed | 预约确定 | ✅ |
| Closed | 病人已到店、已登记 | ✅（当天仍占用医生时间） |
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

业务流程方面的问题（W1–W12）在 [`clinic-workflow.md`](clinic-workflow.md) 第 7 节。

| # | 问题 | 目前所知（2026-09-30） | 验证方式 |
|---|---|---|---|
| Q1 | 各状态实际使用多少？哪些占用时段？ | staff：主要用 `Confirmed` / `Closed` / `Canceled` | 统计 A |
| Q2 | `Duration` 的格式？一个预约会占多个 30 分钟格吗？ | 会。staff 在 Remarks 写 `1 hour`，该病人独占这一格和下一格；`Duration` 字段可能没用 | 统计 A、B5 |
| Q3 | `AppointmentDate` 只有日期还是带时间？ | — | 统计 A |
| Q4 | 诊所实际营业时间？ | ✅ 9:00–17:00，最后预约 16:30；星期六、日营业，公共假期休息（诊所提供） | 统计 B1、B2 核对 |
| Q5 | 同一医生、同一时段是否允许多个预约？ | ✅ 允许，一般 2 人，视疗程可到 3 人；相邻两格不能都是 3 人 | 统计 B3 看分布 |
| Q6 | 数据是否仍在使用（最新预约日期）？ | ✅ 仍在使用（2026-09-30 有预约） | — |
| Q7 | `DOCTOR` 资源代表什么？ | — | 询问诊所 |
| Q8 | GPiS 如何产生新的 `AppointmentID`？ | 诊所说员工不会 `Delete`，改期是 `Edit` 原记录（`AppointmentID` 不变） | 在 `GPiS_Dev` 上观察，或用 SQL Profiler 看 GPiS 发出的 SQL；B9 若空洞很多，说明编号方式不是 MAX+1 或有其他删除来源 |
| Q9 | 手机号格式（有无 `+60`、空格、`-`）？能否可靠匹配 WhatsApp 号码？ | 格式混杂：纯数字、带空格、带 `-`，截图里没见到 `+60`；**有家人共用号码** | 统计 B10、B11 |

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

-- B2 各医生、星期几、时段的预约数 → 验证营业时间和午休
SELECT DoctorID, DATEPART(weekday, AppointmentDate) AS WD, TimeSlot, COUNT(*) AS N
FROM Tbl_CAH_Appointment
WHERE AppointmentDate >= DATEADD(month, -12, GETDATE())
  AND ISNULL(Status, '') <> 'Canceled'
GROUP BY DoctorID, DATEPART(weekday, AppointmentDate), TimeSlot
ORDER BY DoctorID, WD, TimeSlot;

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

-- B4 00:00 记录的状态分布 → 验证"提醒处理完改成 Closed"
SELECT Status, COUNT(*) AS N FROM Tbl_CAH_Appointment WHERE TimeSlot = '00:00' GROUP BY Status;

-- B5 Remarks 里表示时长的写法（只取关键字前后几个字，出现少于 3 次的不显示）
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
```

执行：把上面的 SQL 存成 `gpis_stats_b.sql`，然后
`sqlcmd -S .\SQLEXPRESS -E -d GPiS_Dev -W -s "," -i gpis_stats_b.sql -o "$HOME\Desktop\gpis_stats_b.txt"`

结果贴回来之前先扫一眼，确认里面没有病人名字或号码（B7 如果 Remarks 里有名字，先遮掉）。
