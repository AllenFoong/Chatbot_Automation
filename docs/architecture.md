# 系统架构与技术选型

> 最后更新：2026-09-30

## 1. 需求

- 病人用 **WhatsApp** 预约，不需要下载 App、不需要注册。
- **AI Agent** 代替客服：病人说出想要的时间，AI 查空档并自动回复。
- **人工随时可介入**：Admin Platform 可查看所有对话、接手对话、确认/拒绝预约。
- **不影响 GPiS**：第一阶段只读取 GPiS 预约数据判断空档，最终预约由员工录入 GPiS。

## 2. 两层结构

原本讨论的两个方案不是二选一，而是上下两层：

```
方案 B：AI Agent（对话层）     理解病人、推荐时段、自动回复
          │ Tool Calling
方案 A：GPiS 数据（数据层）    查询空档、（将来）写入预约
          │
人工介入 / Admin Platform      查看对话、接手、审批
```

没有数据层，AI 不知道真实空档；没有对话层，数据层只是查询工具。

## 3. 目标架构

```
病人 ──WhatsApp──→ WhatsApp Cloud API ──Webhook──→ Backend (FastAPI)
                                                     │
                     ┌───────────────────────────────┼──────────────────┐
                     ▼                               ▼                  ▼
               AI Agent (LLM)                  PostgreSQL          GPiS SQL Server
               Tool Calling                   （本系统数据，读写） （只读，查空档）
                                                     │
                                                     ▼
                                          Admin Platform (React)
                                                     │
                                                     ▼
                                     员工确认 → 手动录入 GPiS
```

## 4. 技术选型

| 部分 | 选择 | 说明 |
|---|---|---|
| Backend | Python + **FastAPI** | 适合 REST API 与 Webhook，方便接入 LLM |
| 本系统数据库 | **PostgreSQL** | 存 WhatsApp 对话、消息、预约请求、员工账号 |
| 读取 GPiS | **SQL Server** via `pyodbc` / SQLAlchemy | 专用只读账号，只开放预约相关表 |
| Admin Platform | **React** | 员工查看对话、接手、审批 |
| 消息入口 | **WhatsApp Cloud API** | Webhook 收消息，API 发消息 |
| AI | LLM + **Tool Calling** | 第二阶段加入 |
| 部署 | Docker → 云端（AWS 等） | 云端测试只用假数据 |

### 本系统数据库（初步）

```
customers             id, name, phone, gpis_contact_id (nullable), created_at
conversations         id, customer_id, mode (BOT / HUMAN / CLOSED), assigned_staff_id, created_at
messages              id, conversation_id, direction (IN / OUT), sender (CUSTOMER / BOT / STAFF), body, wa_message_id, created_at
appointment_requests  id, customer_id, conversation_id, service, preferred_date, preferred_slot, doctor_id,
                      status (PENDING / CONFIRMED / REJECTED / CANCELLED), handled_by,
                      gpis_appointment_id (nullable，员工录入 GPiS 后填上；改期时 ID 不变),
                      group_id (nullable，一起来的多位病人共用，对应 Remarks 的 WITH), created_at
staff                 id, name, role, password_hash, created_at

-- 诊所设置（GPiS 没有，由本系统配置，员工可在 Admin Platform 修改）
doctors               id (= GPiS DoctorID), display_name, remark_tag ('P' / 'G'), active
doctor_schedules      doctor_id, weekday (1=一 … 7=日), is_working, start_time, last_slot, break_start, break_end
services              code ('OR', 'S+P', 'RCT' …), name,
                      may_need_1h (可能要 1 hour，由员工看情况决定), can_be_third (能否当一格的第 3 人), multi_step,
                      ai_can_book (AI 能否自己推荐时段；否 = 收集需求后转员工，见 D16), active
clinic_closures       date, reason                         -- 假期管理模块维护：全国 + Johor 公共假期、农历新年多休的日子、诊所自定休息日
                                                           -- 每年可用程序预填公共假期（如 Python `holidays` 套件），员工再核对、补上多休的日子
settings              max_per_slot（默认 3）、max_per_slot_for_ai（默认 3；改成 2 = AI 不用第 3 个名额）等
```

`appointment_requests.service` 使用 GPiS Remarks 的同一套治疗代码（`C/UP`、`S+P`、`OR` …，见 [`clinic-workflow.md`](clinic-workflow.md) 第 6 节），员工录入 GPiS 时可以直接照抄。

### AI Agent 工具（初步）

```
check_available_slots(date, service, doctor_id?, duration = 30)  → 读 GPiS 当天预约 + 本系统排班、疗程设置，规则见下
create_appointment_request(...)            → 写 PostgreSQL（PENDING）
get_customer_by_phone(phone)               → 读 GPiS Qry_CAH_Appointment / Tbl_CAH_ContactNumbers（一个号码可能对应多位病人）
                                             号码先标准化成国际格式再比对（约 12% 是新加坡号码），规则见 gpis-database.md 统计查询 C 的结果
get_treatment_doctor(contact_id, service)  → 读 GPiS：这位病人上一次同类疗程的医生；多步骤疗程的后续预约必须用这位医生（W9）
                                             只回传医生，不回传病历（最少必要信息）
handover_to_human(reason)                  → conversation.mode = HUMAN，通知员工
```

GPiS 的预约**可能被删除**（W26），所以每次都重新读 GPiS，不缓存旧结果；`appointment_requests.gpis_appointment_id` 在 GPiS 找不到时，在 Admin Platform 提醒员工。

```
```

### 空档计算规则（初版，待统计查询 B 验证）

业务规则来源见 [`clinic-workflow.md`](clinic-workflow.md)。原则：**宁可少推荐，也不要重复预约**；不确定的情况转人工。

```
输入：date, service（要预约的疗程代码）, doctor_id（多步骤疗程固定为原来的医生）, duration（30 或 60，默认 30）
1. clinic_closures 有这一天，或 doctor_schedules 显示该医生这天不上班 → 没有空档
2. 候选时段 = 该医生这天 start_time … last_slot，每 30 分钟一格，扣掉 break_start … break_end
   （例：PHANG 星期三 → 9:00 … 16:30，扣掉午休 12:00、12:30 → 14 格；GOH 星期一 → 9:00 … 15:30，扣掉午休 13:00、13:30 → 12 格）
3. 从 GPiS 读该医生这天的预约，排除 Status 为 Canceled 的
4. 先看本系统的"医生请假"记录，再找 GPiS 的占位记录，不论在哪个时段（包括 00:00）、不论联系人是谁
   （统计 B7、B12：诊所联系人也用来记真实疗程，OFF DAY 记录的联系人都不是诊所 → 按 Remarks 判断）：
     - 本系统记录了请假，或 Remarks 去掉空格后含 OFFDAY（包括农历新年、圣诞节的写法；`OFF SUNDAY` 不算）→ 该医生这天没有空档
     - 诊所联系人的其他写法（如 1130 FIRST APPT、GO BANK）→ 这天整天标记 NEEDS_REVIEW，AI 不自动推荐，转员工
   占位记录本身不算病人，之后不再计算
5. 再排除 TimeSlot = '00:00'（提醒 / 未定时间）和 Status = Postpone，剩下的才是占用时段的预约
6. 现有预约里的长预约独占多格：1 hour 占 2 格，1.5 hour 占 3 格；被占的格整格封锁
   时长只看 Remarks（W17）：转大写、去空格后用正则匹配"数字 + H / HR / HOUR(S)"，
   1.5 / 1.30 / 1HOURS30 = 90 分钟（3 格，W23）；有 HOUR 字样但解析不了 → 当天转人工（写法见统计 B5、C4）
   xxMIN（如 20MIN!!!）一律当 30 分钟、1 格（W24）
7. 判断每个候选时段 S：
   a. duration = 60（员工决定这次要 1 hour）：
        S 和下一格都没封锁、都是 0 人，且下一格不是午休
        （S = last_slot 例外：可以做到下班之后，PHANG 16:30 → 17:30、GOH 15:30 → 16:30（W16、W27））
   b. duration = 30：
        S 没封锁，且已占人数 < 上限
        上限 = 3，如果 service.can_be_third 且前一格、后一格都不是 3 人；否则 2
        AI 用的上限 = min(上限, max_per_slot_for_ai)
```

- `duration = 60` 给 Admin Platform 用，帮员工找 1 hour 空档。AI 只推荐 30 分钟、`ai_can_book` 的疗程；`may_need_1h` 的疗程和 implant、denture、RCT 的后续步骤，由员工决定，AI 收集需求后转员工（D15、D16）。
- AI 可以用第 3 个名额，但只限 `can_be_third` 的疗程；员工最后仍要确认（D6）。
- 多人一起来（Remarks 的 `WITH`）：AI 先找一格剩余名额够所有人的时段，找不到就转员工。

## 5. 人工介入设计

- 每段对话有 `mode`：`BOT` / `HUMAN` / `CLOSED`。员工接手后，AI 停止回复该对话。
- 所有进出消息都存入 `messages`，Admin Platform 实时显示、可搜索、可直接回复。
- **自动转人工**：投诉、急症、AI 不确定、病人要求真人、连续多次无法理解。
- **WhatsApp 24 小时规则**：病人最后一条消息 24 小时后，只能发预先审批的模板消息。
- 对话发给 LLM 前要考虑病人隐私（最少必要信息）。

## 6. 开发路线

| Phase | 内容 |
|---|---|
| 0 | 建测试环境：开发电脑还原 `GPiS_Dev`，跑统计查询（进行中） |
| 1 | 在 `GPiS_Dev` 上写出"查某天某医生空档"的 SQL |
| 2 | FastAPI 封装 `check_available_slots()` 等 API |
| 3 | PostgreSQL：customers / conversations / messages / appointment_requests |
| 4 | React Admin Platform：看对话、接手、确认/拒绝；排班、疗程、**假期管理**模块（公共假期、农历新年多休等） |
| 5 | WhatsApp Cloud API（Webhook）；预约前一天自动提醒（模板消息，要读 GPiS 明天的预约，和 A1 一起设计）。员工现在一个个手动发，提醒又不需要 AI，可以比 Phase 6 的 AI Agent 更早上线 |
| 6 | AI Agent（Tool Calling）+ 转人工规则 |
| 7 | Docker 化，部署到云端（假数据） |
| 8 | 解决主机 ↔ 云端同步，再评估是否写入 GPiS |

## 7. 未解决的架构问题

| # | 问题 |
|---|---|
| A1 | **主机不在公网**：云端 Backend 如何读取主机上的 GPiS？候选：诊所本地放一个同步小程序，定时把空档（不含病人资料）推送到云端 |
| A2 | AI 自主程度：只收集需求 / 推荐空档由员工一键批准 / 空档明确时自动确认？ |
| A3 | 员工在哪里介入：只用网页 Admin Platform，还是也要手机？ |
| A4 | 各服务的时长？✅ 一般 30 分钟；`RCT`、`IMPLANT`、`SCAN B`、`VENEER` 等可能要 1 hour，由员工看情况在 Remarks 写 `1 hour`（`clinic-workflow.md` 第 2 节） |
| A5 | 是否已获得诊所 / GPiS 开发商对这种数据使用方式的书面同意？ |
| A6 | 项目性质（学习 / 毕业项目 / 正式上线）、时间与预算（LLM、WhatsApp API 费用）？ |
| A7 | 病人已经习惯用诊所现有的 WhatsApp 号码，诊所用的是 **WhatsApp Business App**（W18）。候选：Meta 的 **Coexistence**，同一个号码同时用 Business App 和 Cloud API，保留聊天记录，员工仍可在手机上回复（第三方资料显示马来西亚已支持）。已知限制：每秒最多 20 条消息；不支持群组、广播列表、语音 / 视频通话、目录（catalog）、限时消息等。**待验证**：以 Meta 官方文件为准；员工在手机上发的消息，本系统能不能看到（Admin Platform 要显示完整对话） |
