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
| [`sql/README.md`](sql/README.md) | Phase 1：查空档的 SQL、测试记录 |
| [`backend/README.md`](backend/README.md) | Phase 2：FastAPI 空档 API；Phase 3：PostgreSQL（安装、建表、改表结构的步骤）；Phase 4a：员工登录、Admin API；Phase 5a：WhatsApp（Meta 测试 App、tunnel、测试清单）；对照步骤 |
| [`frontend/README.md`](frontend/README.md) | Phase 4b：Admin Platform 网页（React + TypeScript）：安装、启动、测试清单 |

开始新 session 时先读这四个文件。

## 必须遵守的规则

1. **绝不在主机（诊所生产环境）上做测试**。主机上只允许只读查询和 `BACKUP ... WITH COPY_ONLY`。
2. **所有开发和测试都在自己电脑上的 `GPiS_Dev` 测试数据库进行。**
3. 第一阶段对 GPiS **只读，不写入**。
4. **病人资料不能进入仓库、GitHub、AI 对话或云端。** 只处理表结构、设置表和统计数字；云端测试用假数据。截图也一样：先遮住病人名字、HP No、NRIC。
5. **不反编译 GPiS、不解密 `sa` 密码、不读取 `Tbl_User`。**
6. 仓库里不写入任何密码、连接字符串中的密码、access token（用环境变量 / `.env`，并加入 `.gitignore`）。

## 当前进度（2026-10-07）

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
- [x] 诊所回答 `docs/clinic-workflow.md` 的新问题 W19–W27
- [x] 诊所已回答 `docs/clinic-workflow.md` 第 7 节的全部问题（W1–W18）
- [x] Phase 1 SQL 初版：`sql/check_available_slots.sql`、`sql/find_test_dates.sql`
- [x] Phase 1 测试：全部通过（记录见 `sql/README.md`）
- [x] Phase 2 初版：`backend/`（FastAPI `GET /availability`，假数据单元测试 39 个通过）
- [x] Phase 2 对照：开发电脑连 `GPiS_Dev`，10 个测试日期和 Phase 1 SQL 结果一致（记录见 `backend/README.md`）
- [x] Phase 3 初版：`backend/app/db/`（PostgreSQL 12 张表 + Alembic migration；诊所设置搬进数据库；云端容器 PostgreSQL 16 上 104 个测试通过，全部假数据）
- [x] Phase 3 对照：开发电脑装 PostgreSQL 18，`pytest` 104 个通过、没有 skipped；10 个测试日期结果和 Phase 2 一样（记录见 `backend/README.md`）
- [x] Phase 4a 初版：员工登录（ADMIN / STAFF）+ Admin API（`backend/app/api/`，migration `0002`；云端容器 131 个测试通过，全部假数据）
- [x] Phase 4a 测试：开发电脑 `0002 (head)`，`pytest` 131 个通过、没有 skipped，`/docs` 登录试用 5 项正常（记录见 `backend/README.md`）
- [x] Phase 4a 合并进 `main`（PR #8）
- [x] Phase 4b 初版：`frontend/`（React + TypeScript + Vite，英文画面；Vite proxy 把 `/api` 转给 FastAPI；Vitest 31 个测试通过；云端容器用 Node 22.13 和浏览器点过测试清单，全部假数据）
- [x] 补上漏掉的疗程代码 `ISSUE CROWN`、`ISSUE BRIDGE`；牙冠、牙桥算多步骤疗程（类别 `CROWN`、`BRIDGE`，W28–W30、D33）
- [x] Phase 4b 测试：开发电脑（Node.js v22.13.0）照 `frontend/README.md` 的条件和测试清单全部通过（记录见 `frontend/README.md`）
- [x] Phase 4b 合并进 `main`（PR #9）
- [x] Phase 5a 初版：WhatsApp webhook（`backend/app/webhook_main.py`，port 8001）、员工回复、送达状态（migration `0003`）；开发只用 Meta 测试号码 + allowlist（D34–D38）；云端 `pytest` 161 个、Vitest 35 个通过，全部假数据
- [x] Phase 5a 设定检查：`python -m app.whatsapp_check`（问 Meta + 经 tunnel 打一次 webhook，找出手机消息没送来的原因；也查 token 能不能发消息）；`pytest` 181 个
- [ ] Phase 5a 测试：开发电脑建 Meta 测试 App，照 `backend/README.md`「Phase 5a」的清单测一次，再开 PR（第 1、2、4 项已通过；token 改用 System User 的，D39）
- [ ] 清理网盘中转文件（删除 + 清空回收站）

## 下一步

1. **Phase 5a 测试**：开发电脑在 Meta 建测试 App（自己的帐号，不用诊所的），装 cloudflared，照 `backend/README.md`「Phase 5a」的清单测（手机的消息没送来：先跑 `python -m app.whatsapp_check`）；通过后开 PR。
2. Phase 5b：模板消息 + 预约前一天的提醒（和第 3 点一起设计）；5c：上线时用 Coexistence 接上诊所的号码（A7 待决定：BSP 还是自己做 Embedded Signup）。
3. 设计主机 ↔ 本系统的数据读取方式（`docs/architecture.md` A1）：`GPiS_Dev` 只是 9 月 28 日的快照，正式上线必须读主机的实时数据。
4. 上线前：用 Admin Platform（*Settings → Clinic closures*）导入公共假期、补上农历新年多休的日子（`clinic_closures` 现在是空的）。
5. Phase 6（AI 推荐时段）之前要解决 A8：还没录入 GPiS 的预约请求要算进空档。

改空档规则时，`sql/check_available_slots.sql` 和 `backend/app/availability.py` 要一起改，再用上面的测试日期对照一次。
改表结构时：改 `backend/app/db/models.py` → 加 Alembic migration → `pytest`（步骤见 `backend/README.md`「改表结构的步骤」）。
改 API 的回传栏位时：`frontend/src/types.ts` 也要一起改，再 `npm run build`（TypeScript 会指出画面上用到旧栏位的地方）。
