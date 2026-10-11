# Frontend（Phase 4b：Admin Platform 网页）

员工用的网页：看 WhatsApp 对话、接手 / 交回 AI、确认预约请求、预约提醒的名单（Phase 5b）、改诊所设置、管理员工账号。
**画面是英文**（D24），资料全部来自 Phase 4a 的 `/api`（说明见 [`backend/README.md`](../backend/README.md)「Admin Platform 的 API」）。

React 19 + TypeScript + Vite。只多用了一个套件 React Router（网址 ↔ 画面）；没有 UI 套件（D30）。

## 文件

| 文件 | 内容 |
|---|---|
| `src/api.ts` | 调用后端 `/api` 的地方都在这里；错误变成一句英文；401 → 回登录画面 |
| `src/types.ts` | API 回传的资料长什么样子（= 后端的 Pydantic model） |
| `src/auth.tsx` | 谁登录了（问 `/api/auth/me`）；登录、登出 |
| `src/App.tsx` | 外框：上面的选单、各个页面的网址 |
| `src/hooks.ts` | `useLoad`（读资料、自动更新）、`useAction`（按钮做事情） |
| `src/format.ts` | 日期时间的显示（一律马来西亚时间） |
| `src/schedule.ts` | 排班送出前的检查（和数据库的 CHECK 一样，信息比较好懂） |
| `src/pages/` | 各个画面：登录、对话、预约请求、预约提醒、设置（`settings/`）、员工账号、我的账号 |
| `src/**/*.test.ts(x)` | 测试（Vitest），全部用假资料、假后端 |
| `vite.config.ts` | 开发用的网页服务器：`/api` 转给 FastAPI |
| `package.json`、`package-lock.json` | 套件和固定的版本（`npm ci` 照 lock 文件装，每台电脑装到的一模一样） |

## 画面

| 网址 | 谁能用 | 做什么 |
|---|---|---|
| `/conversations` | 所有员工 | 对话列表（Open / Needs staff / AI replying / Closed），每 15 秒更新 |
| `/conversations/12` | 所有员工 | 完整对话；**Take over**（AI 停止回复）、**Hand back to AI**、**Close**、经 WhatsApp 回复（Phase 5a） |
| `/requests` | 所有员工 | 预约请求；**Confirm**（先在 GPiS 录入，可以填 GPiS AppointmentID）、**Reject**、**Patient cancelled** |
| `/reminders` | 所有员工 | 预约提醒的名单（Phase 5b）：*Ready* / *Needs staff* / *Not appointments*；**Open in WhatsApp**（消息已经填好，员工按 Enter，D54；按过会记下来，别的员工也看得到，D58）；*Mark as not sent*；*Copy message*；**NO WA**（这个号码不要提醒，D55）。每次 *Refresh* 都重新读 GPiS |
| `/settings/...` | 看：所有员工；改：**ADMIN** | 医生和排班、疗程、假期（一键导入公共假期）、医生请假、每格上限 |
| `/staff` | **ADMIN** | 员工账号：新增、改权限、停用、重设密码 |
| `/account` | 所有员工 | 改自己的密码 |

- 选单上的红色数字：要员工处理的对话（`HUMAN`）、待确认的请求（`PENDING`），每 30 秒更新。
- 回复病人（Phase 5a）：对话下面的 *Reply on WhatsApp*，`Ctrl + Enter` 也能送出。病人最后一条消息 24 小时之后不能回（WhatsApp 的规定），画面会说明。
  发出的消息下面显示送到哪一步：*Sending…* / *Sent* / *Delivered* / *Read* / *Not delivered*（红字是原因）。设定 WhatsApp 的步骤见 [`backend/README.md`](../backend/README.md)「Phase 5a」。
- STAFF 看不到修改的按钮，但**真正挡住的是后端**（STAFF 直接呼叫 API 会得到 403）。

## 在开发电脑上安装（Windows，只做一次）

需要 **Node.js 22.13 或以上**（`node --version` 确认）。在仓库的 `frontend` 文件夹里：

```powershell
cd <仓库位置>\frontend
npm ci
```

`npm ci` 会照 `package-lock.json` 装套件到 `frontend\node_modules\`（不进仓库）。最后应该显示 `found 0 vulnerabilities`。
PowerShell 说不能执行 `npm.ps1` 的话，跟 Phase 2 一样先跑 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`。

## 使用

要开**两个** PowerShell 视窗：

```powershell
# 视窗 1：后端（和 Phase 4a 一样）
cd <仓库位置>\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# 视窗 2：网页
cd <仓库位置>\frontend
npm run dev
```

浏览器打开 <http://localhost:5173>，用 Phase 4a 建的账号登录。

- 网页在 `localhost:5173`，后端在 `127.0.0.1:8000`。浏览器只跟 5173 说话，`/api/...` 由 Vite 转给后端（`vite.config.ts` 的 `proxy`）。
  这样浏览器看到的是同一个网址，`SameSite=Strict` 的登录 cookie 才会被带上，后端也不用开 CORS（D29）。
- 只在自己电脑上用：**不要**加 `--host`（`vite.config.ts` 固定只听 `localhost`）。
- 改了 `src/` 里的文件，浏览器会自动更新，不用重开。
- 画面显示 *The server is not responding. Is the backend (uvicorn) running?*：视窗 1 没开或出错了。
- 想要重新开始（假资料改乱了）：见下面「重设假资料」。

## 测试

```powershell
npm test            # Vitest：44 个测试，假后端、假资料，不需要开 uvicorn
npm run build       # TypeScript 检查 + 打包到 dist\（不进仓库）
```

`npm run build` 先跑 `tsc`：栏位名字打错、少处理 `null` 时会在这里失败。

## Phase 4b 完成的条件（在开发电脑上测试）

1. `node --version` → v22.13 或以上；`npm ci` → `found 0 vulnerabilities`。
2. `npm test` → **31 passed**；`npm run build` → `✓ built`，没有错误。
3. 后端 `pytest` 还是 **131 passed**（4b 在后端只改了 `seed.py` 的疗程代码）。
4. 补上新的疗程代码（2026-10-06，W28–W30）：在 `backend` 跑 `python -m app.db.seed` → `services: 新增 2 行`（`ISSUE CROWN`、`ISSUE BRIDGE`）。
   `SC`、`SCAN B` 已经在数据库里，`seed` 不会改它们，所以在清单第 7 项用网页改。
5. 开两个视窗，照下面的清单在浏览器上点一次（`chatbot_dev` 的假资料，先跑过 `python -m app.db.demo`）：

| # | 做什么 | 应该看到 |
|---|---|---|
| 1 | 打开 <http://localhost:5173/requests>，密码故意打错 | 红字 *Wrong username or password*，密码栏清空 |
| 2 | 用 ADMIN 账号登录 | 直接到 *Appointment requests*；Demo Kid A、Demo Kid B 互相显示 *Together with* |
| 3 | Demo Kid A → **Confirm** → 填 `123456` → *Entered in GPiS – confirm* | 从 Pending 消失；*Confirmed* 分页看得到 `GPiS AppointmentID 123456` |
| 4 | *Conversations* → Demo Mum → **Take over** | 黄色横条 *Staff is handling this conversation (你的名字)*；选单 Conversations 的数字 +1 |
| 5 | **Hand back to AI** | 回到 *The AI is replying …* |
| 6 | *Settings → Doctors & schedules*：星期六 *Last slot* 选比 *Start* 早的时间 | 红字说明哪里错，*Save schedule* 不能按；改回来 → *Saved.* |
| 7 | *Treatments* → `C/UP` → Edit → 改名字 → Save；`SC` → Edit → *Group* 选 `CROWN` → Save；`SCAN B` → *Group* 选 `BRIDGE` | 名字更新（代码里有 `/` 也没问题）；`SC`、`ISSUE CROWN` 都是 `CROWN`，`SCAN B`、`ISSUE BRIDGE` 都是 `BRIDGE` |
| 8 | *Clinic closures* → **Import public holidays for 2026** | *Added 11 day(s)*（诊所休的那几种，D61；已经导入过的话：*Added 0 day(s); 11 were already there*） |
| 9 | 加一个已经有的日子（例 2026-02-17） | *This date is already a closure day.* |
| 10 | *Staff accounts* → 加一个 STAFF 账号 → 登出 → 用它登录 | 看不到 *Staff accounts*；*Settings* 显示 *Only an admin can change them*，没有 Edit 按钮 |
| 11 | 用另一个浏览器（或无痕视窗）以 ADMIN 登录，停用那个 STAFF；回到 STAFF 的视窗点 *Requests* | 马上回到登录画面 |
| 12 | 把浏览器视窗拉窄（像手机） | 选单换行，对话列表 / 对话内容分开显示，不会挤在一起 |

测完把结果记在下面「测试记录」，再开 PR。截图如果用的是 `chatbot_dev` 的假资料，可以直接贴回来。

### 重设假资料

`chatbot_dev` 的假资料被改乱了，想从头再测一次：在 SQL Shell (psql) 用 `postgres` 登录，

```sql
DROP DATABASE chatbot_dev WITH (FORCE);
CREATE DATABASE chatbot_dev OWNER chatbot;
```

再到 `backend` 跑 `alembic upgrade head` → `python -m app.db.seed` → `python -m app.db.create_staff …` → `python -m app.db.demo`。
**只对 `chatbot_dev` 做**，它里面只有假资料。

## 上线

`npm run build` 产生的 `dist\` 是普通的 HTML / JS / CSS 文件，要和 `/api` 放在**同一个网址**下，cookie 才会带上。

- **5b 试跑（电脑 B）**：FastAPI 同时提供 `dist\`，只听 `127.0.0.1`，用 `http://localhost:8000`（D62，步骤见 [`docs/deploy-pc-b.md`](../docs/deploy-pc-b.md)）。
- **以后放到网络上（Phase 7）**：要用 https 并把 `COOKIE_SECURE=true`。

开发时照旧用 `npm run dev`。

## 测试记录

云端容器（2026-10-06，Node 22.22 和 **22.13.0** 各跑一次，PostgreSQL 16，只用假资料）：

- `npm ci` → 133 个套件，`found 0 vulnerabilities`；每个套件的 `engines` 都接受 Node 22.13。
- `npm test` → 31 passed；`npm run build` → 成功（JS 约 93 kB gzip）。
- 后端 `pytest` → 131 passed（后端只改了 `seed.py` 的疗程代码）。
- 补上 `ISSUE CROWN`、`ISSUE BRIDGE` 后：模拟旧的 `chatbot_dev`（24 个疗程）再跑 `seed` → `services: 新增 2 行`；在网页把 `SC`、`SCAN B` 的 *Group* 改成 `CROWN`、`BRIDGE`，重新整理后还在。
- 用 headless Chromium 连 `npm run dev` + `uvicorn` + `chatbot_dev`（seed + demo 假资料）点过上面清单 1–12，全部正常，浏览器 console 没有 React 警告。

开发电脑（2026-10-06，Windows、Node.js v22.13.0、PostgreSQL 18，`chatbot_dev` 的假资料）：

- 「Phase 4b 完成的条件」1–5 全部通过：`npm ci`、`npm test`、`npm run build`、后端 `pytest`、`seed` 补上 2 个疗程代码。
- 测试清单 1–12 项全部正常（包括 `SC`、`SCAN B` 的 *Group* 改成 `CROWN`、`BRIDGE`）。

结论：Phase 4b 完成。

### 公共假期只导入诊所休的日子（D61，2026-10-12，开发电脑）

- `pytest` 300 passed、`npm test` 44 passed。
- 先在 `chatbot_dev` 删掉以前导入的 24 天（Phase 4a 的 23 天 + 测试加的 1 天）。
- *Import public holidays for 2026* → *Added 11 day(s)*：1 月 1 日 + 诊所给的 10 天，没有替代假（3 月 24 日、11 月 9 日）。
- *Import public holidays for 2027* → *Added 11 day(s)*：和诊所的名单一样（Deepavali 10 月 28 日：诊所漏写了，W59）。
- 加 `2026-09-02 Test closure`：`python -m app.cli 2026-09-02 PHANG S+P` → `CLINIC_CLOSED`；`python -m app.reminders_cli 2026-09-02` → Ready 0，25 个预约在 *Needs staff*（*Clinic is closed that day (Test closure)*）；删掉之后变回 `OK`（W56）。
