/* =====================================================================
   Phase 1：查某天某医生的空档
   ---------------------------------------------------------------------
   在 GPiS_Dev 上执行（SSMS → 选 GPiS_Dev → Ctrl+T 文字结果 → F5）。
   只读 Tbl_CAH_Appointment，不写入任何数据。
   输出不含病人名字、电话、Remarks 原文，可以直接贴给别人对照。

   规则来源：docs/architecture.md「空档计算规则」、docs/clinic-workflow.md 第 1、2 节
   ===================================================================== */

SET NOCOUNT ON;
SET DATEFIRST 1;  -- 1 = 星期一 … 7 = 星期日

/* ---------- 1. 输入：每次查询改这三个 ---------- */
DECLARE @Date     date         = '2026-10-09';
DECLARE @DoctorID nvarchar(20) = N'PHANG';     -- PHANG / GOH
DECLARE @Service  nvarchar(20) = N'S+P';       -- 要预约的疗程代码；决定能不能用第 3 个名额

/* ---------- 2. 设置：将来放在本系统 PostgreSQL（doctor_schedules、services、clinic_closures） ---------- */
DECLARE @MaxPerSlot      int = 3;      -- 每格最多几人（W22）
DECLARE @MaxPerSlotForAI int = 3;      -- 改成 2 = AI 不用第 3 个名额
DECLARE @ClinicContactID int = 34094;  -- 诊所自己当联系人（统计 B6）

-- 医生排班（W13、W20、W21）：BreakStart … BreakEnd 之间的格不能约
DECLARE @Schedule TABLE (
    DoctorID   nvarchar(20),
    WD         tinyint,
    IsWorking  bit,
    StartTime  time(0),
    LastSlot   time(0),
    BreakStart time(0),
    BreakEnd   time(0)
);
INSERT INTO @Schedule VALUES
    (N'PHANG', 1, 1, '09:00', '16:30', '12:00', '13:00'),
    (N'PHANG', 2, 0, NULL,    NULL,    NULL,    NULL),     -- 星期二休息
    (N'PHANG', 3, 1, '09:00', '16:30', '12:00', '13:00'),
    (N'PHANG', 4, 1, '09:00', '16:30', '12:00', '13:00'),
    (N'PHANG', 5, 1, '09:00', '16:30', '12:00', '13:00'),
    (N'PHANG', 6, 1, '09:00', '16:30', '12:00', '13:00'),
    (N'PHANG', 7, 1, '09:00', '16:30', '12:00', '13:00'),
    (N'GOH',   1, 1, '09:00', '15:30', '13:00', '14:00'),
    (N'GOH',   2, 1, '09:00', '15:30', '12:00', '13:00'),  -- 星期二午休 12:00
    (N'GOH',   3, 0, NULL,    NULL,    NULL,    NULL),     -- 星期三休息
    (N'GOH',   4, 0, NULL,    NULL,    NULL,    NULL),     -- 星期四休息
    (N'GOH',   5, 1, '09:00', '15:30', '13:00', '14:00'),
    (N'GOH',   6, 1, '09:00', '15:30', '13:00', '14:00'),
    (N'GOH',   7, 1, '09:00', '15:30', '13:00', '14:00');

-- 能当一格第 3 人的疗程（W15）
DECLARE @CanBeThird TABLE (Code nvarchar(20) PRIMARY KEY);
INSERT INTO @CanBeThird VALUES (N'OR'), (N'S+P'), (N'F'), (N'RETAINER');

-- 诊所休息日：全国 + Johor 公共假期、农历新年多休的日子（W1、W14）
DECLARE @Closures TABLE (D date PRIMARY KEY, Reason nvarchar(100));
-- INSERT INTO @Closures VALUES ('2026-12-25', N'Christmas');

-- 本系统记录的医生请假（备用；GPiS 里的 OFF DAY 也会检查，W25）
DECLARE @DoctorLeaves TABLE (DoctorID nvarchar(20), D date);
-- INSERT INTO @DoctorLeaves VALUES (N'GOH', '2026-10-10');


/* ---------- 3. 这位医生这天的排班 ---------- */
DECLARE @WD tinyint = DATEPART(weekday, @Date);
DECLARE @IsWorking bit, @StartTime time(0), @LastSlot time(0), @BreakStart time(0), @BreakEnd time(0);

SELECT @IsWorking  = IsWorking,
       @StartTime  = StartTime,
       @LastSlot   = LastSlot,
       @BreakStart = BreakStart,
       @BreakEnd   = BreakEnd
FROM @Schedule
WHERE DoctorID = @DoctorID AND WD = @WD;


/* ---------- 4. 读 GPiS 这天的预约（排除 Canceled、Postpone） ---------- */
DECLARE @Appt TABLE (
    AppointmentID int,
    RawSlot       nvarchar(10),
    Slot          time(0) NULL,   -- 00:00（提醒）和格式不对的时段 = NULL，不占时段
    Status        nvarchar(20),
    R             nvarchar(600),  -- Remarks 转大写、去掉空格和 *，只在这里用来判断，不输出
    IsPlaceholder bit,
    IsOffDay      bit,
    DurSlots      tinyint,
    HourUnparsed  bit
);

INSERT INTO @Appt (AppointmentID, RawSlot, Slot, Status, R, IsPlaceholder)
SELECT a.AppointmentID,
       a.TimeSlot,
       CASE WHEN a.TimeSlot LIKE '[0-2][0-9]:[0-5][0-9]' AND a.TimeSlot <> '00:00'
            THEN TRY_CAST(a.TimeSlot AS time(0)) END,
       a.Status,
       UPPER(REPLACE(REPLACE(REPLACE(ISNULL(a.Remarks, N''), N' ', N''), NCHAR(9), N''), N'*', N'')),
       CASE WHEN a.ContactID = @ClinicContactID THEN 1 ELSE 0 END
FROM dbo.Tbl_CAH_Appointment a
WHERE a.AppointmentDate >= @Date
  AND a.AppointmentDate <  DATEADD(day, 1, @Date)
  AND a.DoctorID = @DoctorID
  AND ISNULL(a.Status, N'') NOT IN (N'Canceled', N'Postpone');

-- OFF DAY：任何联系人、任何时段（包括 00:00），去掉空格后含 OFFDAY（C5；OFF SUNDAY 不算）
UPDATE @Appt SET IsOffDay = CASE WHEN R LIKE N'%OFFDAY%' THEN 1 ELSE 0 END;

-- 时长只看 Remarks（W17、W23、W24）：先判断长的，再判断短的；xxMIN 一律当 1 格
UPDATE @Appt SET DurSlots =
    CASE
        WHEN R LIKE N'%2HOUR%' OR R LIKE N'%2HR%' THEN 4
        WHEN R LIKE N'%1.5HOUR%' OR R LIKE N'%1.5HR%' OR R LIKE N'%1.5H)%'
          OR R LIKE N'%1.30HOUR%' OR R LIKE N'%1HOUR30%' OR R LIKE N'%1HOURS30%' OR R LIKE N'%1HR30%' THEN 3
        WHEN R LIKE N'%1HOUR%' OR R LIKE N'%1HR%' OR R LIKE N'%(1H)%' THEN 2
        ELSE 1
    END;

-- 有 HOUR / HR 字样但看不懂 → 当天转人工
UPDATE @Appt SET HourUnparsed =
    CASE WHEN DurSlots = 1 AND (R LIKE N'%HOUR%' OR R LIKE N'%[0-9]HR%') THEN 1 ELSE 0 END;


/* ---------- 5. 这天的状态 ---------- */
DECLARE @DayStatus nvarchar(30), @DayNote nvarchar(200);

IF NOT EXISTS (SELECT 1 FROM @Schedule WHERE DoctorID = @DoctorID)
    SELECT @DayStatus = N'UNKNOWN_DOCTOR', @DayNote = N'排班表里没有这位医生';
ELSE IF EXISTS (SELECT 1 FROM @Closures WHERE D = @Date)
    SELECT @DayStatus = N'CLINIC_CLOSED', @DayNote = (SELECT Reason FROM @Closures WHERE D = @Date);
ELSE IF ISNULL(@IsWorking, 0) = 0
    SELECT @DayStatus = N'DOCTOR_NOT_WORKING', @DayNote = N'这位医生这天固定休息';
ELSE IF EXISTS (SELECT 1 FROM @DoctorLeaves WHERE DoctorID = @DoctorID AND D = @Date)
    SELECT @DayStatus = N'DOCTOR_ON_LEAVE', @DayNote = N'本系统记录了请假';
ELSE IF EXISTS (SELECT 1 FROM @Appt WHERE IsOffDay = 1)
    SELECT @DayStatus = N'OFFDAY_IN_GPIS', @DayNote = N'GPiS 有 OFF DAY 记录';
ELSE IF EXISTS (SELECT 1 FROM @Appt WHERE IsPlaceholder = 1)
    SELECT @DayStatus = N'NEEDS_REVIEW', @DayNote = N'有诊所联系人的记录（可能是医生的私人安排），AI 不自动推荐';
ELSE IF EXISTS (SELECT 1 FROM @Appt WHERE HourUnparsed = 1 AND Slot IS NOT NULL)
    SELECT @DayStatus = N'NEEDS_REVIEW', @DayNote = N'有看不懂的时长写法，AI 不自动推荐';
ELSE
    SELECT @DayStatus = N'OK', @DayNote = NULL;


/* ---------- 6. 时段表：营业时段 + 最后一格之后的一格（给 1 hour 从最后一格开始用） ---------- */
DECLARE @Grid TABLE (Slot time(0) PRIMARY KEY, IsBreak bit, IsAfterHours bit);

IF @IsWorking = 1
    INSERT INTO @Grid (Slot, IsBreak, IsAfterHours)
    SELECT t.Slot,
           CASE WHEN t.Slot >= @BreakStart AND t.Slot < @BreakEnd THEN 1 ELSE 0 END,
           CASE WHEN t.Slot > @LastSlot THEN 1 ELSE 0 END
    FROM (
        SELECT DATEADD(minute, 30 * v.n, @StartTime) AS Slot
        FROM (VALUES (0),(1),(2),(3),(4),(5),(6),(7),(8),(9),(10),
                     (11),(12),(13),(14),(15),(16),(17),(18),(19),(20)) v(n)
    ) t
    WHERE t.Slot <= DATEADD(minute, 30, @LastSlot);

-- 每格已约人数（不算占位、OFF DAY），以及有没有被长预约整格封锁
DECLARE @S TABLE (Slot time(0) PRIMARY KEY, IsBreak bit, IsAfterHours bit, Booked int, LongBlocked bit);

INSERT INTO @S (Slot, IsBreak, IsAfterHours, Booked, LongBlocked)
SELECT g.Slot, g.IsBreak, g.IsAfterHours,
       (SELECT COUNT(*) FROM @Appt a
         WHERE a.Slot = g.Slot AND a.IsPlaceholder = 0 AND a.IsOffDay = 0),
       CASE WHEN EXISTS (
            SELECT 1 FROM @Appt a
            WHERE a.IsPlaceholder = 0 AND a.IsOffDay = 0 AND a.DurSlots >= 2
              AND g.Slot >= a.Slot
              AND g.Slot <  DATEADD(minute, 30 * a.DurSlots, a.Slot)
       ) THEN 1 ELSE 0 END
FROM @Grid g;


/* ---------- 7. 输出 ---------- */

-- 7a. 这天的总结
SELECT @Date                                   AS [Date],
       DATENAME(weekday, @Date)                AS [Weekday],
       @DoctorID                               AS Doctor,
       @Service                                AS Service,
       @DayStatus                              AS DayStatus,
       @DayNote                                AS Note,
       (SELECT COUNT(*) FROM @Appt
         WHERE Slot IS NOT NULL AND IsPlaceholder = 0 AND IsOffDay = 0) AS Patients;

-- 7b. 每个时段
;WITH x AS (
    SELECT s.*,
           LAG(s.Booked, 1, 0)       OVER (ORDER BY s.Slot) AS PrevBooked,
           LEAD(s.Booked, 1, 0)      OVER (ORDER BY s.Slot) AS NextBooked,
           LEAD(s.LongBlocked, 1, 0) OVER (ORDER BY s.Slot) AS NextBlocked,
           LEAD(s.IsBreak, 1, 1)     OVER (ORDER BY s.Slot) AS NextIsBreak
    FROM @S s
),
c AS (
    SELECT x.*,
           -- 上限：能当第 3 人的疗程，且前后两格都不是 3 人 → 3；否则 2（W2、W15、W22）
           CASE WHEN @Service IN (SELECT Code FROM @CanBeThird)
                 AND x.PrevBooked < 3 AND x.NextBooked < 3
                THEN 3 ELSE 2 END AS CapRule
    FROM x
),
d AS (
    SELECT c.*,
           (SELECT MIN(v) FROM (VALUES (c.CapRule), (@MaxPerSlot), (@MaxPerSlotForAI)) m(v)) AS Cap
    FROM c
)
SELECT CONVERT(char(5), d.Slot, 108) AS Slot,
       CASE WHEN d.IsAfterHours = 1 THEN N'AFTER HOURS'
            WHEN d.IsBreak = 1      THEN N'BREAK'
            WHEN d.LongBlocked = 1  THEN N'LONG APPT'
            ELSE N'' END              AS Kind,
       d.Booked,
       CASE WHEN d.IsBreak = 1 OR d.IsAfterHours = 1 OR d.LongBlocked = 1 THEN NULL ELSE d.Cap END AS Cap,
       CASE WHEN @DayStatus NOT IN (N'OK', N'NEEDS_REVIEW')
              OR d.IsBreak = 1 OR d.IsAfterHours = 1 OR d.LongBlocked = 1 THEN 0
            WHEN d.Cap > d.Booked THEN d.Cap - d.Booked ELSE 0 END          AS Remaining,
       -- 30 分钟预约能不能约
       CASE WHEN @DayStatus IN (N'OK', N'NEEDS_REVIEW')
             AND d.IsBreak = 0 AND d.IsAfterHours = 0 AND d.LongBlocked = 0
             AND d.Booked < d.Cap
            THEN 1 ELSE 0 END                                                AS Can30,
       -- 1 hour 预约能不能从这格开始：这格和下一格都空、都没封锁、下一格不是午休
       -- （最后一格的下一格是 AFTER HOURS，可以用，W16、W27）
       CASE WHEN @DayStatus IN (N'OK', N'NEEDS_REVIEW')
             AND d.IsBreak = 0 AND d.IsAfterHours = 0 AND d.LongBlocked = 0
             AND d.Booked = 0 AND d.NextBooked = 0 AND d.NextBlocked = 0 AND d.NextIsBreak = 0
            THEN 1 ELSE 0 END                                                AS Can60
FROM d
ORDER BY d.Slot;

-- 7c. 这天每条预约怎么被解读（只有 ID 和判断结果，没有名字和 Remarks）
SELECT AppointmentID,
       RawSlot       AS TimeSlot,
       Status,
       DurSlots,
       IsPlaceholder,
       IsOffDay,
       HourUnparsed,
       CASE WHEN Slot IS NULL THEN N'不占时段（00:00 或格式不对）' ELSE N'' END AS Note
FROM @Appt
ORDER BY RawSlot, AppointmentID;
