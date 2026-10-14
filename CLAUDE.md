# Chatbot_Automation

牙医诊所的 **WhatsApp 预约系统**：病人用 WhatsApp 预约（不需要 App），AI Agent 代替客服自动回复，员工可以随时通过 Admin Platform 查看对话、接手、确认预约。

诊所现有的管理系统是 **GPiS**（.NET 桌面程序 + SQL Server Express），运行在诊所的一台 Windows 电脑上（称为"**主机**"）。本系统独立于 GPiS 之外，第一阶段**只读取** GPiS 的预约数据来判断空档。

## 文档索引

| 文件 | 内容 |
|---|---|
| [`docs/gpis-database.md`](docs/gpis-database.md) | GPiS 数据库：表、字段、跑过的 SQL、结果、待验证的问题 |
| [`docs/architecture.md`](docs/architecture.md) | 系统架构、技术选型、开发路线、人工介入设计；第 8 节：Phase 5b 预约提醒的设计（草稿）；第 9 节：A1 怎么读主机的方案比较；第 10 节：5c 接上诊所号码、第三方平台、费用和 Plan B（草稿）；第 11 节：Phase 6 AI Agent 的设计（草稿） |
| [`docs/decisions.md`](docs/decisions.md) | 做过的决定和原因、数据安全规则 |
| [`docs/clinic-workflow.md`](docs/clinic-workflow.md) | 营业时间、医生排班、staff 如何使用 GPiS 预约、Remarks 治疗代码、待确认问题 |
| [`sql/README.md`](sql/README.md) | Phase 1：查空档的 SQL、测试记录 |
| [`backend/README.md`](backend/README.md) | Phase 2：FastAPI 空档 API；Phase 3：PostgreSQL（安装、建表、改表结构的步骤）；Phase 4a：员工登录、Admin API；Phase 5a：WhatsApp（Meta 测试 App、tunnel、测试清单）；Phase 5b：预约提醒（名单、Open in WhatsApp、测试清单）；资料保留（A10：提醒 90 天后删掉、测试清单）；对照步骤 |
| [`frontend/README.md`](frontend/README.md) | Phase 4b：Admin Platform 网页（React + TypeScript）：安装、启动、测试清单；画面整理（D66）的测试清单 |
| [`docs/deploy-pc-b.md`](docs/deploy-pc-b.md) | 5b 试跑：装到柜台电脑 B（要准备什么、安装、自动启动、备份、检查、先在开发电脑演练和记录、更新、还原备份）；脚本在 `deploy/` |
| [`docs/pc-b-checklist.md`](docs/pc-b-checklist.md) | 去诊所装电脑 B 的打勾清单：出发前、传档案（Google Drive，不用 USB）、到了先看先问、B 和 A 的步骤和时间、B 不合要求 / 连不上 A 怎么办、离开前 |

开始新 session 时先读这四个文件。

## 必须遵守的规则

1. **绝不在主机（诊所生产环境）上做测试**。主机上只允许只读查询和 `BACKUP ... WITH COPY_ONLY`。（例外：诊所同意建一个只读的 SQL 帐号，做法见 `docs/decisions.md` D52）
2. **所有开发和测试都在自己电脑上的 `GPiS_Dev` 测试数据库进行。**
3. 第一阶段对 GPiS **只读，不写入**。
4. **病人资料不能进入仓库、GitHub、AI 对话或云端。** 只处理表结构、设置表和统计数字；云端测试用假数据。截图也一样：先遮住病人名字、HP No、NRIC。
5. **不反编译 GPiS、不解密 `sa` 密码、不读取 `Tbl_User`。**
6. 仓库里不写入任何密码、连接字符串中的密码、access token（用环境变量 / `.env`，并加入 `.gitignore`）。

## 当前进度（2026-10-14）

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
- [x] W40b：纸本是每天一张、所有病人一起签的签名表，没有写 WhatsApp → 在签名表加一句 WhatsApp 的同意，不同意的写 `NO WA`（D55）
- [x] 诊所回答 W54（B 下班有时候关、有时候不关）、W55（签名表加了 WhatsApp 的同意）、W58（B 的 WhatsApp Desktop 登入诊所的号码；员工现在用手机发提醒）（2026-10-13）
- [x] Phase 5b 第一步程序：Reminders 页面（只看名单）+ Open in WhatsApp（`backend/app/reminders.py`、`api/reminders.py`、`reminders_cli.py`，`frontend/src/pages/RemindersPage.tsx`）；没有改数据库；云端 `pytest` 255 个、Vitest 41 个通过，headless Chromium 用假资料点过，全部假数据
- [x] Phase 5b 第一步：开发电脑测试第 1–10 项全部通过（`--check-gpis` OK、4 个测试日期和以前的结果一致、假资料的 Open in WhatsApp 正常，2026-10-09；记录见 `backend/README.md`）
- [x] 测试时找到 `C/UP AFTER ISSUE DENTURE`（装好之后的检查）被当成要等技工所 → `AFTER` 后面的戴牙代码不算（D57）；`pytest` 261 个
- [x] GPiS 的名字后面有的带 `(P)`：名单和消息里拿掉最后的 `(P)`、`(G)`（D56）；`pytest` 257 个
- [x] Phase 5b 第一步合并进 `main`（PR #13）
- [x] Phase 5b 第二步程序：`reminders` 表（按过 Open in WhatsApp 记下来、*Mark as not sent*、按过之后 GPiS 改了会提醒）+ *NO WA*（号码 opt-out，D55）；migration `0004`（D58）；云端 `pytest` 272 个、Vitest 44 个通过，headless Chromium 用假资料点过
- [x] Phase 5b 第二步：开发电脑测试 8 项全部通过（`0004 (head)`、`pytest` 272 个、`npm test` 44 个，2026-10-09；记录见 `backend/README.md`）
- [x] Phase 5b 第二步合并进 `main`（PR #14）
- [x] W51：柜台另一台的 GPiS 用 `sa` 经局域网连 `<主机A的IP>\SQLEXPRESS` → A 不用改设定，只要加只读帐号
- [x] 只读帐号脚本：`sql/create_readonly_login.sql`、`drop_readonly_login.sql`；读主机的 `GPiS` 时帐号不是只读就拒绝（D59）；`--check-gpis` 检查帐号；云端 `pytest` 289 个（SQL 脚本在云端没有 SQL Server 可以跑）
- [x] 只读帐号：开发电脑测试 6 项全部通过（2026-10-11，记录见 `sql/README.md`）
- [x] 测试时找到 GPiS 把 `CREATE TABLE`、`CREATE PROCEDURE`、`BACKUP DATABASE` 等给了 `public`（每个帐号都有，主机 A 也一样）→ 脚本数据库层 `DENY`、其他 201 个表和视图 `DENY SELECT`、最后自己检查；`--check-gpis` 也查 `BACKUP`（D60）；`sqlcmd` 要加 `-C -f 65001`；云端 `pytest` 294 个
- [x] 只读帐号（D59、D60）和测试记录合并进 `main`（PR #15、#16）
- [x] 诊所给了 2026 年休息的公共假期（Johor，10 种）：*Import public holidays* 改成只导入这 10 种，替代假不导入（D61）；要问 W56（替代假）、W57（2027 农历新年多休）；云端 `pytest` 296 个、Vitest 44 个
- [x] 诊所回答 W56（替代假不休；临时休息的日子员工自己加、自己通知病人）、W57（2027 年的名单：多了 New Year's Day、农历新年不多休）、W59（2027 的 Deepavali 是漏写的）→ 导入每年加上 1 月 1 日（D61）
- [x] 假期：开发电脑测试通过（2026-10-12，2026、2027 年各导入 11 天，和诊所的名单一样；临时休息日不能约、已有的预约进 *Needs staff*；记录见 `frontend/README.md`）；`chatbot_dev` 已经照新规则重新导入
- [x] 装到电脑 B 的文件和脚本（草稿）：`docs/deploy-pc-b.md`、`deploy/`（做安装包、登入自动启动、开机备份）；FastAPI 也提供网页、只听 `127.0.0.1`（D62）；要问 W58（B 上的 WhatsApp Desktop）；云端 `pytest` 300 个；PowerShell 脚本只在云端检查过语法
- [x] 假期（D61）和电脑 B 的安装草稿（D62）合并进 `main`（PR #17）
- [x] 开发电脑照 `docs/deploy-pc-b.md` 第 8 节演练（2026-10-12，记录在第 8 节）：第 7 节 1–7 项、停止 / 自己重开、还原备份全部通过；演练前改了：uvicorn 停了由 `start-chatbot.ps1` 自己重开、加 `stop-chatbot.ps1`；演练找到：只用 `Stop-ScheduledTask` 停不干净、B 要装 Python 3.11.9（不是 3.12）和固定版本 `backend/requirements-lock.txt`、加还原备份的步骤（第 10 节）（D63）；已经清理干净
- [x] 演练的修改和记录（D63）合并进 `main`（PR #18）
- [x] 开发电脑重设 `postgres` 的密码（2026-10-12，系统管理员视窗：暂时只让本机的 `postgres` 不用密码 → `\password` → 改回来；新密码在密码管理器）
- [x] 去诊所装电脑 B 的清单（`docs/pc-b-checklist.md`）；顺便改：B 装 PostgreSQL 18、第 7 节第 5 项按过要 *Mark as not sent*、第 6 项在 B 上测（不用 A 的浏览器）、`chatbot_reader` 的密码用密码管理器产生（A 上要看着打）、连 A 有 SSL / TLS 错误时只改 B（`Encrypt=no` → ODBC Driver 17）；合并进 `main`（PR #20）
- [x] 电脑 B 安装第一天（2026-10-12，记录在 `docs/deploy-pc-b.md` 第 11 节）：没带 USB → zip 经 Google Drive 链接下载；ODBC 18、PostgreSQL 18、python.org 的 Python 3.11.9（B 本来有 Store 的 3.11 和 3.12.0，不动、不加 PATH）、`0004`、共用帐号 `admin` / `staff`、假资料（`REMINDER_SOURCE=demo`）、自动启动都好了；A 的只读帐号还没建。找到：`requirements-lock.txt` 的中文说明让英文 Windows 的 pip 读不了 → 改成只有 ASCII、加测试；Store 的 Python、*Python install manager* 不能用
- [x] 电脑 B 第二天（2026-10-13，记录在 `docs/deploy-pc-b.md` 第 11 节）：第一天剩下的都通过（重开机、假期 2026 / 2027 各 11 天、`staff` 登入、清理）；主机 A 建好 `chatbot_reader`（`.sql` 经 Drive 链接在 A 下载，D64；第三次才成功，前两次没有建任何东西）；B 接 A：`--check-gpis` 两个 `[OK]`（ODBC 18 连 SQL Server 2012 没有 TLS 问题）；10-14 的名单 13 个和 GPiS 一样；*Open in WhatsApp* 试过、按回 *Not sent*；A 上的 `COPY_ONLY` 备份删了、私人网盘已登出；B 装了 Windows Terminal（中文显示）；记录合并进 `main`（PR #22）
- [x] 不做 1–2 星期的对照试跑（W42）：2026-10-13 起员工直接按 *Open in WhatsApp* 发（D65）；头一两个星期发之前在 GPiS 扫一眼明天的预约，对不上的记下日期、时间、医生（不记名字、号码）
- [x] Admin Platform 画面整理初版（D66）：左边选单（☰ 收成只有图示；窄的萤幕 ☰ 打开）、登录后先到 Reminders、提醒名单一个号码一张卡片、一排 3 张 + 「Opened in WhatsApp: x of y」、每页统一的标题和说明、表格 / 表单 / 提醒框统一样式（还是不用 UI 套件，D30）；云端 `npm test` 47 个，headless Chromium 截图每一页（1920 / 1366 / 1024 / 400 宽），全部假资料
- [x] D65 和画面整理（D66）合并进 `main`（PR #23）
- [x] 画面整理：开发电脑照 `frontend/README.md`「画面整理（D66）」的 15 项全部通过（2026-10-13）
- [x] 电脑 B 更新到 PR #23 的版本（2026-10-13，`16655f6`；记录在 `docs/deploy-pc-b.md` 第 11 节）：`--check-gpis` 两个 `[OK]`、明天的名单数目和 GPiS 一样、登入后到 Reminders；旧文件夹改名失败（Access denied），新版直接盖在原来的文件夹（只改网页，所以可以），第 9 节加了「改名失败就停下来」；记录合并进 `main`（PR #24）
- [x] 不用 USB（D64）：zip 和 A 的 `create_readonly_login.sql` 都经 Google Drive 链接，在 B / A 的 InPrivate 视窗下载（不登入）、对 hash、用完就删；文件照着改；第一天的记录、`requirements-lock.txt` 的修正和 D64 合并进 `main`（PR #21）
- [x] Phase 5b 设计 + A1 合并进 `main`（PR #11）
- [x] 5c 的 Plan B、第三方平台、Meta 的费用（2026-10-01 起 24 小时内的消息也收费）整理进 `docs/architecture.md` 第 10 节；5b 加「Open in WhatsApp」按钮，不用等 5c（D54）
- [x] 清理网盘中转文件（2026-10-13：Drive 上的 zip 删了、垃圾桶清空了）
- [x] A10 提醒的保留期限（D67）初版：预约日期过了 90 天的 `reminders` 整行删掉、只留每天的数目（`reminder_stats`，migration `0005`）；*NO WA* 的号码一直留，改回照常、没有对话的号码删掉；B 每次登入先备份、**备份成功才清理**（`python -m app.retention`，`--dry-run`、`--stats`），备份超过 30 天的也删；`/api` 加 `Cache-Control: no-store`（headless Chromium：假名字在浏览器快取里 2 个档案 → 0 个）；要问诊所 W60；云端 `pytest` 316 个、Vitest 47 个，PowerShell 只在云端用 PowerShell 7 试过，全部假数据
- [x] A10：开发电脑测试 10 项全部通过（2026-10-13，Windows PowerShell 5.1；记录见 `backend/README.md`）：`0005 (head)`、`pytest` 316 个、`npm test` 47 个；没有 pgpass 时备份失败、不清理；有了之后先备份再删 1 条、40 天前的假备份删了、`reminder_stats` 累加成 `2 | 1 | 4`；`no-store`；已经清理干净。找到：开发电脑的 `psql` 不在 PATH（用完整路径 `$psql`）、过了半夜 `CURRENT_DATE` 会变 → 清单改了
- [x] A10（D67）和开发电脑的测试记录合并进 `main`（PR #26）
- [x] B 的 uvicorn 日志「留最新 14 个」其实没有在删：删的那一行在 uvicorn 停了之后，关机、`stop-chatbot.ps1` 都会连脚本一起停掉、轮不到 → 改成**启动前**删（`deploy/start-chatbot.ps1`）；PowerShell 7 用假档案跑过脚本里的那一段（20 个旧的、启动 4 次 → 剩 14 个）；开发电脑 Windows PowerShell 5.1 试过（2026-10-14：20 个假日志 → 启动一次剩 14 个，最旧的是 `0908`）；合并进 `main`（PR #27）
- [x] 5c 的比较（2026-10-14，D68）：**提醒继续手动**，不为提醒接 5c（省的时间不够付费用）；5c 等 Phase 6 的 AI 才接，选只给 API、支持 Coexistence 的 BSP；不自己当 Tech Provider（要验证自己的公司）；全部用诊所的名义，开发者当管理员；刚开始不做商家验证（要的时候用 SSM + 水电费单 / 银行月结单）；Coexistence 之后 B 的 WhatsApp for Windows 不支持
- [x] Phase 6 设计草稿（只有文件，没有程序）：`docs/architecture.md` 第 11 节（AI 推荐时段、员工先输入 GPiS 再按 *Confirm*；A8 的做法；工具只回最少资料；转员工的情况；病人资料和 AI 公司 A11；默认 Claude Opus 5.5 和费用粗估；分 6a–6d）；要问诊所 W61–W71；病人传了 IC / 护照号码：存之前遮掉后面 6 位、留生日（D69），要问 W72

## 下一步

1. 员工用 *Open in WhatsApp* 发（D65，2026-10-13 起）：一两个星期后问员工名单有没有漏掉的、*Needs staff* 有没有处理（只问日期、时间、医生，不要截图）；对不上的记下来，回来一起找原因。
2. 画面整理（D66，PR #23）：B 已经更新（2026-10-13）。和第 1 项一起，一两个星期后问员工新画面（卡片、☰）好不好用。画面还是英文（D24）。
3. A10（D67）：已经合并（PR #26）→ 开发电脑 `git checkout main`、`git pull`（`alembic current` 是 `0005 (head)`）→ 更新 B（这次**有改表** `0005`：照第 9 节完整做、改名成 `.old`，当天的提醒发完之后才更新）。uvicorn 日志的修正（PR #27，只改 `deploy/start-chatbot.ps1`）跟下一次更新 B 一起装。问诊所 W60（90 天可以吗）。B 2027-01-13 之前每次都是 `删了 0 条`；那之后看一次 `start.log`，确认第一次真的删了。
4. 更新电脑 B：照 `docs/deploy-pc-b.md` 第 9 节（zip 经 Google Drive 链接、对 hash，D64）；更新前先在开发电脑跑过测试。B 上**不跑测试**，读的是主机 A 的正式资料。第一版模板没有按钮（D48）；真的用 Cloud API 发只用假的预约来源 + Meta 测试号码 + 允许名单（D44）。每次测 WhatsApp：cloudflared 重开后要改 Meta 的 *Callback URL*；System User 的 token 60 天失效（D39）；有问题先跑 `python -m app.whatsapp_check`。
5. Phase 6（AI）：先看设计草稿（`docs/architecture.md` 第 11 节），整理 W61–W71 的中英问卷请老板回答，照回答改设计，再从 6a（A8 + 工具，不接 AI）开始写程序。提醒继续手动（D68）；5c 等 AI 要上线才接（BSP + Coexistence，老板签约）。
6. A1：B 经局域网用只读帐号读 A，已经通了（2026-10-13）。B 下班有时候关（W54）：Phase 6 之前决定长期放哪里（`docs/architecture.md` 9.4）。
7. 假期：B 已经导入 2026、2027 年（2026-10-13）。2028 年的在 2027 年底前导入、核对回教节日的日期（D61）；诊所临时休息的日子 `admin` 自己加。
8. A8（还没录入 GPiS 的请求要算占用）是 Phase 6 的第一步（6a），建议的做法在 `docs/architecture.md` 11.6。

改空档规则时，`sql/check_available_slots.sql` 和 `backend/app/availability.py` 要一起改，再用上面的测试日期对照一次；提醒名单沿用同一套判断（D41），也要再看一次。
改表结构时：改 `backend/app/db/models.py` → 加 Alembic migration → `pytest`（步骤见 `backend/README.md`「改表结构的步骤」）。
改 API 的回传栏位时：`frontend/src/types.ts` 也要一起改，再 `npm run build`（TypeScript 会指出画面上用到旧栏位的地方）。
