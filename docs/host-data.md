# A1：本系统怎么读主机上的 GPiS

> 设计初稿，**还没有定案**：要等诊所回答第 7 节的问题（H1–H8），再把第 8 节的决定编进 [`decisions.md`](decisions.md)。
> 本文件不含病人资料、密码、诊所识别信息。
> 最后更新：2026-10-08

## 1. 问题

- GPiS 在诊所的**主机**上（Windows 电脑，SQL Server **2012** Express，数据库 `GPiS`），局域网里有几台电脑在用 GPiS（[`gpis-database.md`](gpis-database.md) 第 1 节）。GPiS 自己用 `sa` 连数据库。
- 本系统现在只读开发电脑上的 `GPiS_Dev`，那是 **9 月 28 日的快照**。正式上线一定要读主机上**现在**的预约。
- 主机**不在公网**，外面连不进去；主机上最后一次备份是 2021 年。
- 已经定的规则：主机只做只读查询和 `COPY_ONLY` 备份（D3）；对 GPiS 只读、不写（D5）；用专门的只读帐号，绝不用 `sa`（D7）。

## 2. 本系统要从 GPiS 读什么

| 谁要用 | 读什么 | 要多新 | 有没有病人资料 |
|---|---|---|---|
| 空档（员工的 `/availability`；Phase 6 的 AI） | 某天、某医生的预约：`TimeSlot`、`Status`、`ContactID`、`Remarks` | **每次都要最新**：员工会删改预约（W26），用旧资料会重复预约（D15） | `Remarks` 可能有家人名字（`WITH …`） |
| 用电话找病人（`get_customer_by_phone`） | 电话 → `ContactID`、名字 | 最新 | 有 |
| 原来的疗程医生（`get_treatment_doctor`，W9） | 某位病人以前同类疗程的医生 | 最新 | 有（只回传医生） |
| 5b 预约前一天提醒 | 明天的预约 + 病人名字、手机 | 发之前读一次 | 有 |
| A8 对上 GPiS 的预约 | 日期、时段、医生、病人 | 最新 | 有 |

结论：**几乎每一项都要病人资料，而且要最新的**。原本 A1 的想法"定时把空档（不含病人资料）推上云端"只够第一项用，不够。

## 3. 先要决定：本系统正式上线放在哪里

A1 的答案取决于本系统放在哪里：

- **放在诊所里**：和主机在同一个局域网，直接读就好；只要让 Meta 连得到 webhook（和现在开发一样用 tunnel）。
- **放在云端**：要想办法把主机的资料送到云端，病人资料就会离开诊所。

病人资料方面要注意：

- `CLAUDE.md` 规则 4 写"病人资料不能进入云端"，那是开发阶段的规则。正式上线如果放云端，等于推翻它，要诊所同意（A5），也要照 PDPA 处理（云端机房在不在马来西亚、和云端公司的资料处理协议）。
- 不管放哪里，WhatsApp 的对话本来就会经过 Meta。Phase 6 的 AI 也会把对话送给 LLM，那是另一个决定（最少必要信息）。

## 4. 候选方案

```
方案 1  系统放诊所里的一台电脑（不是主机），在局域网直接读 GPiS
        病人 ⇄ Meta ⇄ tunnel ⇄【系统电脑：Admin API、webhook、PostgreSQL】⇄ 局域网 ⇄【主机：GPiS】

方案 2  系统放云端；诊所放一个"GPiS 小窗口"（gateway），只开放几个固定的查询
        病人 ⇄ Meta ⇄【云端：Admin API、webhook、PostgreSQL】⇄ tunnel ⇄【诊所电脑：gateway】⇄【主机：GPiS】

方案 3  系统放云端；诊所放一个同步小程序，定时把资料推上云端（原本 A1 的想法）
        【主机：GPiS】⇄【诊所电脑：同步程序】→ 每几分钟推一次 →【云端：本系统】

方案 4  系统放云端，经 VPN 直接连主机的 SQL Server
```

| | 方案 1 诊所里 | 方案 2 云端 + gateway | 方案 3 云端 + 同步 | 方案 4 云端 + VPN |
|---|---|---|---|---|
| 资料多新 | 每次直接查，最新 | 每次问 gateway，最新 | 每几分钟一次，中间可能已经被约走 | 最新 |
| 病人资料去哪里 | 留在诊所 | 每次只传回需要的几栏；对话存云端 | **整批复制到云端**（未来几十天的预约、电话） | 云端直接查 |
| 主机要改什么 | 一个只读帐号；SQL Server 接受局域网连线（见第 5.2 节） | 同方案 1 | 同方案 1 | 要对 VPN 开放 SQL Server |
| 诊所要多什么 | 一台 24 小时开着的电脑 + UPS | 一样要一台 24 小时开着的电脑 | 一样要一台 | 主机装 VPN |
| 诊所断网、停电 | Meta 会重送 webhook（第三方资料说最多 7 天）；恢复后补收 | 云端照收消息；读不到 GPiS → 空档转人工 | 云端用旧资料，可能是错的 | 读不到 GPiS → 转人工 |
| 要写的程序 | **最少**：现在开发就是这样跑的 | 多一个 gateway 服务 + 它的验证 | 最多：同步、删除（W26）、冲突 | 少，但设定 VPN |
| 安全上最担心 | 系统电脑本身要顾好 | gateway 在网上找得到，要保护好 | 云端存最多病人资料 | SQL Server 2012 已经没有安全更新（2022-07-12 停止），开到网上风险最高 |

方案 5（每天在主机做 `COPY_ONLY` 备份，搬去别处还原）资料一天才更新一次，不能用来查空档，直接排除。

## 5. 建议：先用方案 1，以后需要再换方案 2

理由：

1. **最新**：每次直接查主机，员工刚删改的预约马上反映出来（W26、D15）。
2. **病人资料留在诊所**：PDPA 最单纯，也符合规则 4 的精神。
3. **程序几乎不用改**：开发电脑现在就是"Admin API + webhook + PostgreSQL + 读 GPiS + tunnel"，只是 `GPiS_Dev` 换成主机的 `GPiS`。
4. **以后可以换**：读 GPiS 的地方已经是一个接口（`backend/app/gpis.py` 的 `AppointmentSource`）。要搬到云端时，把它换成"问 gateway"，就变成方案 2。

方案 1 的缺点，要诊所先知道：

- 诊所要有一台 **24 小时开着**的电脑。建议另买一台小电脑，不要装在主机上，不影响 GPiS（D3）。
- 系统电脑或网络停了，WhatsApp 消息会延后（Meta 重送），AI 也不会回复；员工在诊所里仍然可以用 GPiS 照常工作。
- 维护要靠远程（Parsec）或到诊所；系统电脑也要备份（PostgreSQL）。
- 员工在诊所外（例如用手机）要看 Admin Platform 的话，要再设计（A3）。

### 5.1 方案 1 的样子

```
诊所的局域网
  主机（不动）：GPiS、SQL Server 2012 Express
      ▲  只读帐号 chatbot_reader：只能 SELECT 指定的表和栏位
      │
  系统电脑（新的，24 小时开着）
      Admin API（8000）+ webhook（8001）+ PostgreSQL + 网页（build 好的，由 Admin API 提供，D29）
      ▲                                  │
      │ 局域网                           │ cloudflared：固定网址，只通到 webhook（D35）
  员工电脑的浏览器                         ▼
                                     Meta ⇄ 病人的手机
```

- tunnel 要用**固定网址**（Cloudflare 帐号 + 自己的网域，"named tunnel"）：开发用的 `trycloudflare.com` 每次重开都会变，不能用在正式环境。
- 网页不再用 `npm run dev`（视窗 4）：`npm run build` 后由 Admin API 一起提供（D29 已经这样规划）。

### 5.2 读主机的 GPiS：只读帐号

| 项目 | 做法 |
|---|---|
| 帐号 | SQL Server 登录 `chatbot_reader`（GPiS 已经开了 SQL 登录，因为它用 `sa`）；密码只放系统电脑的 `.env` |
| 权限 | **只给需要的表和栏位** `SELECT`（栏位层级的 `GRANT`），不加入 `db_datareader`。不给 `NRIC`、`DOB`、`HouseNo` 这些用不到的栏位 |
| 明确禁止 | `DENY SELECT ON Tbl_User`（D13）；没有任何 `INSERT`、`UPDATE`、`DELETE` |
| 初稿的清单（写程序时再对照） | `Tbl_CAH_Appointment`：`AppointmentID`、`AppointmentDate`、`TimeSlot`、`ContactID`、`ContactName`、`DoctorID`、`Status`、`Remarks`<br>`Tbl_CAH_ContactNumbers`：`ContactID`、`DisplayType`、`DisplayValue`<br>`Tbl_CAH_Contact`：`ContactID`、`Name` |
| 程序这边再加一道 | 连线字串 `ApplicationIntent=ReadOnly`、pyodbc `readonly=True`、检查数据库名字（`GPIS_EXPECTED_DATABASE=GPiS`）、查询逾时 5 秒；只有固定几条 `SELECT`，没有任意 SQL |
| 局域网连线 | 先确认 GPiS 的其他电脑是不是已经经局域网连主机的 SQL Server（H3）。如果是，就已经开了；如果不是，要在主机开 TCP/IP、设固定 port，防火墙**只开给系统电脑的 IP**。这要重开 SQL Server 服务，只能在下班后做 |
| 绝不 | 把 SQL Server 开到局域网以外（它已经没有安全更新） |

建帐号、改连线设定都是**主机上的改动**，D3 没有包含，所以要：

1. 先在开发电脑的 `GPiS_Dev` 上用同一个 script 试过（第 6 节）。
2. 诊所同意；GPiS 开发商知道（A5）。
3. 下班后做，做之前先 `COPY_ONLY` 备份。
4. 做了什么记在这个文件。

### 5.3 读不到 GPiS 的时候

- 空档、找病人、疗程医生：一律回"读不到 GPiS"，AI **转人工**，不用旧资料猜（D15）。
- 5b 提醒：读不到就不发，Admin Platform 提醒员工"今天的提醒没有发出去"。
- Admin Platform 上方显示"读不到 GPiS"，让员工知道。
- 日志只记"读不到"和原因，不记病人资料（D38）。

### 5.4 对主机的负担

- 每次查询都很小：一天一位医生大约 15 条，明天的提醒名单大约 30 条。
- 还不知道 `Tbl_CAH_Appointment` 有没有 `AppointmentDate` 的 index。先在 `GPiS_Dev` 查（第 6 节），没有的话也不能自己加：主机的表结构属于 GPiS（D5），只能问开发商。
- 同一个查询几秒内重复的话（例如 AI 一次对话问好几次），可以在程序里缓存几秒；不缓存超过一分钟（W26）。

## 6. 先在开发电脑上试（不碰主机）

下一个 session 写程序时做，全部只在 `GPiS_Dev`：

1. 写 `sql/create_readonly_login.sql`：建 `chatbot_reader`，只给第 5.2 节的栏位，`DENY Tbl_User`。数据库名字当参数，先给 `GPiS_Dev` 用。
2. 开发电脑的 `.env` 改用 `chatbot_reader` 连 `GPiS_Dev`（SQL 登录，不再用 Windows 登录），跑 10 个测试日期：结果要和现在一样。
3. 用 `chatbot_reader` 试：`INSERT`、`UPDATE`、读 `Tbl_User`、读 `NRIC` 都要被拒绝。
4. 在 `GPiS_Dev` 查 `Tbl_CAH_Appointment` 的 index 和查一天要多久（只看统计，不看资料）。
5. （选做）从家里另一台电脑经局域网连开发电脑的 SQL Server，练习"开 TCP/IP、防火墙只开给一个 IP"。

## 7. 要问诊所的问题（H = 主机，避免和 5b 的 W 编号重复）

| # | 问题 | 为什么要问 |
|---|---|---|
| H1 | 诊所可以放一台 24 小时开着的小电脑给本系统吗？还是只能用现有的电脑？ | 方案 1、2、3 都要一台 |
| H2 | 主机晚上、假期会关机吗？ | 主机关了就读不到 GPiS |
| H3 | GPiS 装在几台电脑？其他电脑的 `GPiS.exe.config` 里 `Database.Server` 写什么？（只看这一项，不看密码） | 判断 SQL Server 是不是已经接受局域网连线 |
| H4 | 诊所的网络、电力稳不稳？有没有 UPS？多久断一次？ | 系统电脑要 24 小时在线 |
| H5 | 诊所和 GPiS 开发商同意在主机上建一个只读帐号吗？谁有主机的管理员权限？ | 第 5.2 节要改主机（A5） |
| H6 | 员工需要在诊所外（例如用手机）看 Admin Platform 吗？ | 方案 1 只在诊所里看得到（A3） |
| H7 | GPiS 会更新版本吗？谁负责、多久一次？ | 表结构变了，本系统的查询要跟着改 |
| H8 | 诊所现在有备份 GPiS 吗？（主机上最后的备份是 2021 年） | 不是 A1 的范围，但主机坏了，GPiS 和本系统都会受影响 |

## 8. 决定草案（诊所回答后编进 `decisions.md`）

等 5b 的 PR 合并后再编号，避免两个 session 用到同一个 D 编号。

| 草案 | 决定 | 原因 |
|---|---|---|
| A1-1 | 正式上线先用**方案 1**：本系统放诊所里的一台电脑，在局域网直接读主机的 GPiS；以后需要放云端时改用方案 2（gateway），不用方案 3、4 | 最新、病人资料留在诊所、程序几乎不用改；方案 3 要整批复制病人资料，方案 4 要把没有安全更新的 SQL Server 开到网上 |
| A1-2 | 读 GPiS 只用 `chatbot_reader`：只给需要的表和栏位的 `SELECT`，`DENY Tbl_User`；SQL Server 不开到局域网以外 | 最少权限（D7）；就算程序有 bug 或帐号外泄，也改不了、读不到用不到的病人资料 |
| A1-3 | 主机上的设定改动（建帐号、开局域网连线）是 D3 的例外：先在 `GPiS_Dev` 试、诊所同意、下班后做、做之前 `COPY_ONLY` 备份、记录下来 | 主机是生产环境；改动要可以重做、可以追查 |
| A1-4 | 读不到 GPiS 时一律转人工、提醒不发，不用旧资料 | 宁可少推荐，也不要重复预约（D15） |

## 9. 对开发路线的影响（A1-1 定案后再改 `architecture.md`）

- Phase 7 "Docker → 云端"改成"装到诊所的系统电脑"；云端只用来跑假资料的测试（如果还需要）。
- Phase 8 "解决主机 ↔ 云端同步"不需要了，改成"评估是否写入 GPiS"。
- 5b 提醒：在系统电脑上，发之前直接读主机的明天名单。
- A8：直接读得到主机最新的预约，比较容易对上请求。
- 正式上线前要有：固定网址的 tunnel、系统电脑的备份、开机自动启动 Admin API、webhook、tunnel。

## 资料来源（第三方，上线前再对照官方文件）

- Meta webhook 失败会重送最多 7 天：[Hookdeck：Guide to WhatsApp webhooks](https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices)、[360dialog：Receiving messages via Webhook](https://docs.360dialog.com/partner/messaging/receiving-messages-via-webhook)
- SQL Server 2012 在 2022-07-12 停止支持：[Microsoft Learn：SQL Server 2012 end of support](https://learn.microsoft.com/en-us/lifecycle/announcements/sql-server-2012-windows-server-2012-2012-r2-end-of-support)
