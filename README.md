# WorkBuddy 多账号自动日常（签到 + 喵旅行 + 连续登录）

一个零依赖的 Python 脚本，帮你**自动完成 WorkBuddy 增长中心的每日例行**：

- ✅ **每日签到**（积分）
- ✅ **喵旅行**：上午派猫出发、下午领奖（自动挑地点/时长）
- ✅ **连续登录对话打卡**：用 ACP 协议直写云端会话，等价于当天产生一次真实对话（否则「连续登录」会断）
- ✅ **多账号**：一个 token 列表，批量处理，互不影响

脚本纯 Python 标准库，**macOS / Windows / Linux / GitHub Actions 通用**。不读取、不内置任何人的登录态——账号信息只从你自己的 token 来。

---

## 方式一：部署到 GitHub Actions（推荐，免开机）

把本仓库推到你的 GitHub（建议 **private** 仓库），即可每天自动跑，完全不依赖你的电脑开机。

### 1. 拿到你自己的 accessToken

脚本用 WorkBuddy 桌面端的 `accessToken` 调接口。**每个账号一个 token**（和脚本里的 `WB_TOKEN_1 / 2 / 3` 对应）。

token 在本地登录态文件里，约 **60 天有效**，过期重新取一次即可。

- **macOS**：`~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/` 下的 `*.info` 文件，取其中 `auth.accessToken` 字段。
  一行提取：
  ```bash
  python3 -c "import json,glob,os; p=glob.glob(os.path.expanduser('~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/*.info'))[0]; print(json.load(open(p))['auth']['accessToken'])"
  ```
- **Windows**：`%APPDATA%\CodeBuddyExtension\Data\Public\auth\*.info`，同样取 `auth.accessToken`。
- **Linux**：`~/.config/CodeBuddyExtension/Data/Public/auth/*.info`。

> 取之前先在 WorkBuddy 桌面端正常登录一次，文件才会有。

### 2. 把 token 加进仓库 Secrets

仓库页面 → **Settings → Secrets and variables → Actions → New repository secret**，逐个添加（名称必须完全匹配）：

| Secret 名 | 值 |
|---|---|
| `WB_TOKEN_1` | 第 1 个账号的 accessToken |
| `WB_TOKEN_2` | 第 2 个账号的 accessToken |
| `WB_TOKEN_3` | 第 3 个账号的 accessToken |

> 有几个账号就加几个，命名 `WB_TOKEN_4`、`WB_TOKEN_5`… 脚本会按序号自动全部读取。

### 3. 开启 Actions

- 推送到 GitHub 后，进仓库 **Actions** 标签页。
- 如果看到 "Workflows aren't being run on this fork" 之类的提示，点 **I understand my workflows, go ahead and enable them**。
- 首次建议手动跑一次验证：Actions → 选 `WorkBuddy Daily Checkin` → **Run workflow**。

### 4. 完成

工作流会每天北京时间 **09:30** 和 **14:00** 各跑一次（已带 `--chat`，顺带做对话打卡）。
看日志：Actions → 某次 run → 展开步骤，确认有 `签到成功` / `对话打卡已发往会话`。

### ⚠️ GitHub 方案的坑

- **token 绝对不能写进代码**，只能放 Secrets。一旦 push 到 public 仓库等于账号泄露。
- **token ~60 天过期**：过期后 Actions 会失败，重新取值并更新对应 Secret 即可。
- **cron 会延迟**：高峰期可能晚 5–30 分钟，极偶尔整点跳过——签到不要求精确到秒，无妨。
- **仓库 60 天无活动，定时会被自动停用**：偶尔去 Actions 点一次 Run workflow 即可续命。
- **私有仓库免费额度 2000 分钟/月**，每次跑约 10 秒，完全够用。
- **对话打卡需账号有过云端会话**：新号先在 WorkBuddy 客户端随便聊一句（让云端有会话），否则该账号的对话打卡会被跳过（签到/喵旅行不受影响）。是否计入「连续登录」以次日增长中心为准。

---

## 方式二：本地 / 服务器定时跑

适合不想用 GitHub、或想自己机器常开的情况。

### 1. 准备 token 文件

仓库根目录建 `tokens.txt`（**已被 .gitignore 挡住，不会误提交**），格式参考 `tokens.txt.example`：

```text
# WB_TOKEN_1 = 我的主账号
WB_TOKEN_1=粘贴你的accessToken

# WB_TOKEN_2 = 我的小号
WB_TOKEN_2=粘贴你的另一个accessToken
```

### 2. 跑

```bash
# 早晨例行（全部账号）：签到 + 领旧奖 + 派猫 + 查积分 + 对话打卡
python3 scripts/auto_daily.py --chat

# 下午领奖（上午派出的猫回来了）
python3 scripts/auto_daily.py --afternoon --chat

# 只查积分
python3 scripts/auto_daily.py --query

# 查积分使用概况（额度/已用/剩余/临近失效）
python3 scripts/auto_daily.py --usage

# 只处理第 2 个账号
python3 scripts/auto_daily.py --account 2 --chat
```

> Windows 上把 `python3` 换成 `python`。`--chat` 可与日常合并，默认顺带签到。

### 3. 定时（任选）

仓库 `schedules/` 下已备好 macOS（launchd）、Linux（cron）、Windows（任务计划程序）三套现成模板，替换里面的 `__PYTHON__` / `__SKILL_DIR__` / `__WORK_DIR__` 占位符即可。详见 `schedules/README.md`。

---

## 安全须知

- 本仓库的 `.gitignore` 已挡掉 `tokens.txt`、`*.info`、登录态缓存、日志等私密文件。**不要手动 `git add` 这些文件**。
- 脚本本身不含任何账号信息，可放心分享给同事；每个人填自己的 token（Secrets 或本地 `tokens.txt`）。
- 接口仅做签到 / 喵旅行 / 查积分 / 对话打卡，不碰资金、不删数据。

---

## 常见问题

- **401**：token 过期 → 重新取 accessToken，更新 Secret 或 `tokens.txt`。
- **某账号报错其他正常**：正常，脚本逐账号隔离；检查该账号 token 是否失效。
- **「连续登录」没涨**：确认该账号云端有会话（见上）；仍不涨则次日手动在客户端聊一句兜底。
- **`python3` 找不到（Windows）**：换成 `python`，或安装时勾选「Add Python to PATH」。
- **脚本读不到 token**：确认运行命令时的「当前目录」下有 `tokens.txt`，或改用环境变量 `WB_TOKEN_1=...` 直接传。
