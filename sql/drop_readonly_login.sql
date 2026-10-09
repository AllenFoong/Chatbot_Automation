-- 拿掉只读帐号 chatbot_reader（create_readonly_login.sql 的相反）。
-- 用法：sqlcmd -S .\SQLEXPRESS -E -i drop_readonly_login.sql -v DatabaseName="GPiS_Dev"
-- 先关掉本系统（uvicorn）：帐号还在连线时 DROP LOGIN 会失败。
-- 只删这个帐号，不动 GPiS 的资料。

:on error exit
SET NOCOUNT ON;

USE [$(DatabaseName)];
IF USER_ID(N'chatbot_reader') IS NOT NULL
    DROP USER [chatbot_reader];
GO

USE [master];
IF SUSER_ID(N'chatbot_reader') IS NOT NULL
    DROP LOGIN [chatbot_reader];
PRINT N'完成：chatbot_reader 已经拿掉。';
GO
