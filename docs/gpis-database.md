# GPiS 数据库

> 本文件**不包含任何病人资料、密码或诊所识别信息**。所有查询都只针对表结构、设置表或统计数字。
> 最后更新：2026-09-28

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

### 状态是否占用时段（推测，部分已由统计验证，见第 6 节）

| 状态 | 实际数量 | 占用时段？ |
|---|---|---|
| Closed | 80,158 | —（已完成的过去预约） |
| Confirmed | 17,514 | ✅ 正常预约的主要状态 |
| Canceled | 6,189 | ❌ |
| Rearrange | 458 | ⚠️ 待定 |
| Waiting | 114 | ✅（很少用） |
| Postpone | 103 | ❌ |
| Calling | 1 | ❓ **不在 `RefAppointmentStatus` 里**，说明状态字段没有外键约束 |

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

## 6. 统计查询结果（2026-09-30，在开发电脑的 `GPiS_Dev` 上）

开发电脑：SQL Server **17.0（2025）** Express，备份还原后改名为 `GPiS_Dev`。（新版本可还原旧备份，但**不能再备份回主机的 2012**。）

| 项目 | 结果 | 结论 |
|---|---|---|
| 日期范围 | 2017-11-18 ～ **2027-04-30** | 数据一直在用，已有约半年后的预约 |
| 总数 | **104,537** 条 | |
| `AppointmentDate` | 时间部分全是 `00:00:00` | **只存日期，时间只存在 `TimeSlot`** |
| `Duration` | `30`：104,449 条（99.9%）；另有 5、15、45、60、90、120 少量 | 单位是**分钟**（文字）；几乎所有预约都只占 1 格 |
| `DoctorID` | 14 个不同的值，其中一个医生约占 64%；另有 `admin` 3 条 | 多数是历史医生；当前有效医生以 `Qry_CAH_Resource_Sch` 为准 |

### `TimeSlot` 分布

| 时段 | 数量 | 解读 |
|---|---|---|
| `00:00` | 781 | ❗ 不是真实时间，见下方"00:00 现象" |
| 00:30–08:30 | 每格 1–8 | 录入错误，可忽略 |
| **09:00–12:00** | 每格 4.5k–7.3k | 上午营业 |
| **12:30** | 1,567 | 明显下降 → 可能是午休 |
| **13:00–17:00** | 每格 3k–8.3k | 下午营业（14:00 最多） |
| 17:30–20:30 | 每格 100–1.8k | 晚间，逐渐减少 → 可能某些日子有夜诊 |
| 21:00、22:30 | 各 1 | 录入错误 |

### "00:00 现象"

同一医生、同一时段出现多个预约的前 10 名，**全部是某月 1 号的 `00:00`、同一位医生**（最多 20 条）。
推测：`00:00` + 每月 1 号 = **"本月待联系 / 回访名单"**，不是真正的预约时间（`Calling` 状态可能也与此有关）。
→ 计算空档时**排除 `TimeSlot = '00:00'`**。

## 7. 待验证的问题

| # | 问题 | 状态 |
|---|---|---|
| Q1 | 各状态实际使用多少？哪些占用时段？ | ✅ 数量已知（见第 4 节）；`Rearrange` 是否占用仍待定 |
| Q2 | `Duration` 的格式？ | ✅ 分钟数（文字），99.9% 是 30 |
| Q3 | `AppointmentDate` 只有日期还是带时间？ | ✅ 只有日期 |
| Q4 | 诊所实际营业时间？ | 🔶 推测 09:00–12:30、13:00–17:30，部分日子到 20:30；需按星期统计 + 询问诊所 |
| Q5 | 同一医生、同一时段是否允许多个预约？ | 🔶 前 10 名都是 `00:00`；需**排除 00:00** 后重查 |
| Q6 | 数据是否仍在使用？ | ✅ 是，已有到 2027-04 的预约 |
| Q7 | `DOCTOR` 资源代表什么？ | 询问诊所 |
| Q8 | GPiS 如何产生新的 `AppointmentID`？ | 在 `GPiS_Dev` 上观察，或用 SQL Profiler |
| Q9 | 手机号格式能否可靠匹配 WhatsApp 号码？ | 只统计格式，不看具体号码 |
| Q10 | `00:00` 预约是否真的是"回访名单"？ | 统计日期是否都是每月 1 号、状态分布 + 询问诊所 |
| Q11 | 哪天休息？各星期几的营业时段？ | 按星期统计 |
| Q12 | 最近一年实际在看诊的医生有哪些？ | 统计最近 12 个月的 `DoctorID` |

### 第一轮统计查询（已执行，结果见第 6 节）

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

### 第二轮统计查询（待执行，回答 Q4、Q5、Q10–Q12）

备份日期约为 2026-09-28，下面以此为"今天"。只含统计，不含病人资料。

```sql
SET NOCOUNT ON;
SET DATEFIRST 1;  -- 1 = 星期一 ... 7 = 星期日

-- A. 排除 00:00 后，同一医生同一时段的重复预约（Q5）
SELECT COUNT(*) AS DupGroups FROM (
  SELECT AppointmentDate, TimeSlot, DoctorID FROM Tbl_CAH_Appointment
  WHERE TimeSlot <> '00:00' AND Status IN ('Confirmed','Waiting','Closed')
  GROUP BY AppointmentDate, TimeSlot, DoctorID HAVING COUNT(*) > 1) x;
SELECT TOP 10 CONVERT(varchar(10), AppointmentDate, 120) AS D, TimeSlot, DoctorID, COUNT(*) AS SameSlot
  FROM Tbl_CAH_Appointment
  WHERE TimeSlot <> '00:00' AND Status IN ('Confirmed','Waiting','Closed')
  GROUP BY AppointmentDate, TimeSlot, DoctorID HAVING COUNT(*) > 1
  ORDER BY SameSlot DESC, D DESC;

-- B. 00:00 预约是几号、什么状态（Q10）
SELECT DAY(AppointmentDate) AS DayOfMonth, COUNT(*) AS N FROM Tbl_CAH_Appointment
  WHERE TimeSlot = '00:00' GROUP BY DAY(AppointmentDate) ORDER BY N DESC;
SELECT Status, COUNT(*) AS N FROM Tbl_CAH_Appointment
  WHERE TimeSlot = '00:00' GROUP BY Status;

-- C. 最近 12 个月：时段 × 星期几（Q4、Q11）
SELECT TimeSlot,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 1 THEN 1 ELSE 0 END) AS Mon,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 2 THEN 1 ELSE 0 END) AS Tue,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 3 THEN 1 ELSE 0 END) AS Wed,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 4 THEN 1 ELSE 0 END) AS Thu,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 5 THEN 1 ELSE 0 END) AS Fri,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 6 THEN 1 ELSE 0 END) AS Sat,
  SUM(CASE WHEN DATEPART(weekday, AppointmentDate) = 7 THEN 1 ELSE 0 END) AS Sun
FROM Tbl_CAH_Appointment
WHERE TimeSlot <> '00:00' AND Status <> 'Canceled'
  AND AppointmentDate >= '2025-09-28' AND AppointmentDate < '2026-09-28'
GROUP BY TimeSlot ORDER BY TimeSlot;

-- D. 最近 12 个月实际看诊的医生（Q12）
SELECT DoctorID, COUNT(*) AS N,
  CONVERT(varchar(10), MIN(AppointmentDate), 120) AS FirstDate,
  CONVERT(varchar(10), MAX(AppointmentDate), 120) AS LastDate
FROM Tbl_CAH_Appointment
WHERE AppointmentDate >= '2025-09-28'
GROUP BY DoctorID ORDER BY N DESC;

-- E. 未来预约（2026-09-28 之后）的状态分布（Q1：哪些状态代表"已订"）
SELECT Status, COUNT(*) AS N FROM Tbl_CAH_Appointment
  WHERE AppointmentDate >= '2026-09-28' GROUP BY Status;
```
