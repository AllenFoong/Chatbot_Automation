# Chatbot_Automation

牙医诊所的 **WhatsApp 预约系统**：病人用 WhatsApp 预约（不需要 App），AI Agent 代替客服自动回复，员工可以随时通过 Admin Platform 查看对话、接手、确认预约。

诊所现有的管理系统是 **GPiS**（.NET 桌面程序 + SQL Server Express），运行在诊所的一台 Windows 电脑上（称为"**主机**"）。本系统独立于 GPiS 之外，第一阶段**只读取** GPiS 的预约数据来判断空档。

## 文档索引

| 文件 | 内容 |
|---|---|
| [`docs/gpis-database.md`](docs/gpis-database.md) | GPiS 数据库：表、字段、跑过的 SQL、结果、待验证的问题 |
| [`docs/architecture.md`](docs/architecture.md) | 系统架构、技术选型、开发路线、人工介入设计 |
| [`docs/decisions.md`](docs/decisions.md) | 做过的决定和原因、数据安全规则 |
| [`docs/clinic-workflow.md`](docs/clinic-workflow.md) | 营业时间、医生排班、staff 如何使用 GPiS 预约、Remarks 治疗代码、待确认问题 |

开始新 session 时先读这四个文件。

## 必须遵守的规则

1. **绝不在主机（诊所生产环境）上做测试**。主机上只允许只读查询和 `BACKUP ... WITH COPY_ONLY`。
2. **所有开发和测试都在自己电脑上的 `GPiS_Dev` 测试数据库进行。**
3. 第一阶段对 GPiS **只读，不写入**。
4. **病人资料不能进入仓库、GitHub、AI 对话或云端。** 只处理表结构、设置表和统计数字；云端测试用假数据。截图也一样：先遮住病人名字、HP No、NRIC。
5. **不反编译 GPiS、不解密 `sa` 密码、不读取 `Tbl_User`。**
6. 仓库里不写入任何密码、连接字符串中的密码、access token（用环境变量 / `.env`，并加入 `.gitignore`）。

## 当前进度（2026-10-02）

- [x] 确认 GPiS 使用 SQL Server 2012 Express，数据库名 `GPiS`
- [x] 导出表结构，找到预约表 `Tbl_CAH_Appointment` 及相关设置表
- [x] 在主机上 `COPY_ONLY` 备份成功
- [x] 备份经 7-Zip 加密后传到开发电脑：`D:\GPiS\GPiS_copy.bak`
- [x] 整理 staff 使用 GPiS 预约的方式和业务规则（`docs/clinic-workflow.md`）
- [x] 开发电脑安装 SQL Server 2025 Express + SSMS
- [x] 还原并改名为 `GPiS_Dev`
- [x] 统计查询 A（结果见 `docs/gpis-database.md` 第 6 节）
- [x] 统计查询 B（B1–B13，结果见 `docs/gpis-database.md`）
- [x] 统计查询 C（C1–C6，结果见 `docs/gpis-database.md`）
- [ ] 诊所回答 `docs/clinic-workflow.md` 的新问题（W21、W22 已回答；W19、W20、W23–W27 待确认）
- [x] 诊所已回答 `docs/clinic-workflow.md` 第 7 节的全部问题（W1–W18）
- [ ] 清理网盘中转文件（删除 + 清空回收站）

## 下一步

1. 向诊所确认 `docs/clinic-workflow.md` 剩下的问题，**W20（午休前半格能不能约）最影响空档计算**。
2. 同时开始 Phase 1：按 `docs/architecture.md` 的"空档计算规则"，写出"查某天某医生空档"的 SQL。已确定：午休只封锁后半格（PHANG 12:30、GOH 13:30 / 星期二 12:30）、GOH 最后时段 15:30、每格上限 3。
