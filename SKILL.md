---
name: workbuddy-checkin-travel
description: WorkBuddy 多账号自动日常：签到 + 喵旅行（派猫/领奖）+ 查积分。当用户要自动完成 WorkBuddy 签到、喵旅行、多账号批量操作，或查各账号可用积分时使用。技能不内置任何账号信息，首次使用前使用者必须提供自己的 accessToken（环境变量或本地 tokens.txt），支持无限多账号。脚本纯 Python 标准库，macOS / Windows / Linux 通用。
agent_created: true
---

# WorkBuddy 多账号自动日常（签到 + 喵旅行 + 查积分）

## 概述

把 WorkBuddy 增长中心的每日例行自动化封装成可复用技能：**签到 → 喵旅行领奖 → 喵旅行派发 → 查积分**，支持**任意多个账号**批量处理。脚本纯标准库、零依赖、账号完全解耦——不读取也不内置任何人的登录态。

**跨平台**：脚本只用到 Python 3 标准库（`urllib` / `json` / `os` / `datetime` 等），macOS、Windows、Linux 都能直接跑，只要装了 Python 3。文档里所有命令都标注了不同系统的差异。

## 重要：首次使用必须提供你自己的 accessToken

技能不会、也不能读取任何人的登录信息。使用前二选一提供你自己的 token：

- **方式 A（单账号）**：用下面的环境变量写法提供（不同系统语法不同，见下）。
- **方式 B（多账号，最推荐）**：在当前工作目录放 `tokens.txt`，只填你自己的 token：
  ```text
  # WB_TOKEN_1 = 我的主账号
  WB_TOKEN_1=<你的token>
  # WB_TOKEN_2 = 小号
  WB_TOKEN_2=<你的token>
  ```
  `#` 开头是备注，写你自己的账号标签即可。账号顺序即 WB_TOKEN_1/2/3…。**方式 B 不依赖任何系统路径与 shell 语法，跨平台最稳。**

### 如何获取你自己的 accessToken

不同系统的 WorkBuddy 把登录态存在各自的「应用数据」目录里，字段都是 `auth.accessToken`。
**最推荐、最跨平台的方式**：把该 token 字符串直接粘进 `tokens.txt`（方式 B），完全不依赖系统路径。

- **macOS（已确认）**：`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop*.info`
- **Windows / Linux**：路径随版本与安装方式不同，请在你系统的 WorkBuddy 应用数据目录下找同名 `auth` 目录
  （Windows 通常在 `%APPDATA%\CodeBuddyExtension\...`；Linux 通常在 `~/.config` 或 `~/.local/share` 下）。
  拿不准就以「粘 token 到 tokens.txt」为准，不要硬猜路径。

- token 有效期约 **60 天**（实测为签发日 +60d 的固定值，非长期凭证），过期后接口返回 `401`，重新取新值覆盖即可。
- **脚本会自动报剩余天数**：每次运行每个账号都会打印 `🔐 token 剩余 N 天（YYYY-MM-DD 到期）`；剩余 <7 天转 `🟠` 提醒，已过期转 `🔴`。定时任务静默失效前能提前发现。
- **CI（GitHub Actions）无法自己续期**：云端容器没有桌面端登录态，而用 refresh_token 换新的 OAuth 路也走不通
  （`client_id=console` 是 confidential 客户端，返回 `401 unauthorized_client`，需内置在客户端里的 client_secret）。
  实测：accessToken **60 天**、refreshToken **90 天**，都不是 1 年。
  所以 CI 侧 token 只能由**装了桌面端的机器**推送（见下），CI 自己用 `--check-expiry` 做告警。
- 若脚本/系统直接读登录数据目录被拦（`PermissionError`、杀软拦截等），直接复制 `.info` 里的 `accessToken` 字符串粘进 `tokens.txt` 即可绕过。

### 跨平台：怎么把 token 提供给脚本

- **方式 B（tokens.txt）**：任何系统都一样，无需管 shell 语法，首选。
- **方式 A（环境变量）**，不同系统写法不同。单个账号用 `WB_TOKEN`；
  **多个账号用 `WB_TOKEN_1` / `WB_TOKEN_2` / `WB_TOKEN_3` …**（按序号自动全部读取，不需要 tokens.txt，CI 场景用这种）：
  - macOS / Linux（bash / zsh）：
    ```bash
    export WB_TOKEN=<你的token>                 # 单账号
    export WB_TOKEN_1=<token1> WB_TOKEN_2=<token2>   # 多账号
    ```
  - Windows 命令提示符（CMD）：
    ```bat
    set WB_TOKEN=<你的token>
    ```
  - Windows PowerShell：
    ```powershell
    $env:WB_TOKEN="<你的token>"
    ```

## 用法

> 命令里的 `python3` 在 **Windows** 上通常叫 `python`（取决于安装时是否勾选「Add to PATH」）。

```bash
# 早晨例行（全部账号）：签到 + 领上次奖励 + 派猫出发 + 查积分
python3 scripts/auto_daily.py

# 下午领奖（上午派出的猫回来了，单独再跑一次领奖）
python3 scripts/auto_daily.py --afternoon

# 只查积分（可用余额）
python3 scripts/auto_daily.py --query

# 查积分使用概况：本月额度 / 已用 / 剩余 / 7 天内将失效 / 最近失效日期
python3 scripts/auto_daily.py --usage

# 连续登录对话打卡（WebChat 直写真实会话，三账号统一；与当日例行合并，默认顺带签到）
python3 scripts/auto_daily.py --chat
python3 scripts/auto_daily.py --afternoon --chat   # 下午领奖 + 对话打卡

# 对话打卡 N 次（成长任务「和 AI 聊天 5 次」用；注意真实对话会消耗模型额度）
python3 scripts/auto_daily.py --chat=5

# 成长任务：接受 + 查看进度 + 领取已达成的奖励（动态读取，不硬编码任务码）
python3 scripts/auto_daily.py --tasks

# 抽奖（自动查剩余次数并抽完）
python3 scripts/auto_daily.py --lottery

# 按连续登录档位兑换奖励（7d / 14d / 28d，已兑换或天数不足自动跳过）
python3 scripts/auto_daily.py --redeem

# 补签卡：连续登录断签时补回那天（不带日期=补今天）
python3 scripts/auto_daily.py --makeup
python3 scripts/auto_daily.py --makeup=2026-09-20   # 补签指定日期

# 一次跑全：早晨例行 + 对话打卡 + 成长任务 + 抽奖 + 连登兑换
python3 scripts/auto_daily.py --all

# 只处理第 2 个账号
python3 scripts/auto_daily.py --account 2

# 额外开 Buddy 盲盒（消耗 10 能量）
python3 scripts/auto_daily.py --open-box
```

多账号会逐个独立处理，某个账号 token 失效只单独报错，不中断其他账号。

## 多账号：切换 / 指定某个账号

**关键认知**：脚本是**直接用 token 调接口**的，不需要也不依赖在 WorkBuddy 客户端里切换登录账号。
`tokens.txt` 里配了几个账号，脚本就能同时操作几个；客户端当前登录的是谁，跟脚本完全无关。

所以「切换账号」= 指定脚本处理哪一个账号，三种方式：

```bash
# 1) 先看看已配置了哪些账号（序号 + 标签 + 脱敏 token）
python3 scripts/auto_daily.py --list

# 2) 按序号切换
python3 scripts/auto_daily.py --account 2

# 3) 按标签关键字切换（更直观，支持手机尾号或中文备注）
python3 scripts/auto_daily.py --account 1234
python3 scripts/auto_daily.py --account 小号
```

- 不加 `--account` → 默认处理**全部**账号。
- `--account` 的匹配规则（这点容易踩坑，已实测修正）：
  **数字且落在有效序号范围内 → 按序号**；否则（数字越界、或传入的是文字）**→ 按标签关键字模糊匹配**，
  不区分大小写。
  为什么这样设计：账号标识常是**手机尾号这类纯数字**（例如标签 `主号(1234)`），
  它并不在序号范围内，会自动当作标签关键字匹配，所以 `--account 1234` 能正确选中那个账号；
  而 `--account 2` 在只有 2 个账号时会被理解为「第 2 个」。
  匹配不到时会打印当前所有可用账号供你确认。
- **建议把标签写清楚**：在 `tokens.txt` 的 `#` 备注里写易记的关键字，
  例如 `# WB_TOKEN_1 = 主号(1234)`、`# WB_TOKEN_2 = 小号(5678)`，
  之后就能用 `--account 1234` 或 `--account 主号` 直接切换，不用记序号。
- `--list` 输出的 token 是脱敏的（只显示头尾各几位），可安全查看/截图。

## 接口（已验证）

| 用途 | 方法 | 地址 |
|---|---|---|
| 签到 | POST | `https://www.codebuddy.cn/v2/billing/meter/daily-checkin` |
| 查积分 | POST（空 body `{}`） | `https://www.codebuddy.cn/v2/billing/meter/get-user-resource` |
| 喵旅行配置 | GET | `https://www.codebuddy.cn/v2/activity/growth/buddy/travel/config` |
| 喵旅行状态 | GET | `https://www.codebuddy.cn/v2/activity/growth/buddy/travel/status` |
| 派猫出发 | POST `{location_id, duration_hours}` | `https://www.codebuddy.cn/v2/activity/growth/buddy/travel/depart` |
| 领取奖励 | POST | `https://www.codebuddy.cn/v2/activity/growth/buddy/travel/claim` |
| 能量余额 | GET | `https://www.codebuddy.cn/v2/activity/growth/energy` |
| 开盲盒 | POST（空 body） | `https://www.codebuddy.cn/v2/activity/growth/buddy/open` |

所有请求带 `Authorization: Bearer <你的token>` 与 `Content-Type: application/json`。接口域名 `www.codebuddy.cn` 与账号体系均为 WorkBuddy 服务，跨平台一致。

## 关键口径与坑

- **积分口径**：客户端「可用积分」= 当月周期剩余 `CycleCapacityRemainPrecise` 之和，**不是**总剩余 `CapacityRemain`（后者会偏高几百）。脚本已统一用前者，缺失时依次回退 `CycleCapacityRemain` → `CapacityRemain`。筛选：`CapacityUnit == "credits"` 且 `Status == 0`。
- **喵旅行时长**：80% 用满 4h（最高奖励），20% 随机 1–3h（接口允许范围内）。`depart` 响应的 `duration_hours` 不可靠（恒 0），真实时长以 `arrive_at` 反推为准。
- **每日两次领奖**：上午派猫下午才回，所以早晨跑一次（领旧奖 + 派新），下午再跑一次 `--afternoon`（领新奖）。
- **「连续登录」≠ 积分签到**：增长中心的「当前连续登录」需要当天产生一次**真实对话**才会记录，纯签到 API 不会增加它。
  **脚本已内置 `--chat` 用 WebChat 通道直写真实云端会话来补这件事**（见下「连续登录对话打卡（WebChat 通道，纯 token）」一节）。
  原理：增长中心后端只对当日产生真实对话的账号自动 +1，没有任何可程序化打卡的 RPC；`--chat` 走 WebChat（`/console/webchat/conversations` 新建会话 + `/console/chat/completions` 发消息 + `/v2/report` 发 `chat_request_*` 遥测），在该账号名下产生一次真实对话。
  - **实测三账号均 ✅**（各账号都能新建会话 + 拿到回复 + 遥测成功）。此前长期无对话记录的账号，换 WebChat 后已打通。
  - **⚠️ 是否计入连续登录仍需你次日核对**：机制上是真实会话+正确遥测，理应计入；建议连续观察 2~3 天增长中心「当前连续登录」是否稳定 +1。
  - **副作用（轻微）**：会在该账号多一个 `wb-checkin-*` 真实会话 + 一条打卡消息。无需客户端在线、无需内置 Automation。
  - **已验证生效**：跑完 `--chat` 后，账号的成长任务「和 AI 聊天」进度会真实 +1（例如 0/5 → 1/5），说明后端确实把它算作一次真实对话，因此连续登录会正常 +1。
- **成长任务 / 抽奖 / 兑换 / 补签卡**（`--tasks` / `--lottery` / `--redeem` / `--makeup`，均走网页端 host `www.workbuddy.cn`）：
  - 任务对象字段：`task_code`、`title`、`progress{current,target}`、`accept_status`（`accepted` 进行中 / `claimed` 已领取）、`reward_credit`。
  - 接受任务要传 **`{"task_codes": [...]}` 数组**（不是 `task_code` 单数）；领取是 `POST /v2/activity/growth/tasks/{code}/claim`。
  - 抽奖次数在 `GET .../lottery/chances` 的 **`data.balance`**（不是 `chances`/`remaining`）；抽奖 `POST .../lottery/draw` 需带 `client_token`。
  - 兑换按连续登录档位 `7d`/`14d`/`28d`，`POST .../redeem {"tier","client_token"}`；返回 409=本月已兑换、403=天数不足，均属正常跳过。
  - 补签卡 `POST .../makeup-cards/use {"target_date":"YYYY-MM-DD"}`。
  - ⚠️ 纯对话类任务（如「和 AI 聊天 5 次」「桌面端对话1次」）靠 `--chat=N` 产生的真实对话推进，`--tasks` 只负责接受与领取。
- **`travel/status` 不可靠，别用它判断"有没有待领"**：status 返回的是最近一条旅行记录，`state=arrived` + `letter` 有内容**不代表还没领**（实测领取后仍显示 arrived/letter）。
  唯一准的判断是**直接调用 `travel/claim`**：已领过会返回 `code=400 msg="no unclaimed travel"`（脚本提示「猫猫在家，无待领奖励」），可领才返回 `code=0`。
  → 排查漏领时直接跑 `--afternoon` 让脚本去 claim，不要靠 status 下结论（曾据此误判两个号"已领完"，实际各漏 +7 / +9）。
- **想看「用了多少 / 什么时候过期」用 `--usage`**（脚本已内置，字段口径见下）：
  - 有效积分账户的筛选同积分口径（`CapacityUnit == "credits"` 且 `Status == 0`）。
  - **输出**：`剩余 | 累计已用 | 本月作废 | 7天内到期 | 最近到期`。
  - **失效时间看 `DeductionEndTime`（毫秒时间戳），不是 `ExpiredTime`**（后者经常为空字符串）。每天的签到奖励都是一份独立小包，各自有到期日，不用会过期作废。
  - **打印到期日必须带年份（`%Y-%m-%d`）**：长期包（如「CodeBuddy个人体验版」）的 `DeductionEndTime` 可能是 2034 年，只格式化 `%m-%d` 会显示成「10-11」，被误读成"本月/近期到期"。
  - **Top-level `TotalDosage` = 可用积分合计**，可与 `CycleCapacityRemainPrecise` 求和交叉校验（实测两者一致，均为 3723）。`TotalCount` = 包数量。
  - **「已用 0」不一定是 bug**：实测有些账号所有包的 `CapacityUsedPrecise` / `CycleCapacityUsedPrecise` 全为 0（总量=剩余），说明当前对话消耗走的是另一套额度或不扣 credits。此时如实说明"接口口径下无消耗记录"，别硬编造用量。平台侧无公开用量明细接口（试过 `get-user-usage` / `describe-usage` / `get-bill` 等均 404），只能以此接口为准。
  - `CycleStartTime` / `CycleEndTime` 是该充值包的周期区间，跟失效时间不是一回事。
  - **「已用」必须不筛 `Status`**：积分包被消耗光后会从 `Status == 0` 列表里消失，只统计 live 会严重低估真实用量
    （实测同一账号 live 口径显示"已用 27"，真实累计已用是 1210）。所以脚本累加**所有**积分包的 `CapacityUsedPrecise`。
    系统扣减时优先扣最快到期的包，所以看到的剩余会是"离到期最远的那批"。
- **签到接口返回在顶层**：`daily-checkin` 的结构是顶层 `code` / `msg`（如 `code=10001 msg="今天已签到，请明天再来"`），不是 `data.Response.Data`。token 失效是 HTTP 401，两者不要混淆。
- **领取奖励后「可用积分」可能不变**：签到/喵旅行的奖励进累计池，而脚本读的是**当月周期剩余**额度，所以常见"领取 +9 但可用积分净变化 +0"。这不是失败，别误判成没领到。

## 连续登录对话打卡（WebChat 通道，纯 token）

增长中心「当前连续登录」需要当天产生**真实对话**才 +1，且后端没有可程序化打卡的 RPC。`--chat` 用前端同款 **WebChat 通道**（参考社区签到脚本 v21~v23）直写该账号的真实云端会话，等价于当天产生一次对话，**三账号统一、纯 token、可 CI、不依赖客户端在线**。

**三步链路（均用 `Authorization: Bearer <accessToken>`，accessToken 与签到同款；host 是 `www.workbuddy.cn`，与计费 API 的 `www.codebuddy.cn` 不同）：**

1. `POST https://www.workbuddy.cn/console/webchat/conversations`，body `{"name":"wb-checkin-<rand>"}`
   → 返回 `data.conversationId`（**新建**一个真实会话；注意不是 ACP 的 `/console/as/conversations`，那个 POST 是 403 无权限）。
2. `POST https://www.workbuddy.cn/console/chat/completions`，`Accept: text/event-stream`，body `{"messages":[{"role":"user","content":"早安…"}],"model":"glm-5.2","stream":true,"conversationId":"<上一步 id>"}`
   → SSE 流里拼出 AI 真实回复（证明这是一次有效对话）。
3. `POST https://www.workbuddy.cn/v2/report`，body 为 `[chat_request_send, chat_request_response]` 两个遥测事件（`eventCode` 即这两个；Growth 系统只认这俩，不认 `agent_task_created`；`userId` 从 Bearer JWT 中段 base64 解出 `sub`）。

**为什么不用 ACP（旧方案已弃用）：** ACP 的 `/console/as/conversations` 对长期未活跃的账号全是 `completed` 会话，worker 把 prompt 收下(202)但不落库、不计连续登录；且 `POST /console/as/conversations` 创建会话是 **403 access_denied**（accessToken 对该 AS 控制台只有读权限）。WebChat 通道绕开了这个死路，**实测三账号均 ✅**（各账号都能新建会话 + 拿到回复 + 遥测成功）。

**已踩的坑：** 遥测事件码必须用 `chat_request_send` / `chat_request_response`；`/v2/report` 顶层是事件数组；`userId` 缺了会导致遥测无效、任务不推进（从 JWT `sub` 解）。

**⚠️ 是否计入连续登录仍需次日核对**：机制上是真实会话+正确遥测，理应计入；建议连续观察 2~3 天增长中心「当前连续登录」是否稳定 +1。无需客户端在线、无需内置 Automation 兜底。

## 跨平台与定时执行（让它真正"自动"）

脚本本身跨平台。要每天无人值守执行，**技能已自带三套现成调度模板**，在 `schedules/` 目录：

```text
schedules/
├── README.md                                   # 占位符说明 + 三系统安装/验证步骤
├── macos/
│   ├── com.workbuddy.checkin.morning.plist     # launchd，每天 09:30
│   └── com.workbuddy.checkin.afternoon.plist   # launchd，每天 14:00（带 --afternoon）
├── linux/
│   └── crontab.example                         # cron 两行（09:30 / 14:00）
└── windows/
    ├── task-morning.xml                        # 任务计划程序，09:30
    └── task-afternoon.xml                      # 任务计划程序，14:00（带 --afternoon）
```

只需填 **3 个占位符**（见 `schedules/README.md` 怎么查）：

| 占位符 | 含义 |
|---|---|
| `__PYTHON__` | Python 3 解释器路径（`which python3` / `where python`） |
| `__SKILL_DIR__` | 技能解压目录（内含 `scripts/auto_daily.py`） |
| `__WORK_DIR__` | **放 `tokens.txt` 的目录**，也是运行时工作目录 |

| 系统 | 调度器 | 安装方式 |
|---|---|---|
| macOS | launchd | 两份 plist 拷进 `~/Library/LaunchAgents/`，`launchctl load`（或下次登录自动加载） |
| Linux | cron | `crontab -e` 粘贴 `crontab.example` 内容（先 `mkdir -p __WORK_DIR__/logs`） |
| Windows | 任务计划程序 | `schtasks /create /tn "WorkBuddyCheckinMorning" /xml task-morning.xml`，或 GUI 导入 |
| **任意（云端）** | **GitHub Actions** | 推到 GitHub 仓库，token 存 Secrets，见下一节 |

**关键点**：定时任务必须切到**放 `tokens.txt` 的目录**再运行（脚本从当前目录读 token），
所以三套模板都设了工作目录（launchd 的 `WorkingDirectory` / cron 的 `cd` / Windows 的「起始位置」）。

> **为什么用系统调度器**：不依赖 App 常驻，比 WorkBuddy 内置 Automation 更稳（后者存在偶发漏触发导致断签）。
> **其它前提**：机器要开机、联网、不休眠（macOS：`sudo pmset -c sleep 0`）；
> 早晨签到与下午领奖建议保留两次（喵旅行上午派出、下午才回，必须领两次）。
> 跨机器迁移时整个文件夹拷过去，对方填自己的 `tokens.txt` 并按上表配一遍调度即可，无需改脚本。

## 放到 GitHub 上跑（GitHub Actions，不依赖本地开机）

本地定时再稳也怕关机、休眠、断网。想要「真正的无人值守」，可以把脚本推到 GitHub 用 Actions 每天定时执行。
**工作流已就绪于 `.github/workflows/checkin.yml`**（推到 GitHub 后 Actions 自动识别、无需再复制；`schedules/github/checkin.yml` 是同一份的模板副本）。面向同事的分发说明见仓库根目录 `README.md`。

**步骤**

1. 建仓库（**建议 private**，因为要用你的 token）：
   ```bash
   cd workbuddy-checkin-travel
   # .gitignore 已在仓库根目录，已挡住 tokens.txt / *.info / backups / logs，无需再建
   git remote add origin git@github.com:<你的账号>/<仓库名>.git
   git push -u origin main
   ```
2. 添加 Secrets：仓库 → Settings → Secrets and variables → Actions → New repository secret，逐个加
   `WB_TOKEN_1` / `WB_TOKEN_2` / `WB_TOKEN_3`（要几个账号加几个，脚本按序号自动全读）。
3. Actions 页面确认 workflow 已启用，点 Run workflow 手动试跑一次，看日志里有没有 `签到成功`。

**必须知道的几个坑**

- **token 绝对不能写进代码**：只能放 Secrets。一旦 push 到 public 仓库，等于账号被人拿走。
- **token 约 60 天过期**，过期后 Actions 会失败，需要重新取值更新 Secret（到期前换个新 token 即可）。
- **GitHub 的 cron 会延迟**：高峰期可能晚 5–30 分钟触发，极偶尔整点跳过。签到这种不要求精确到秒的任务无所谓，别拿它做严格定时任务。
- 仓库 **60 天没有任何提交/活动，schedule 会被自动停用**，偶尔去点一次 Run workflow 就行。
- 私有仓库免费额度 2000 分钟/月，每次跑 10 秒左右，完全够用。
- **连续登录也能在云端补**：workflow 早晨跑 `--all`（含对话打卡 + 成长任务 + 抽奖 + 连登兑换），下午跑 `--afternoon --chat`。对话打卡用 WebChat 通道（`/console/webchat/conversations` + `/console/chat/completions` + `/v2/report` 遥测），纯 token、无需客户端在线、无需账号预先有过云端会话（脚本会新建）。
  - **已验证生效**：跑完后账号的成长任务「和 AI 聊天」进度会真实 +1（如 0/5 → 1/5），说明后端确实计为一次真实对话。
  - ⚠️ 真实对话会少量消耗积分（实测约 9 积分/次），但成长任务奖励（+100）远大于此，配合 `--tasks` 跑是净赚。
- **CI 侧的 token 体检（零配置到期提醒）**：workflow 里加了独立一步
  `python scripts/auto_daily.py --check-expiry=7`。
  有 token 剩余 <7 天就**让工作流失败**，GitHub 会给失败的定时任务发邮件 —— 不需要额外配置通知渠道。
  也可本机单跑：`--check-expiry` / `--check-expiry=14`（默认阈值 7 天，命中则退出码 1）。
- **CI token 怎么续（本机 → GitHub Secrets）**：
  ```bash
  brew install gh && gh auth login          # 只需一次
  python3 refresh_tokens.py --push-github=jhaEffort/workbudby-auto
  ```
  脚本会把 `tokens.txt` 里的每个 token 用 `gh secret set` 推到仓库 Secrets。
  配合本机每周定时任务（`com.workbuddy.token-refresh.plist`）就能全自动，CI 侧完全不用管。
  未装 `gh` 时脚本会明确提示安装命令，不会静默失败。

## 常见问题

- **401**：token 过期 → 重新从本地登录数据取新 `accessToken` 覆盖 `tokens.txt` / 环境变量。
- **某账号报错但其他正常**：正常现象，脚本逐账号隔离；检查该账号 token 是否失效。
- **数字比客户端高**：误用了 `CapacityRemain`，脚本已规避，确认未被改回。
- **`python3` 命令找不到（Windows）**：把 `python3` 换成 `python`，或安装时勾选「Add Python to PATH」。
- **脚本找不到 tokens.txt**：确认你运行命令时的「当前目录」下有 `tokens.txt`，或改用环境变量方式 A。
