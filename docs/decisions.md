# 决定记录

> 每条决定写明原因。推翻某条决定时，不删除原记录，新增一条并注明取代哪一条。
> 最后更新：2026-10-05

| # | 决定 | 原因 |
|---|---|---|
| D1 | **不反编译 GPiS**，只研究数据库结构 | 手上没有源代码；反编译通常违反 EULA；数据库是标准 SQL Server，足够用 |
| D2 | **不解密 `sa` 密码**，用 Windows 身份验证连接 | 没必要，也等于破解厂商保护 |
| D3 | **主机只做只读查询和 `COPY_ONLY` 备份，不做任何测试** | 主机是诊所每天营业的生产环境 |
| D4 | 在**开发电脑**上还原为 **`GPiS_Dev`**，所有测试都在它上面做 | 可以随便试，弄坏了重新还原即可 |
| D5 | 第一阶段对 GPiS **只读，不写入** | `AppointmentID` 不是自动编号（GPiS 很可能用 MAX+1），同时写入会冲突；`TimeSlot`、`Duration` 格式也还没摸清 |
| D6 | 预约流程：**AI 读空档 → 生成待确认请求 → 员工确认后手动录入 GPiS** | 避免重复预约和写入风险 |
| D7 | 将来集成用**专门的只读 SQL 账号**，只开放预约相关表，**绝不用 `sa`** | 最小权限原则 |
| D8 | **营业时间由本系统配置** | GPiS 的 `RefTimeSlot` 覆盖全天 24 小时，没有营业时间 |
| D9 | 本系统数据用 **PostgreSQL**（读写），GPiS 的 **SQL Server 只读** | 两个数据库职责分开 |
| D10 | 方案 A（数据层）和方案 B（AI 对话层）**合并**成上下两层，而不是二选一 | AI 需要真实空档；数据层需要对话入口 |
| D11 | 不为病人开发 Mobile App | WhatsApp 即可完成预约，App 只会增加步骤 |
| D12 | GPiS 参考文件放在单独的私有仓库 `AllenFoong/GPiS-reference`；上传前排除 `.7z`、`.mp4`、`.pdb`、`.Err` 日志、图标图片，config 里的密码先遮掉 | 和本项目分开；避免大文件和敏感资料 |
| D13 | `Tbl_User` 本系统**绝不读取** | 员工密码很可能明文保存 |
| D14 | 医生排班、午休、疗程规则（占几格、能否当第 3 人）、每格容量、假期都存在本系统的设置表（`doctor_schedules`、`services`、`clinic_closures` 等），员工可在 Admin Platform 修改；假期由**假期管理模块**维护（全国 + Johor 公共假期、农历新年多休的日子）（扩展 D8） | GPiS 没有这些设置；排班、疗程规则、假期每年都会变，不能写死在代码里 |
| D15 | 空档计算**宁可少推荐，也不重复预约**：状态不明的算占用；现有预约只有 Remarks 写了 `1 hour` 才当 1 hour（员工看情况决定）；AI 只在 `OR`、`S+P`、`F`、`RETAINER` 时用第 3 个名额（可用 `max_per_slot_for_ai` 关掉）；`OFF DAY` 以外的占位记录、可能要 1 hour 的疗程、implant / denture / RCT 的后续步骤转人工 | Remarks 是自由文字，无法可靠解析；推荐错了比少推荐更伤害诊所信誉 |
| D16 | 多步骤疗程（implant、denture、矫正、RCT）的后续预约**只推荐原来那位医生**的时段。矫正的后续预约（`OR`、`RETAINER`、`RB`）由 AI 处理；implant、denture、RCT 的后续步骤转人工 | 诊所规定同一疗程要同一位医生做完（W9）；矫正的后续预约每次内容固定、30 分钟，`OR` 每月都有、数量多，最适合交给 AI；implant、denture、RCT 的下一步是哪一步、什么时候能来（例如要等技工所）、要不要 1 hour，AI 判断不了 |
| D17 | **对话按 WhatsApp 号码分**（`wa_contacts` → `conversations`），预约请求才指向具体哪一位病人（`appointment_requests.customer_id`）；`customers.phone` 不唯一（取代 `architecture.md` 初稿的 `conversations.customer_id`） | 统计 B11：2,243 个号码对应多于一位病人；一段对话可能帮几位家人预约 |
| D18 | 本系统数据库用 **SQLAlchemy 2.0 + Alembic + psycopg 3**；表结构的每次修改都写成 migration（`backend/migrations/`），测试检查 migration 建出来的表和 `models.py` 一模一样 | 表结构有版本记录；开发电脑和将来的云端用同一个指令建出一样的表 |
| D19 | 规则尽量写成**数据库约束**（CHECK、UNIQUE）：时间在 30 分钟格上、每格上限 1–3、一个号码只有一段没结束的对话、同一条 WhatsApp 消息只存一次。`clinic_settings` 只有一行、每个设置一栏（不用 key-value 表） | 程序有 bug、两个请求同时到、员工在 Admin Platform 输入错的值时，数据库是最后一道防线；每个设置一栏才能有类型和范围检查 |
| D20 | 测试连**真正的 PostgreSQL**，不用 SQLite 代替；测试数据库名字必须以 `_test` 结尾（测试会清空它），测试不能连 `DATABASE_URL`；没有设置 `TEST_DATABASE_URL` 就跳过 | SQLite 和 PostgreSQL 的行为不同（partial index、时区、CHECK）；名字检查防止清空开发用的数据库 |
| D21 | `services.multi_step`（是 / 否）改成 `treatment_group`（`IMPLANT` / `DENTURE` / `ORTHO` / `RCT`） | `get_treatment_doctor` 要找"上一次**同类**疗程"的医生（W9），光有是 / 否不知道哪些代码是同一类 |
| D22 | 员工在 `BOT` 模式的对话里回复，**等于接手**（mode 改成 `HUMAN`），AI 不再回复 | 避免 AI 和员工同时回复同一位病人 |
| D23 | `messages` 不存 `direction`，由 `sender` 决定（`CUSTOMER` = 收到，`BOT` / `STAFF` = 发出）；WhatsApp 24 小时规则从 `messages` 算出来，不另外存一栏 | 同一件事只存一次，不会互相矛盾 |
| D24 | Admin Platform **画面用英文**，前端用 **React + TypeScript**；Phase 4 分两步：4a 后端 API，4b 网页 | 员工习惯 GPiS 和疗程代码的英文；TypeScript 打错栏位名字时编辑器会提醒；每一步小一点比较好测试 |
| D25 | 员工分 **ADMIN / STAFF**：STAFF 处理对话和预约请求；只有 ADMIN 能改排班、疗程、假期、请假、每格上限、员工账号；至少要留一个 active 的 ADMIN | 设置改错会影响所有病人的空档；最少权限原则 |
| D26 | 登录用**服务器端 session**：密码用 Argon2 加密；cookie 是 HttpOnly + SameSite=Strict、12 小时失效；数据库只存 token 的 SHA-256；员工停用、重设密码时，已登录的马上失效（不用 JWT） | 网页里有病人资料；HttpOnly 防 XSS 偷 token，SameSite 防 CSRF；服务器端 session 可以马上撤销，JWT 做不到 |
| D27 | 公共假期用 Python `holidays` 套件预填（马来西亚 + Johor），**只加没有的日子**；农历新年多休的日子由员工自己加 | 每年手动输入容易漏；回教节日是预估日期、诊所多休的日子套件不知道，所以导入后要员工核对 |
| D28 | 员工在 Admin Platform **回复病人**的功能等 Phase 5 接上 WhatsApp 才做 | 现在存一条"发出"的消息，病人其实收不到，会误导员工 |

## 数据安全规则（病人资料，受马来西亚 PDPA 保护）

- ❌ 不用 WhatsApp / Telegram / 邮件附件传备份
- ❌ 不把数据库、备份、病人记录放进 GitHub 或任何 AI 对话
- ✅ 传输前用 **7-Zip AES 加密**（勾选"加密文件名"），密码不和文件放在一起
- ✅ 网盘中转后**删除文件并清空回收站**；公司电脑上退出私人账号
- ✅ 云端测试一律用**假数据**
- ✅ 给 AI 看 GPiS 截图前，先遮住 Patient Name、HP No、NRIC、House No 等栏位（或者用 `GPiS_Dev` 的假数据截图）

### 记录：备份的传输方式

主机（公司网络）与开发电脑（家里网络）不在同一网络，远程控制工具 Parsec 不支持传文件。
最终做法：主机上 7-Zip 加密 → 私人网盘（不分享）→ 开发电脑下载解压到 `D:\GPiS\GPiS_copy.bak`。
