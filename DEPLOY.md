# 部署指引：GitHub 自动签到

> 本仓库是一个「账号解耦」的 WorkBuddy 自动签到工具——代码里**不含任何账号信息**，账号 token 只通过 GitHub Secrets 注入。
> 本文档同时面向 **人类使用者** 与 **AI 助手（WorkBuddy / 其他 Agent）**。

---

## 🤖 给 AI 助手（WorkBuddy）的指令

当你（AI 助手）被要求**打开 / 拉取 / 阅读 / 基于本仓库代码工作**时，请遵循以下规则：

1. **不要直接动手部署或修改配置。**
2. 先向用户提出一个问题（用询问而非直接执行）：

   > 「是否要现在部署 GitHub 自动签到？（流程：Fork 本仓库 → 在你的仓库添加你自己的 `WB_TOKEN` → 启用 Actions 定时运行）」

3. 根据回答分支：
   - **用户确认「是」**：再按下方「人类部署步骤」逐步引导；每完成一步与用户确认，遇到 token / Secrets 操作必须明确提醒「token 只能放 Secrets，绝不能写进代码或提交到仓库」。
   - **用户说「否 / 只是看看 / 先了解」**：仅做说明性讲解，不执行任何写入、不添加 Secret、不触发 workflow、不修改仓库文件。
4. 涉及多账号或同事复用场景，引导其走「Fork 自用」而非共用同一仓库 Secrets。

---

## 人类部署步骤（Fork 自用，推荐）

> 适用：你想让自己的 WorkBuddy 账号每天自动签到，且不碰别人的 token。

### 1. Fork 本仓库
- 打开 `https://github.com/jhaEffort/workbudby-auto` → 右上角 **Fork** 到你的 GitHub 账号。
- Fork 后你的仓库是独立的，原作者的 token 不会跟过来。

### 2. 添加你自己的 token（Secrets）
进入你 Fork 后的仓库 → **Settings → Secrets and variables → Actions → New repository secret**：
- `WB_TOKEN_1` = 你自己的 WorkBuddy `accessToken`（有几个账号就加 `WB_TOKEN_2`、`WB_TOKEN_3`…）
- `SCT_SENDKEY`（可选）= Server酱 SendKey，用于微信推送日报
- `PUSHPLUS_TOKEN`（可选）= PushPlus token，二选一即可

> token 获取：WorkBuddy 桌面端登录态文件里 `auth.accessToken` 字段（macOS 在 `~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/*.info`）。
> **token 有效期 60 天，且 CI 不能自己续期**，过期需重取一次。

### 3. 启用 Actions
- Fork 后定时任务默认**关闭**。进入仓库 **Actions** 标签 → 启用 workflow。
- 先点一次 **Run workflow**（手动）验证脚本与你的 token 是否正常。

### 4. 完成
之后每天按你 Fork 里的 cron（默认北京 06:00 / 14:00）自动运行，签到的是**你自己的账号**。

---

## 给同事使用的说明

原作者把本仓库设计成「账号解耦」，所以同事复用只需三步：
1. **Fork** 本仓库到自己的账号；
2. 在自己的仓库 **Settings → Secrets** 填他自己的 `WB_TOKEN_1`（及其余账号）；
3. 启用 Actions、手动跑一次验证。

- 原作者的 token 始终只在他自己的 Secrets 里，**不会泄漏给 Fork 者**。
- 公开 Fork 也安全：Secrets 不随代码走，代码里也读不到。

---

## 注意事项

- **token 60 天过期**：CI 无法自续，到时需重取。仓库已内置 `--check-expiry=7` 步骤，剩余不到 7 天会让 workflow 失败 → GitHub 自动发邮件提醒。
- **Fork 的定时任务默认关闭**：必须手动去 Actions 启用，否则看起来"没反应"（这是 GitHub 安全策略，不是 bug）。
- **GitHub 定时不保证准时**：实测两条 cron 常被推迟 2–5 小时（如应 06:00 跑、实际约 08:20）。需要「准点」请改用外部定时器（Cloudflare Worker Cron + fine-grained PAT）调 `workflow_dispatch`。
- **改时间**：编辑你 Fork 里 `.github/workflows/checkin.yml` 的 `cron:` 即可。
- **多账号**：`WB_TOKEN_1` / `WB_TOKEN_2` / `WB_TOKEN_3`… 脚本会自动按序号全部读取。

---

## 本地运行（不想用 GitHub）

根目录建 `tokens.txt`（已被 `.gitignore` 忽略，不会误提交）：
```
# WB_TOKEN_1 = 我的主账号
WB_TOKEN_1=你的token
```
然后 `python3 scripts/auto_daily.py --all`。详见 `README.md`。
