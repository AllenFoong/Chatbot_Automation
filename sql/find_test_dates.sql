/* =====================================================================
   找适合测试 check_available_slots.sql 的日期
   ---------------------------------------------------------------------
   在 GPiS_Dev 上执行。只输出日期和数量，不含病人资料。
   挑几种日子测试：有长预约（LongAppts > 0）、有 3 人格（MaxPerSlot = 3）、
   有 OFF DAY、有诊所联系人的记录（Placeholder = 1）、普通的日子。
   ===================================================================== */

SET NOCOUNT ON;
SET DATEFIRST 1;

DECLARE @From date = '2026-09-01';
DECLARE @To   date = '2026-10-31';
DECLARE @ClinicContactID int = 34094;

WITH a AS (
    SELECT CAST(AppointmentDate AS date) AS D,
           DoctorID,
           TimeSlot,
           ContactID,
           UPPER(REPLACE(REPLACE(ISNULL(Remarks, N''), N' ', N''), N'*', N'')) AS R
    FROM dbo.Tbl_CAH_Appointment
    WHERE AppointmentDate >= @From
      AND AppointmentDate <  DATEADD(day, 1, @To)
      AND DoctorID IN (N'PHANG', N'GOH')
      AND ISNULL(Status, N'') NOT IN (N'Canceled', N'Postpone')
),
s AS (
    SELECT D, DoctorID, TimeSlot, COUNT(*) AS N
    FROM a
    WHERE TimeSlot <> '00:00'
    GROUP BY D, DoctorID, TimeSlot
)
SELECT a.D                                AS [Date],
       DATENAME(weekday, a.D)             AS [Weekday],
       a.DoctorID,
       SUM(CASE WHEN a.TimeSlot <> '00:00' THEN 1 ELSE 0 END) AS Patients,
       (SELECT MAX(N) FROM s WHERE s.D = a.D AND s.DoctorID = a.DoctorID) AS MaxPerSlot,
       SUM(CASE WHEN a.R LIKE N'%1HOUR%' OR a.R LIKE N'%1HR%' OR a.R LIKE N'%(1H)%'
                  OR a.R LIKE N'%1.5HOUR%' OR a.R LIKE N'%2HOUR%' THEN 1 ELSE 0 END) AS LongAppts,
       MAX(CASE WHEN a.R LIKE N'%OFFDAY%' THEN 1 ELSE 0 END)                      AS OffDay,
       MAX(CASE WHEN a.ContactID = @ClinicContactID THEN 1 ELSE 0 END)            AS Placeholder
FROM a
GROUP BY a.D, a.DoctorID
ORDER BY a.D, a.DoctorID;
