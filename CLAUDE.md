# Chatbot_Automation

牙医诊所的 **WhatsApp 预约系统**：病人用 WhatsApp 预约（不需要 App），AI Agent 代替客服自动回复，员工可以随时通过 Admin Platform 查看对话、接手、确认预约。

诊所现有的管理系统是 **GPiS**（.NET 桌面程序 + SQL Server Express），运行在诊所的一台 Windows 电脑上（称为"**主机**"）。本系统独立于 GPiS 之外，第一阶段**只读取** GPiS 的预约数据来判断空档。

## 文档索引

| 文件 | 内容 |
|---|---|
| [`docs/gpis-database.md`](docs/gpis-database.md) | GPiS 数据库：表、字段、跑过的 SQL、结果、待验证的问题 |
| [`docs/architecture.md`](docs/architecture.md) | 系统架构、技术选型、开发路线、人工介入设计；第 8 节：Phase 5b 预约提醒的设计（草稿）；第 9 节：A1 怎么读主机的方案比较；第 10 节：5c 接上诊所号码、第三方平台、费用和 Plan B（草稿） |
| [`docs/decisions.md`](docs/decisions.md) | 做过的决定和原因、数据安全规则 |
| [`docs/clinic-workflow.md`](docs/clinic-workflow.md) | 营业时间、医生排班、staff 如何使用 GPiS 预约、Remarks 治疗代码、待确认问题 |
| [`sql/README.md`](sql/README.md) | Phase 1：查空档的 SQL、测试记录 |
| [`backend/README.md`](backend/README.md) | Phase 2：FastAPI 空档 API；Phase 3：PostgreSQL（安装、建表、改表结构的步骤）；Phase 4a：员工登录、Admin API；Phase 5a：WhatsApp（Meta 测试 App、tunnel、测试清单）；Phase 5b：预约提醒（名单、Open in WhatsApp、测试清单）；对照步骤 |
| [`frontend/README.md`](frontend/README.md) | Phase 4b：Admin Platform 网页（React + TypeScript）：安装、启动、测试清单 |

开始新 session 时先读这四个文件。

## 必须遵守的规则

1. **绝不在主机（诊所生产环境）上做测试**。主机上只允许只读查询和 `BACKUP ... WITH COPY_ONLY`。（例外：诊所同意建一个只读的 SQL 帐号，做法见 `docs/decisions.md` D52）
2. **所有开发和测试都在自己电脑上的 `GPiS_Dev` 测试数据库进行。**
3. 第一阶段对 GPiS **只读，不写入**。
4. **病人资料不能进入仓库、GitHub、AI 对话或云端。** 只处理表结构、设置表和统计数字；云端测试用假数据。截图也一样：先遮住病人名字、HP No、NRIC。
5. **不反编译 GPiS、不解密 `sa` 密码、不读取 `Tbl_User`。**
6. 仓库里不写入任何密码、连接字符串中的密码、access token（用环境变量 / `.env`，并加入 `.gitignore`）。

## 当前进度（2026-10-08）

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
- [x] Phase 5a 设定检查：`python -m app.whatsapp_check`（问 Meta + 经 tunnel 打一次 webhook，找出手机消息没送来的原因；也查 token 能不能发消息）；`pytest` 183 个
- [x] Phase 5a 测试：开发电脑（Meta 测试 App 在自己的测试 portfolio，token 用 System User 的，D39）：`0003 (head)`，`pytest` 183 个、`npm test` 35 个通过，`npm run build` 成功，测试清单 1–7 项全部通过（记录见 `backend/README.md`）
- [x] Phase 5a 合并进 `main`（PR #10）
- [x] Phase 5b 设计草稿（只有文档，没有程序）：预约前一天用 WhatsApp 模板消息提醒病人（`docs/architecture.md` 第 8 节、D40–D47）；要问诊所 W31–W45（给诊所的中英对照问卷在 claude.ai 上，不在仓库）
- [x] 诊所回答第一轮问卷（2026-10-08）：W31–W39、W41–W45 已回答，设计照着改（D48 第一版没有按钮、D49 家人合成 `NAME: A & B`、D50 戴牙的预约要有 `*C` 才发）
- [x] A1 方案比较草稿（`docs/architecture.md` 第 9 节）：建议先在诊所放一台专用小电脑跑本系统，经局域网只读读主机
- [x] 第二轮问卷整理好（中英对照，在 claude.ai 上）：W40a–d（病人同意，附登记表例句）、W46–W47（提醒）、W48–W53（A1）；已知柜台 2 台电脑，主机 A 24 小时开着
- [x] 诊所回答第二轮问卷（2026-10-08）：诊所不能放新电脑 → 5b 先装在柜台另一台电脑（D53）；同意在主机 A 开只读帐号（D52）；`VENEER` 也要 `*C`（D51）；旧病人的同意是「告知」不是「问同意」，要请律师看（`architecture.md` 8.8）
- [ ] 等诊所：W40b（空白登记表的照片）、W54（柜台另一台可不可以一直装着、不关机）
- [x] Phase 5b 第一步程序：Reminders 页面（只看名单）+ Open in WhatsApp（`backend/app/reminders.py`、`api/reminders.py`、`reminders_cli.py`，`frontend/src/pages/RemindersPage.tsx`）；没有改数据库；云端 `pytest` 255 个、Vitest 41 个通过，headless Chromium 用假资料点过，全部假数据
- [ ] Phase 5b 第一步：开发电脑测试（`--check-gpis`、4 个测试日期，`backend/README.md`「Phase 5b」）
- [x] Phase 5b 设计 + A1 合并进 `main`（PR #11）
- [x] 5c 的 Plan B、第三方平台、Meta 的费用（2026-10-01 起 24 小时内的消息也收费）整理进 `docs/architecture.md` 第 10 节；5b 加「Open in WhatsApp」按钮，不用等 5c（D54）
- [ ] 清理网盘中转文件（删除 + 清空回收站）

## 下一步

1. 下次去诊所：看柜台另一台电脑的 Windows 版本、内存、硬盘，和 `GPiS.exe.config` 的 `Database.Server` 那一行（W51，不看密码那一行）；收 W40b 的空白登记表照片（确认上面没有病人资料）。
2. 5b：先在开发电脑照 `backend/README.md`「Phase 5b」测试（`--check-gpis` 不是 `[OK]` 就贴回来改 SQL）。之后：`reminders` 表（记录按过 Open in WhatsApp、opt-out），再装到柜台另一台电脑试跑（D52 只读帐号、D53）。第一版模板没有按钮（D48）；真的发只用假的预约来源 + Meta 测试号码 + 允许名单（D44）。每次测 WhatsApp：cloudflared 重开后要改 Meta 的 *Callback URL*；System User 的 token 60 天失效（D39）；有问题先跑 `python -m app.whatsapp_check`。
3. 员工按「Open in WhatsApp」发，只要 A1 做好（第 4 点）。系统用模板自动发，要等三件事：5c（Coexistence 接上诊所的号码，A7 待决定：BSP 还是自己做 Embedded Signup）、A1（读主机的实时预约）、病人同意（W40、D46）。
4. A1：5b 先把本系统装在柜台另一台电脑（D53），主机 A 的只读帐号照 D52 做（脚本先在开发电脑试）。Phase 6 之前决定长期放哪里（W54、`docs/architecture.md` 9.4）。
5. 上线前：用 Admin Platform（*Settings → Clinic closures*）导入公共假期、补上农历新年多休的日子（`clinic_closures` 现在是空的；提醒也要靠它决定假期前提早发）。
6. Phase 6（AI 推荐时段）之前要解决 A8：还没录入 GPiS 的预约请求要算进空档。

改空档规则时，`sql/check_available_slots.sql` 和 `backend/app/availability.py` 要一起改，再用上面的测试日期对照一次；提醒名单沿用同一套判断（D41），也要再看一次。
改表结构时：改 `backend/app/db/models.py` → 加 Alembic migration → `pytest`（步骤见 `backend/README.md`「改表结构的步骤」）。
改 API 的回传栏位时：`frontend/src/types.ts` 也要一起改，再 `npm run build`（TypeScript 会指出画面上用到旧栏位的地方）。
