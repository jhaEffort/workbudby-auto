#!/usr/bin/python3
"""WorkBuddy 积分日报生成器（合并版）。

现在只服务一条链路：auto_daily.py → 本脚本 → notify.py（微信/邮件）。
老的 checkin.py / cat_travel.py 格式仍兼容解析，以防历史日志回溯。

用法：
  python3 report.py <logfile>          # 解析日志并推送
  python3 report.py -                  # 从 stdin 读
  python3 report.py <logfile> --no-push   # 只渲染不推送（调试用）
  环境变量 WB_NO_PUSH=1 同样可关闭推送

排版铁律：微信/Server酱 把单个 \\n 当空格，**只有空行 \\n\\n 才分段**。
所以每个区块标题前、每个账号条目之间，都必须插入空行。
"""
import re
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import notify


# ────────────────────────── 解析 ──────────────────────────
def _ensure(accounts, label):
    if label not in accounts:
        accounts[label] = {"checkin": {}, "travel": {}, "chat": {},
                           "tasks": {}, "lottery": {}, "redeem": {}, "token": {}}
    return accounts[label]


def _parse_new(log_text: str) -> dict:
    """解析 auto_daily.py 的输出（新链路主格式）。"""
    accounts = {}
    cur = None
    # 账号分隔行形如：── 昵称(尾号) ──  或  ── [1/3] 昵称(尾号) ──（尾号是 3~4 位数字）
    acct_re = re.compile(r"──\s*(?:\[\d+/\d+\]\s*)?(.+?)──")
    label_ok = re.compile(r"\(\d{3,4}\)")

    streak_re = re.compile(r"🔥\s*连续登录\s*(\d+)\s*天")
    before_re = re.compile(r"执行前积分:\s*([\d.]+)")
    after_re = re.compile(r"执行后积分:\s*([\d.]+)\s*\(本次净变化\s*([+-]?[\d.]+)\)")
    ck_ok_re = re.compile(r"✅\s*签到成功\s*\+(\d+)\s*积分")
    token_re = re.compile(r"(🔐|🟠|🔴)\s*token\s*剩余\s*([-]?\d+)\s*天")
    chat_re = re.compile(r"对话打卡完成:\s*(\d+)/(\d+)")
    tasks_re = re.compile(r"📋\s*本轮领取\s*(\d+)\s*个任务奖励")
    task_acc_re = re.compile(r"📋\s*接受任务\s*(\d+)\s*个")
    lottery_none_re = re.compile(r"🎰\s*无抽奖次数")
    lottery_hit_re = re.compile(r"🎰\s*第\s*(\d+)\s*抽")
    redeem_days_re = re.compile(r"🎁\s*连续登录\s*(\d+)\s*天")
    redeem_ok_re = re.compile(r"🎁\s*兑换\s*(\w+)\s*成功")
    redeem_skip_re = re.compile(r"🎁\s*档位\s*(\w+)\s*需\s*(\d+)\s*天")
    redeem_done_re = re.compile(r"🎁\s*兑换\s*(\w+).*?已兑换")

    for line in log_text.splitlines():
        line = line.strip()
        m = acct_re.search(line)
        if m and label_ok.search(m.group(1)):
            cur = m.group(1).strip()
            _ensure(accounts, cur)
            continue
        if cur is None:
            continue
        acc = accounts[cur]

        r = streak_re.search(line)
        if r:
            acc["checkin"]["streak"] = int(r.group(1)); continue
        r = before_re.search(line)
        if r:
            acc["checkin"]["before"] = float(r.group(1)); continue
        r = after_re.search(line)
        if r:
            acc["checkin"]["after"] = float(r.group(1))
            acc["checkin"]["net"] = float(r.group(2)); continue
        r = ck_ok_re.search(line)
        if r:
            acc["checkin"]["result"] = f"✅ +{r.group(1)}"; continue
        if "今天已签到过" in line:
            acc["checkin"]["setdefault_result"] = True
            acc["checkin"]["result"] = "📌 已签到"; continue
        if "签到结果" in line:
            acc["checkin"]["result"] = "⚠️ 见日志"; continue

        r = token_re.search(line)
        if r:
            acc["token"]["mark"] = r.group(1)
            acc["token"]["days"] = int(r.group(2)); continue

        r = chat_re.search(line)
        if r:
            acc["chat"]["done"] = int(r.group(1)); acc["chat"]["total"] = int(r.group(2)); continue

        r = tasks_re.search(line)
        if r:
            acc["tasks"]["claimed"] = int(r.group(1)); continue
        r = task_acc_re.search(line)
        if r:
            acc["tasks"]["accepted"] = int(r.group(1)); continue

        if lottery_none_re.search(line):
            acc["lottery"]["count"] = 0; continue
        r = lottery_hit_re.search(line)
        if r:
            acc["lottery"]["count"] = max(acc["lottery"].get("count", 0), int(r.group(1))); continue

        r = redeem_days_re.search(line)
        if r:
            acc["redeem"]["days"] = int(r.group(1)); continue
        r = redeem_ok_re.search(line)
        if r:
            acc["redeem"].setdefault("ok", []).append(r.group(1)); continue
        r = redeem_done_re.search(line)
        if r:
            acc["redeem"].setdefault("dup", []).append(r.group(1)); continue
        r = redeem_skip_re.search(line)
        if r:
            acc["redeem"].setdefault("skip", []).append(f"{r.group(1)}(需{r.group(2)}天)"); continue

        # 喵旅行细节
        if "✅ 领取成功" in line and "积分" in line:
            g = re.search(r"\+(\d+)\s*积分", line)
            acc["travel"]["claimed"] = True
            if g:
                acc["travel"]["claim_reward"] = int(g.group(1))
            continue
        if "派发成功" in line:
            g = re.search(r"奖励\s*(\d+)\s*积分", line)
            if g:
                acc["travel"]["departed"] = True
                acc["travel"]["reward"] = int(g.group(1))
            continue
        if "猫猫旅行中" in line or "无法派发" in line:
            acc["travel"]["traveling"] = True; continue
        if "今日旅行次数已用完" in line:
            acc["travel"]["limit"] = True; continue
        if "猫猫在家" in line or "无待领奖励" in line:
            acc["travel"]["idle"] = True; continue

    return accounts


def _parse_old(log_text: str) -> dict:
    """解析老的 checkin.py / cat_travel.py 输出（兼容保留）。"""
    accounts = {}
    section, cur = None, None
    acct_re = re.compile(r"──\s*(?:\[\d+/\d+\]\s*)?(.+?)──")
    before_re = re.compile(r"(?:签到前|执行前)积分:\s*([\d.]+)")
    after_re = re.compile(r"(?:签到后|执行后)积分:\s*([\d.]+)\s*\(本次净变化\s*([+-]?[\d.]+)\)")
    success_re = re.compile(r"✅\s*签到成功!.*?\+(\d+)\s*积分")
    claim_re = re.compile(r"✅\s*领取成功!.*?\+(\d+)\s*积分")
    streak_re = re.compile(r"🔥\s*连续登录\s*(\d+)\s*天")
    travel_re = re.compile(r"旅行中:\s*(.+?)\s+(\d+)h\s+奖励\s*(\d+)积分")
    arrive_re = re.compile(r"预计\s*(\d{1,2}:\d{2})\s*回来")

    for line in log_text.splitlines():
        line = line.strip()
        if "每日签到（多账号）" in line:
            section, cur = "checkin", None; continue
        if "喵旅行（多账号）" in line:
            section, cur = "travel", None; continue
        m = acct_re.search(line)
        if m and re.search(r"\(\d{3,4}\)", m.group(1)):
            cur = m.group(1).strip()
            _ensure(accounts, cur)
            continue
        if cur is None or section is None:
            continue
        acc = accounts[cur]
        r = before_re.search(line)
        if r:
            acc["checkin"]["before"] = float(r.group(1)); continue
        r = after_re.search(line)
        if r:
            acc["checkin"]["after"] = float(r.group(1))
            acc["checkin"]["net"] = float(r.group(2)); continue
        r = success_re.search(line)
        if r and section == "checkin":
            acc["checkin"]["result"] = f"✅ +{r.group(1)}"; continue
        if "今天已经签到过了" in line and section == "checkin":
            acc["checkin"]["result"] = "📌 已签到"; continue
        r = streak_re.search(line)
        if r and section == "checkin":
            acc["checkin"]["streak"] = int(r.group(1)); continue
        if section == "travel":
            r = claim_re.search(line)
            if r:
                acc["travel"]["claim_reward"] = int(r.group(1)); acc["travel"]["claimed"] = True
            if "✅ 领取成功" in line:
                acc["travel"]["claimed"] = True
            r = travel_re.search(line)
            if r:
                acc["travel"]["loc"] = r.group(1).strip(); acc["travel"]["reward"] = int(r.group(3))
            r = arrive_re.search(line)
            if r:
                acc["travel"]["arrive"] = r.group(1)
            if "今日旅行次数已用完" in line:
                acc["travel"]["limit"] = True
            if "猫猫没在旅行，无需领取" in line:
                acc["travel"]["idle"] = True
    return accounts


def _parse(log_text: str) -> dict:
    """优先按新格式解析，解析不到账号再回退老格式。"""
    accounts = _parse_new(log_text)
    if not any(accounts[k].get("checkin") for k in accounts):
        old = _parse_old(log_text)
        if old:
            for k, v in old.items():
                if any(v.get(s) for s in ("checkin", "travel")):
                    accounts.setdefault(k, v)
                    for s in ("checkin", "travel"):
                        accounts[k][s].update(v.get(s, {}))
    return accounts


# ────────────────────────── 渲染 ──────────────────────────
def _fmt_bal(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f.is_integer() else f"{f:.1f}"


def _travel_desc(t: dict) -> str:
    if t.get("departed") and t.get("reward") is not None:
        return f"已派发 · 奖励 {t['reward']} 积分"
    if t.get("claimed"):
        base = "✅ 已领取礼物"
        if t.get("claim_reward") is not None:
            base += f" (+{t['claim_reward']})"
        return base
    if t.get("traveling"):
        return "🐱 旅行中"
    if t.get("limit"):
        return "今日旅行次数已用完"
    if t.get("idle"):
        return "无待领奖励"
    if t.get("loc"):
        return f"{t['loc']} 旅行中"
    return None


def _redeem_desc(r: dict) -> str:
    parts = []
    if r.get("ok"):
        parts.append("兑换成功 " + "/".join(r["ok"]))
    if r.get("dup"):
        parts.append("本月已兑换 " + "/".join(r["dup"]))
    if r.get("skip"):
        parts.append("未达 " + "/".join(r["skip"]))
    if r.get("days") is not None and not parts:
        parts.append(f"连登 {r['days']} 天")
    return " · ".join(parts) if parts else None


def _render(accounts: dict) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"📋 WorkBuddy 积分日报", f"🕐 {now}", ""]

    # 1) 每日签到（含连续登录天数 + 余额）
    rows = [(l, a.get("checkin", {})) for l, a in accounts.items()
            if a.get("checkin", {}).get("after") is not None
            or a.get("checkin", {}).get("result")
            or a.get("checkin", {}).get("streak") is not None]
    if rows:
        lines.append("【每日签到】")
        total = 0
        for label, c in rows:
            lines.append("")           # 空行：微信只有 \n\n 才分段
            res = c.get("result", "📌 已签到")
            after = c.get("after")
            bal = f"· 余额 {_fmt_bal(after)}" if after is not None else ""
            streak = c.get("streak")
            streak_s = f"🔥连续{streak}天 " if streak is not None else ""
            net = c.get("net")
            net_s = f" ({'+' if net >= 0 else ''}{_fmt_bal(net)})" if net else ""
            lines.append(f"• {label}：{streak_s}{res}{net_s} {bal}".strip())
            if after is not None:
                total += after
        lines.append("")
        lines.append(f"💰 合计可用积分：{_fmt_bal(total)}")
        lines.append("")

    # 2) 喵旅行
    rows = [(l, a.get("travel", {})) for l, a in accounts.items() if a.get("travel")]
    descs = [(l, _travel_desc(t)) for l, t in rows]
    descs = [(l, d) for l, d in descs if d]
    if descs:
        lines.append("【喵旅行】")
        for label, d in descs:
            lines.append("")
            lines.append(f"• {label}：{d}")
        lines.append("")

    # 3) 连续登录打卡
    rows = [(l, a.get("chat", {})) for l, a in accounts.items() if a.get("chat")]
    if rows:
        lines.append("【连续登录打卡】")
        for label, c in rows:
            lines.append("")
            ok = c.get("done", 0) == c.get("total", 0) and c.get("total", 0) > 0
            lines.append(f"• {label}：{'✅' if ok else '⚠️'} 对话打卡 {c.get('done', 0)}/{c.get('total', 0)}（真实对话已记录）")
        lines.append("")

    # 4) 成长任务
    rows = [(l, a.get("tasks", {})) for l, a in accounts.items() if a.get("tasks")]
    if rows:
        lines.append("【成长任务】")
        for label, t in rows:
            lines.append("")
            got = t.get("claimed", 0)
            acc_n = t.get("accepted")
            acc_s = f"接受 {acc_n} 个 · " if acc_n else ""
            lines.append(f"• {label}：{acc_s}本轮领取 {got} 个奖励")
        lines.append("")

    # 5) 抽奖
    rows = [(l, a.get("lottery", {})) for l, a in accounts.items() if a.get("lottery")]
    if rows:
        lines.append("【抽奖】")
        for label, lo in rows:
            lines.append("")
            n = lo.get("count", 0)
            lines.append(f"• {label}：{'🎰 已抽 ' + str(n) + ' 次' if n else '🎰 无抽奖次数'}")
        lines.append("")

    # 6) 连登兑换
    rows = [(l, a.get("redeem", {})) for l, a in accounts.items() if a.get("redeem")]
    descs = [(l, _redeem_desc(r)) for l, r in rows]
    descs = [(l, d) for l, d in descs if d]
    if descs:
        lines.append("【连登兑换】")
        for label, d in descs:
            lines.append("")
            lines.append(f"• {label}：🎁 {d}")
        lines.append("")

    # 7) Token 有效期
    rows = [(l, a.get("token", {})) for l, a in accounts.items() if a.get("token")]
    if rows:
        lines.append("【Token 有效期】")
        warn = 0
        for label, t in rows:
            lines.append("")
            d, mark = t.get("days", 0), t.get("mark", "🔐")
            if mark == "🔴" or d < 7:
                warn += 1
            lines.append(f"• {label}：剩余 {d} 天 {mark}")
        if warn:
            lines.append("")
            lines.append(f"⚠️ {warn} 个账号 token 临近过期，请运行 refresh_tokens.py 更新")

    # 去掉尾部多余空行
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


# ────────────────────────── 入口 ──────────────────────────
def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("-") or a == "-"]
    no_push = ("--no-push" in sys.argv) or os.environ.get("WB_NO_PUSH") == "1"

    if len(argv) < 1 or argv[0] in ("-", ""):
        log_text = sys.stdin.read()
    else:
        log_text = Path(argv[0]).read_text(encoding="utf-8", errors="replace")

    accounts = _parse(log_text)
    if not accounts:
        print("（本次运行未解析到账号数据）")
        if not no_push:
            notify("WorkBuddy 积分日报", "（本次运行未解析到账号数据）")
        return

    report = _render(accounts)
    print(report)                      # 同时打印到 stdout，方便本地查看
    if no_push:
        print("\n[report] --no-push：已渲染，未推送")
    else:
        notify("WorkBuddy 积分日报", report)


if __name__ == "__main__":
    main()
