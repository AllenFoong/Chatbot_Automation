# 系统架构与技术选型

> 最后更新：2026-09-28

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
                      status (PENDING / CONFIRMED / REJECTED / CANCELLED), handled_by, created_at
staff                 id, name, role, password_hash, created_at
```

### AI Agent 工具（初步）

```
check_available_slots(date, doctor_id?)   → 读 GPiS（Tbl_CAH_RefTimeSlot − 已占用 Tbl_CAH_Appointment ∩ 营业时间）
create_appointment_request(...)            → 写 PostgreSQL（PENDING）
get_customer_by_phone(phone)               → 读 GPiS Qry_CAH_Appointment / Tbl_CAH_ContactNumbers
handover_to_human(reason)                  → conversation.mode = HUMAN，通知员工
```

空档计算：`营业时间内的时段` − `该医生当天占用时段的预约`（占用状态见 `gpis-database.md` 第 4 节）。营业时间由本系统配置（GPiS 没有）。

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
| 4 | React Admin Platform：看对话、接手、确认/拒绝 |
| 5 | WhatsApp Cloud API（Webhook） |
| 6 | AI Agent（Tool Calling）+ 转人工规则 |
| 7 | Docker 化，部署到云端（假数据） |
| 8 | 解决主机 ↔ 云端同步，再评估是否写入 GPiS |

## 7. 未解决的架构问题

| # | 问题 |
|---|---|
| A1 | **主机不在公网**：云端 Backend 如何读取主机上的 GPiS？候选：诊所本地放一个同步小程序，定时把空档（不含病人资料）推送到云端 |
| A2 | AI 自主程度：只收集需求 / 推荐空档由员工一键批准 / 空档明确时自动确认？ |
| A3 | 员工在哪里介入：只用网页 Admin Platform，还是也要手机？ |
| A4 | 各服务的时长（洗牙、补牙、根管等）？ |
| A5 | 是否已获得诊所 / GPiS 开发商对这种数据使用方式的书面同意？ |
| A6 | 项目性质（学习 / 毕业项目 / 正式上线）、时间与预算（LLM、WhatsApp API 费用）？ |
