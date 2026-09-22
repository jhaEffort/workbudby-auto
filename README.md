# WorkBuddy 多账号自动日常（签到 + 喵旅行 + 连续登录 + 成长任务）

一个零依赖的 Python 脚本，自动完成 WorkBuddy 增长中心的每日例行：

- ✅ **每日签到**（积分）
- ✅ **喵旅行**：上午派猫出发、下午领奖（自动挑地点/时长）
- ✅ **连续登录对话打卡**：走网页端 WebChat 通道**新建真实会话并发生成式对话**，后端据此给「连续登录」+1
- ✅ **成长任务**：自动接受 + 查看进度 + 领取奖励（动态读取，不加新任务也不用改代码）
- ✅ **抽奖 / 连登兑换**（7d/14d/28d 档位）/ **补签卡**
- ✅ **多账号**：一个 token 列表批量处理，互不影响
- ✅ **日报推送**：跑完生成微信日报（Server酱 / PushPlus / 邮件）

纯 Python 标准库，**macOS / Windows / Linux / GitHub Actions 通用**。不读取、不内置任何人的登录态——账号信息只从你自己的 token 来。

---

## 方式一：部署到 GitHub Actions（推荐，免开机）

推到你自己的 GitHub（建议 **private**），即可每天自动跑，不依赖电脑开机。

### 1. 拿到你自己的 accessToken

脚本用 WorkBuddy 桌面端的 `accessToken` 调接口，**每个账号一个 token**。
token 在本地登录态文件里，**有效期 60 天**，过期重新取一次即可。

- **macOS**：`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/` 下的 `*.info`，取 `auth.accessToken`
- **Windows**：`%APPDATA%\CodeBuddyExtension\Data\Public\auth\*.info`
- **Linux**：`~/.config/CodeBuddyExtension/Data/Public/auth/*.info`

一行提取（macOS）：
```bash
python3 -c "import json,glob,os; p=glob.glob(os.path.expanduser('~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/*.info'))[0]; print(json.load(open(p))['auth']['accessToken'])"
```

> 先在桌面端正常登录一次，文件才会有。

### 2. 加 Secrets

仓库 → **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名 | 必填 | 说明 |
|---|---|---|
| `WB_TOKEN_1` / `WB_TOKEN_2` / `WB_TOKEN_3` | ✅ | 各账号的 accessToken，有几个加几个（`WB_TOKEN_4`…） |
| `SCT_SENDKEY` | ➖ | Server酱 sendkey，配了才会推微信日报 |
| `PUSHPLUS_TOKEN` | ➖ | PushPlus token，二选一即可 |

> 推送类的都是**可选**：不配就不推送，只写日志，不影响任务本身。

### 3. 开启 Actions

推送到 GitHub 后进 **Actions** 标签页；若有 "Workflows aren't being run…" 提示，点 **I understand my workflows, go ahead and enable them**。
建议先手动跑一次验证：Actions → `WorkBuddy Daily Checkin` → **Run workflow**。

### 4. 完成

每天北京时间 **09:30**（`--all`，全量）和 **14:00**（`--afternoon --chat`，领奖+补打卡）各跑一次。

### ⚠️ GitHub 方案的坑

- **token 绝对不能写进代码**，只能放 Secrets；push 到 public 仓库等于账号泄露。
- **token 60 天过期，且 CI 无法自己续期**：云端没有桌面端登录态，用 refresh_token 换新也被服务端拒绝（客户端是 confidential，需要内置密钥）。
  所以 CI 的 token 只能由装了桌面端的机器定期推送更新。
  好消息：工作流已内置 `--check-expiry=7` 体检步骤，token 剩不到 7 天会**让工作流失败**，GitHub 会给失败的定时任务**发邮件**——零配置到期提醒。
- **cron 会延迟**：高峰期可能晚 5–30 分钟，极偶尔跳过；签到不要求精确到秒，无妨。
- **仓库 60 天无活动，定时会自动停用**：偶尔去点一次 Run workflow 续命。
- **私有仓库免费额度 2000 分钟/月**，每次约 10–30 秒，够用。
- 真实对话会**少量消耗积分**（约 9 积分/次），但成长任务奖励（+100 起）远大于此。

---

## 方式二：本地 / 服务器定时跑

### 1. 准备 token

根目录建 `tokens.txt`（**已被 .gitignore 挡住**），格式见 `tokens.txt.example`：

```text
# WB_TOKEN_1 = 我的主账号
WB_TOKEN_1=粘贴你的accessToken

# WB_TOKEN_2 = 我的小号
WB_TOKEN_2=粘贴你的另一个accessToken
```

### 2. 跑

```bash
# 一次跑全（推荐）：签到 + 领旧奖 + 派猫 + 对话打卡 + 成长任务 + 抽奖 + 兑换
python3 scripts/auto_daily.py --all

# 下午领奖（猫回来了）+ 补一次对话打卡
python3 scripts/auto_daily.py --afternoon --chat

# 对话打卡 N 次（成长任务「和AI聊天5次」；注意消耗额度）
python3 scripts/auto_daily.py --chat=5

# 只查积分 / 查使用概况
python3 scripts/auto_daily.py --query
python3 scripts/auto_daily.py --usage

# 补签卡（连续登录断签兜底），不带日期=补今天
python3 scripts/auto_daily.py --makeup
python3 scripts/auto_daily.py --makeup=2026-09-20

# token 体检：<7 天则退出码 1（CI 告警用）
python3 scripts/auto_daily.py --check-expiry

# 只处理第 2 个账号 / 按尾号切换
python3 scripts/auto_daily.py --account 2 --all
python3 scripts/auto_daily.py --account 1234 --all
```

> Windows 上把 `python3` 换成 `python`。

### 3. 一键跑 + 推微信（推荐本机用）

`scripts/run_daily.sh` 是合并版单一入口：**按当前时间自动选模式**（<12 点跑 `--all`，≥12 点跑 `--afternoon --chat`），跑完自动生成日报并推送。

```bash
cd <放 tokens.txt 的目录> && bash <repo>/scripts/run_daily.sh

# 调试：只跑不推送
WB_NO_PUSH=1 bash <repo>/scripts/run_daily.sh
```

推送配置（**二选一，都不要写进仓库**）：

```bash
# A. 环境变量（推荐，CI 直接配 Secrets）
export SCT_SENDKEY=你的Server酱sendkey      # 或 PUSHPLUS_TOKEN=...

# B. 本机文件 scripts/.notify.json（已在 .gitignore 中）
{"wechat": {"enabled": true, "provider": "serverchan", "sendkey": "..."}}
```

### 4. 定时

`schedules/` 下备好 macOS / Linux / Windows 模板，替换 `__PYTHON__` / `__SCRIPT_DIR__` / `__WORK_DIR__` 占位符即可。
macOS 用的是**单任务双时段**（`com.workbuddy.daily.plist`，09:30 + 14:00 一个 job 搞定）。详见 `schedules/README.md`。

---

## 进阶：token 自动续期（仅本机）

`refresh_tokens.py` 思路（不在本仓库，需配合装了桌面端的机器）：

- accessToken **60 天**、refreshToken **90 天**，都不是长期凭证
- OAuth 刷新路子走不通（客户端需密钥），所以改为**定期把桌面端登录态里最新的 accessToken 同步出来**
- 再配合 `gh secret set` 推给 GitHub Secrets，CI 侧就永远不用手动管

---

## 安全须知

- `.gitignore` 已挡掉 `tokens.txt`、`*.info`、`.notify.json`、`auth_cache/`、日志等私密文件。**不要手动 `git add` 这些**。
- 脚本本身**不含任何账号、token、手机号、昵称或路径信息**，可放心分享给同事；每个人填自己的 token。
- 提交前建议自检：
  ```bash
  git ls-files | xargs grep -lE "/Users/|eyJ|1[3-9][0-9]{9}" || echo "干净"
  ```

### 🔒 提交前自动拦截（强烈建议开启）

仓库自带 `.githooks/pre-commit`，会在每次 commit 时自动扫描，**命中就拒绝提交**：

| 拦截项 | 例子 |
|---|---|
| JWT / accessToken | `eyJ...` 带点分段的長串 |
| 中国大陆手机号 | 1 开头的 11 位数字 |
| 真实家目录路径 | `/Users/<用户名>/`、`/home/<用户名>/` |
| Server酱 sendkey | `SCT...` 长串、`sendkey=xxx` |
| 敏感文件被提交 | `tokens.txt`、`*.info`、`.notify.json`、`refresh_store.json` |
| 你自己的账号尾号 | 从 `.githooks/privacy-tails.local` 读 |

启用（**每人 clone 后执行一次**）：

```bash
git config core.hooksPath .githooks
```

把自己的账号尾号填进 `.githooks/privacy-tails.local`（每行一个，3~4 位数字）——
该文件**不进仓库**（已 gitignore，且钩子本身也会拦它），所以不会泄露。

误报就在 `.githooks/privacy-allowlist` 加一行「文件路径:正则」豁免。
- 接口仅做签到 / 旅行 / 对话打卡 / 成长任务 / 抽奖 / 兑换 / 查积分，不碰资金、不删数据。

---

## 常见问题

- **401**：token 过期 → 重新取 accessToken，更新 Secret 或 `tokens.txt`。
- **某账号报错其他正常**：正常，脚本逐账号隔离；检查该账号 token 是否失效。
- **「连续登录」没涨**：确认当天跑过 `--chat`（它才会产生真实对话）。断签可用 `--makeup` 补签卡兜底。
- **抽奖提示无次数**：正常，当前账号没有抽奖次数，不是脚本问题。
- **`python3` 找不到（Windows）**：换成 `python`，或安装时勾选「Add Python to PATH」。
- **读不到 token**：确认运行时的「当前目录」下有 `tokens.txt`，或直接用环境变量 `WB_TOKEN_1=...`。
