# 定时执行模板（让自动日常真正无人值守）

本目录提供 macOS / Linux / Windows 三套现成配置，按你的系统选一套用即可。

## 先填 3 个占位符

所有模板里都有这些占位符，**使用前必须替换成你自己的真实路径**：

| 占位符 | 含义 | 怎么查 |
|---|---|---|
| `__PYTHON__` | Python 3 解释器路径 | macOS/Linux：终端执行 `which python3`；Windows：执行 `where python` |
| `__SKILL_DIR__` | 技能解压后的目录（内含 `scripts/auto_daily.py`） | 例：macOS `~/.workbuddy/skills/workbuddy-checkin-travel`；Windows `C:\Users\你\AppData\Roaming\...` |
| `__WORK_DIR__` | **放 `tokens.txt` 的目录**，也是脚本运行时的工作目录 | 建议单独建一个，如 `~/workbuddy-auto`（Windows `C:\Users\你\workbuddy-auto`） |

> 为什么要有 `__WORK_DIR__`：脚本从**当前工作目录**读 `tokens.txt`。
> 所以定时任务必须先切到放 `tokens.txt` 的目录再运行，否则会读不到 token。

替换完建议先**手动跑一次**确认无误：

```bash
cd __WORK_DIR__ && __PYTHON__ __SKILL_DIR__/scripts/auto_daily.py --query
```

## macOS —— launchd

1. 把 `macos/` 下两个 plist 拷到 `~/Library/LaunchAgents/`（替换好占位符）。
2. 加载（两种都行）：
   ```bash
   launchctl load ~/Library/LaunchAgents/com.workbuddy.checkin.morning.plist
   launchctl load ~/Library/LaunchAgents/com.workbuddy.checkin.afternoon.plist
   ```
   若报权限/沙箱问题，不用管——**下次登录时 launchd 会自动扫描该目录加载**。
3. 验证：`launchctl list | grep workbuddy`
4. 日志：`__WORK_DIR__/logs/morning.log` 与 `afternoon.log`

## Linux —— cron

1. 复制 `linux/crontab.example` 里的内容（替换占位符）。
2. `crontab -e` 打开编辑器，粘贴进去保存。
3. 验证：`crontab -l`
4. 日志同样写在 `__WORK_DIR__/logs/` 下。

> cron 依赖 `logs` 目录存在，先 `mkdir -p __WORK_DIR__/logs`。

## Windows —— 任务计划程序

1. 编辑 `windows/task-morning.xml` 与 `task-afternoon.xml`，替换占位符
   （路径里的反斜杠保持原样，例如 `C:\Users\你\workbuddy-auto`）。
2. 以**管理员或普通身份**打开命令提示符，导入：
   ```bat
   schtasks /create /tn "WorkBuddyCheckinMorning" /xml "task-morning.xml"
   schtasks /create /tn "WorkBuddyCheckinAfternoon" /xml "task-afternoon.xml"
   ```
3. 验证：`schtasks /query /tn WorkBuddyCheckinMorning`
4. 或在「任务计划程序」GUI 里导入：操作 → 导入任务。

> Windows 上模板的 `<Command>` 填 `__PYTHON__`（通常是 `python` 或完整 `C:\Python3x\python.exe`），
> `<Arguments>` 填脚本路径，`<WorkingDirectory>` 填放 `tokens.txt` 的目录。

## 通用前提（三系统都适用）

- **机器要开机且联网**。休眠时定时任务不会执行：
  - macOS：`sudo pmset -c sleep 0`（只改插电状态，`displaysleep` 不变，屏幕照常熄）
  - Windows：电源设置里把「睡眠」设为「从不」
  - Linux：根据发行版关闭自动挂起
- **时间可自行改**：早晨签到与下午领奖建议保留两次（喵旅行上午派出、下午才回，必须领两次）。
- **为什么用系统调度器而不是 WorkBuddy 内置 Automation**：
  系统调度器（launchd / cron / 任务计划程序）不依赖 App 常驻，实测比 App 内部调度更稳，
  后者存在偶发漏触发导致断签的情况。
- token 约 60 天过期，过期后任务会报 401 —— 重新取 token 覆盖 `tokens.txt` 即可，无需改调度配置。
