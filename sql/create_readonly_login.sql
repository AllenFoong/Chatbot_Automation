-- 只读帐号（D52）：本系统用 chatbot_reader 读 GPiS，不用 sa。
--
-- 在 GPiS 数据库所在的电脑上，用 sqlcmd + Windows 帐号执行（和 COPY_ONLY 备份一样）；步骤见 sql/README.md「只读帐号」。
-- 先在开发电脑的 GPiS_Dev 试过，诊所同意后才在主机 A 执行（D52）。
-- 密码不写在这个档案里：执行时用 -v ReaderPassword=... 传进来（只用英文字母和数字，至少 16 个字）。
--
-- 做的事：
--   1. 建 SQL 登入帐号 chatbot_reader（密码不会过期，不是任何角色的成员）
--   2. 在 $(DatabaseName) 建同名的数据库使用者
--   3. 只给两个 SELECT：dbo.Tbl_CAH_Appointment（预约）、dbo.Qry_CAH_Appointment（视图，手机号码）
--   4. 明确 DENY dbo.Tbl_User：以后就算有人给了更多权限，也读不到（CLAUDE.md 规则 5）
-- 不改 GPiS 的任何资料、不改 sa、不改 SQL Server 的设定、不用重开 SQL Server。
-- 要拿掉这个帐号：drop_readonly_login.sql。

:on error exit
SET NOCOUNT ON;

IF IS_SRVROLEMEMBER('sysadmin') = 0
    RAISERROR(N'要用有管理权限（sysadmin）的 Windows 帐号执行：sqlcmd -S .\SQLEXPRESS -E ...', 16, 1);
IF DB_ID(N'$(DatabaseName)') IS NULL
    RAISERROR(N'找不到数据库 $(DatabaseName)。', 16, 1);
IF LEN(N'$(ReaderPassword)') < 16 OR N'$(ReaderPassword)' LIKE N'%[^A-Za-z0-9]%'
    RAISERROR(N'密码要至少 16 个字，只用英文字母和数字。', 16, 1);
IF SUSER_ID(N'chatbot_reader') IS NOT NULL
    RAISERROR(N'帐号 chatbot_reader 已经存在。要重建，先执行 drop_readonly_login.sql。', 16, 1);
GO

USE [$(DatabaseName)];
IF OBJECT_ID(N'dbo.Tbl_CAH_Appointment', N'U') IS NULL OR OBJECT_ID(N'dbo.Qry_CAH_Appointment', N'V') IS NULL
    RAISERROR(N'$(DatabaseName) 里找不到 dbo.Tbl_CAH_Appointment 或 dbo.Qry_CAH_Appointment。', 16, 1);
GO

USE [master];
CREATE LOGIN [chatbot_reader]
    WITH PASSWORD = N'$(ReaderPassword)', DEFAULT_DATABASE = [$(DatabaseName)],
         CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
GO

USE [$(DatabaseName)];
CREATE USER [chatbot_reader] FOR LOGIN [chatbot_reader] WITH DEFAULT_SCHEMA = [dbo];
GRANT SELECT ON OBJECT::dbo.Tbl_CAH_Appointment TO [chatbot_reader];
GRANT SELECT ON OBJECT::dbo.Qry_CAH_Appointment TO [chatbot_reader];
IF OBJECT_ID(N'dbo.Tbl_User') IS NOT NULL
    EXEC (N'DENY SELECT ON OBJECT::dbo.Tbl_User TO [chatbot_reader];');
GO

-- 印出这个帐号的权限（只有权限，没有任何资料）。应该是：CONNECT、两个 SELECT（GRANT）、Tbl_User 的 SELECT（DENY）
SELECT pe.state_desc AS State, pe.permission_name AS Permission, ISNULL(OBJECT_NAME(pe.major_id), N'(database)') AS ObjectName
FROM sys.database_permissions pe
JOIN sys.database_principals pr ON pr.principal_id = pe.grantee_principal_id
WHERE pr.name = N'chatbot_reader'
ORDER BY pe.state_desc DESC, ObjectName;
PRINT N'完成：chatbot_reader 只能读 Tbl_CAH_Appointment、Qry_CAH_Appointment。下一步：python -m app.reminders_cli --check-gpis';
GO
