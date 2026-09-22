#!/usr/bin/env python3
"""WorkBuddy 多账号自动日常：签到 + 喵旅行 + 查积分（账号解耦版，跨平台）。

跨平台：仅依赖 Python 3 标准库，macOS / Windows / Linux 通用；Windows 上命令用 python 而非 python3。

不内置任何登录信息。首次使用需提供【你自己的】accessToken：

Token 有效期：accessToken 实测为**固定 60 天**（签发日 +60d），不是长期凭证。
  每次运行都会打印该账号 token 的剩余天数；剩余 <7 天会高亮提醒，过期后需重新导出。
  定时任务（cron / GitHub Actions）务必留意这一点，否则会静默失效。

⚠️ **CI（GitHub Actions）无法自己续期**：云端容器里没有桌面端登录态，而 OAuth
  refresh 需要客户端密钥（拿不到，见 refresh_tokens.py 的说明）。
  所以 CI 侧的 token 必须由**装了桌面端的机器**定期推送更新（见 refresh_tokens.py
  --push-github），CI 自己则用 `--check-expiry` 做提前告警：
  有 token 临近过期就让工作流失败，GitHub 会发邮件提醒你。
  A. 环境变量单账号： export WB_TOKEN=<你的token>
  B. 多账号：当前目录建 tokens.txt：
       # WB_TOKEN_1 = 我的主账号
       WB_TOKEN_1=<你的token>
       # WB_TOKEN_2 = 小号
       WB_TOKEN_2=<你的token>

用法：
  python3 auto_daily.py               # 早晨例行：签到 + 领取上次奖励 + 派猫出发 + 查积分（全部账号）
  python3 auto_daily.py --afternoon   # 下午领奖（上午派出的猫回来了）
  python3 auto_daily.py --query       # 只查积分
  python3 auto_daily.py --usage       # 查积分使用概况（额度/已用/剩余/临近失效）
  python3 auto_daily.py --chat        # 连续登录对话打卡（WebChat 直写真实会话，三账号统一）
  python3 auto_daily.py --chat=5      # 对话打卡 5 次（成长任务「和AI聊天N次」用，注意消耗额度）
  python3 auto_daily.py --tasks       # 成长任务：接受 + 查看进度 + 领取奖励
  python3 auto_daily.py --lottery     # 抽奖（自动查剩余次数并抽完）
  python3 auto_daily.py --redeem      # 按连续登录档位兑换奖励（7d/14d/28d）
  python3 auto_daily.py --makeup      # 用补签卡补今天（连续登录断签兜底）
  python3 auto_daily.py --makeup=2026-09-20  # 补签指定日期
  python3 auto_daily.py --all         # 早晨例行 + 对话打卡 + 成长任务 + 抽奖 + 兑换
  python3 auto_daily.py --check-expiry      # 只体检 token 有效期，<7 天则以退出码 1 告警
  python3 auto_daily.py --check-expiry=14   # 阈值改为 14 天
  python3 auto_daily.py --list        # 列出已配置的账号（含序号与标签）
  python3 auto_daily.py --account 2   # 只处理第 2 个账号（按序号）
  python3 auto_daily.py --account 1234   # 只处理标签里含 1234 的账号（按关键字切换）
  python3 auto_daily.py --account 小号    # 只处理标签里含「小号」的账号
  python3 auto_daily.py --open-box    # 额外开 Buddy 盲盒（消耗 10 能量）

多账号切换说明：
  本脚本直接用 token 调接口，不需要在 WorkBuddy 客户端里切换/登录账号——
  tokens.txt 里写了几个账号，脚本就能操作几个。
  想单独操作某个账号用 --account（序号或标签关键字），不加则全部处理。

说明：
  - 每个账号独立处理，互不影响；某个账号 token 失效只会单独报错，不中断其他账号。
  - 「连续登录」的对话打卡是另一回事（需真实对话），用独立的 --chat 子命令做（WebChat 通道）。

--chat 说明（连续登录对话打卡）：
  增长中心「连续登录」后端只对当日产生「真实对话」的账号自动 +1。
  本模式用前端同款 WebChat 通道（纯 token，不依赖客户端在线）直写该账号的真实云端会话：
    1) POST /console/webchat/conversations      新建真实会话，拿 conversationId
    2) POST /console/chat/completions           发消息 + 取真实 AI 回复（SSE 流）
    3) POST /v2/report 发 chat_request_send / chat_request_response 遥测
  三账号统一走这条路径，「是否计入连续登录」仍需次日打开增长中心核对（建议连续观察 2~3 天）。
"""
import json
import sys
import os
import time
import random
import base64
import uuid
import urllib.request
import urllib.error
from datetime import datetime, date

API = "https://www.codebuddy.cn"
WEB = "https://www.workbuddy.cn"   # 对话/遥测通道（与计费 API 不同 host）
EP = {
    "checkin": f"{API}/v2/billing/meter/daily-checkin",
    "resource": f"{API}/v2/billing/meter/get-user-resource",
    "travel_config": f"{API}/v2/activity/growth/buddy/travel/config",
    "travel_status": f"{API}/v2/activity/growth/buddy/travel/status",
    "travel_depart": f"{API}/v2/activity/growth/buddy/travel/depart",
    "travel_claim": f"{API}/v2/activity/growth/buddy/travel/claim",
    "energy": f"{API}/v2/activity/growth/energy",
    "open": f"{API}/v2/activity/growth/buddy/open",
}
TIMEOUT = 15
FOUR_HOURS_PROB = 0.8          # 80% 用满 4h（最高奖励），20% 随机 1-3h


def log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")


def api(url: str, token: str, method: str = "GET", body=None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "WorkBuddy-Desktop",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if e.code == 401:
                log("HTTP 401: token 已失效，请刷新你自己的 accessToken")
            else:
                log(f"HTTP {e.code}: {raw[:200]}")
            return {"_error": e.code}
    except Exception as e:
        log(f"请求失败: {e}")
        return {"_error": str(e)}


# ─── 连续登录对话打卡（WebChat 通道：纯 token 直写真实云端会话，不依赖客户端在线）────
# 增长中心「连续登录」后端只对当日产生「真实对话」的账号自动 +1。
# 早先用 ACP(/console/as/conversations) 直写：长期未活跃账号的会话全是 completed，
#   worker 收下(202)但不落库、不计连续登录；且 POST 创建会话是 403（无权限）——此路已死。
# 现改用前端同款 WebChat 通道（参考社区签到脚本 v21~v23，纯 token 可靠）：
#   1) POST /console/webchat/conversations      -> 新建真实会话，拿 conversationId
#   2) POST /console/chat/completions          -> 发消息 + 取真实 AI 回复（SSE 流）
#   3) POST /v2/report 发 chat_request_send / chat_request_response 遥测
# 三个账号统一走这条 token 路径，无需客户端在线，可 CI。
def jwt_sub(token: str) -> str:
    """从 Bearer JWT 中段解出 sub（user_id），供遥测 userId 字段使用。"""
    try:
        import base64
        parts = token.split(".")
        if len(parts) < 2:
            return ""
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("sub", "") or ""
    except Exception:
        return ""


def jwt_exp(token: str) -> int:
    """从 Bearer JWT 解出 exp（过期时间戳，秒）；无 exp 字段返回 0。"""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return 0
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp") or 0)
    except Exception:
        return 0


def token_expiry_note(token: str, label: str = ""):
    """打印 token 剩余有效期；临近过期(<7 天)或已过期时高亮提醒。

    accessToken 实测固定 60 天有效期（签发日 +60d），到期后需重新导出，
    所以每次运行都报一下剩余天数，避免定时任务静默失效。
    """
    exp = jwt_exp(token)
    if not exp:
        log(f"{label} 🔐 token 无 exp 字段（长效/未知）")
        return
    days = (exp - time.time()) / 86400
    until = datetime.fromtimestamp(exp).strftime("%Y-%m-%d")
    if days <= 0:
        log(f"{label} 🔴 token 已过期（{until}），请重新导出！")
    elif days < 7:
        log(f"{label} 🟠 token 仅剩 {days:.1f} 天（{until} 到期），请尽快重新导出")
    else:
        log(f"{label} 🔐 token 剩余 {days:.0f} 天（{until} 到期）")


def _sse_collect(url: str, headers: dict, body: dict, timeout: int = 60) -> str:
    """POST 并逐行读 SSE 流，拼出 AI 回复文本。"""
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = ""
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk in ("[✅完成]", "[DONE]"):
                    continue
                try:
                    d = json.loads(chunk)
                except Exception:
                    continue
                for c in d.get("choices", []):
                    cp = c.get("delta", {}).get("content", "")
                    if cp:
                        text += cp
            return text
    except urllib.error.HTTPError as e:
        log(f"WebChat HTTP {e.code}: {e.read().decode(errors='replace')[:120]}")
        return ""
    except Exception as e:
        log(f"WebChat 失败: {e}")
        return ""


CHAT_PROMPTS = [
    "早安，请直接回复一句「今日连续登录打卡完成」即可。",
    "你好，请简单介绍一下你自己",
    "今天天气怎么样？",
    "1+1等于几？请直接回答",
    "Python是什么？一句话回答",
    "请说再见",
    "写一首关于春天的诗",
    "如何学习编程？",
    "推荐一本好书",
    "解释一下什么是云计算",
]


def chat_checkin_one(token: str, label: str = "", count: int = 1) -> int:
    """对一个账号做连续登录对话打卡（WebChat 通道，纯 token，不依赖客户端）。

    每次都在账号名下新建一个真实云端会话并发生成式对话，后端据此给「连续登录」+1；
    成长任务类「和AI聊天N次」需要多轮时用 --chat=N（每轮独立会话，更接近真实行为）。
    返回成功对话数。
    注意：真实对话会消耗模型额度，日常续登用默认 1 次即可。
    """
    uid = jwt_sub(token)
    if not uid:
        log(f"{label} ⚠️ 无法从 token 解析 userId，遥测将缺 userId")
    hdr = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
           "Accept": "text/event-stream", "Referer": f"{WEB}/chat/",
           "Origin": WEB, "User-Agent": "Mozilla/5.0"}
    ok = 0
    for i in range(count):
        prompt = CHAT_PROMPTS[i % len(CHAT_PROMPTS)]
        r = api(f"{WEB}/console/webchat/conversations", token, "POST",
                {"name": f"wb-checkin-{uuid.uuid4().hex[:12]}"})
        conv_id = (r.get("data") or {}).get("conversationId", "")
        if not conv_id:
            log(f"{label} WebChat 创建会话失败({i+1}/{count}): {str(r)[:120]}")
            continue
        resp = _sse_collect(f"{WEB}/console/chat/completions", hdr,
                            {"messages": [{"role": "user", "content": prompt}],
                             "model": "glm-5.2", "stream": True, "conversationId": conv_id})
        rid = f"cmb-{uuid.uuid4().hex}"
        now = int(time.time() * 1000)
        events = [
            {"eventCode": "chat_request_send", "timestamp": now - 2000, "reportDelay": 0,
             "expKeys": "", "ideName": "sdk", "machineId": uuid.uuid4().hex, "userId": uid,
             "mode": "ask", "conversationId": conv_id, "requestId": rid,
             "requestModelId": "glm-5.2", "requestModelName": "glm-5.2",
             "inputLength": len(prompt), "customAgentName": ""},
            {"eventCode": "chat_request_response", "timestamp": now, "reportDelay": 0,
             "expKeys": "", "ideName": "sdk", "machineId": uuid.uuid4().hex, "userId": uid,
             "mode": "ask", "conversationId": conv_id, "requestId": rid,
             "requestModelId": "glm-5.2", "requestModelName": "glm-5.2", "toolCallCount": 0,
             "inputToken": max(1, len(prompt) // 4),
             "outputToken": max(1, len(resp) // 4) if resp else 1,
             "totalToken": max(2, (len(prompt) + len(resp)) // 4)},
        ]
        tr = api(f"{WEB}/v2/report", token, "POST", events)
        good = bool(resp) and tr.get("code") == 0
        if good:
            ok += 1
        log(f"{label} 对话 {i+1}/{count} 会话={conv_id[:12]}… 回复={'有' if resp else '无'}"
            f"({len(resp)}字) 遥测={'✅' if tr.get('code') == 0 else '⚠️' + str(tr.get('code'))}")
        if i < count - 1:
            time.sleep(random.uniform(2, 5))
    log(f"{label} 对话打卡完成: {ok}/{count} " + ("✅" if ok == count else "⚠️"))
    return ok


# ─── 成长中心：连续签到 / 成长任务 / 抽奖 / 连登兑换 / 补签卡 ──────────────
# 端点均走网页端 host（WEB），与计费 API（API）不同域。
GR = {
    "streak": f"{WEB}/v2/activity/growth/streak",
    "tasks": f"{WEB}/v2/activity/growth/tasks",
    "accept": f"{WEB}/v2/activity/growth/tasks/accept",
    "claim": f"{WEB}/v2/activity/growth/tasks/",          # + {code} + /claim
    "lottery_chances": f"{WEB}/v2/activity/growth/lottery/chances",
    "lottery_draw": f"{WEB}/v2/activity/growth/lottery/draw",
    "redeem": f"{WEB}/v2/activity/growth/redeem",
    "makeup": f"{WEB}/v2/activity/growth/makeup-cards/use",
}


def get_streak(token: str) -> dict:
    """连续登录天数等信息；失败返回 {}。"""
    r = api(GR["streak"], token)
    if "_error" in r or r.get("code") not in (0, None):
        return {}
    return (r.get("data") or {}).get("streak", {}) or {}


def do_makeup(token: str, label: str, target: str = ""):
    """补签卡：补回断签的那天，连续登录天数可续上（账号需有补签卡）。"""
    if not target:
        target = date.today().strftime("%Y-%m-%d")
    r = api(GR["makeup"], token, "POST", {"target_date": target})
    code = r.get("code", r.get("_error", -1))
    msg = str(r.get("msg", r.get("message", "")))
    if code == 0:
        log(f"{label} 🎫 补签成功 {target} {msg}")
    else:
        log(f"{label} 🎫 补签 {target}: code={code} msg={msg}")


def do_lottery(token: str, label: str):
    """抽奖：先查剩余次数，有多少抽多少。"""
    c = api(GR["lottery_chances"], token)
    d = c.get("data") or {}
    raw = d.get("balance", d.get("chances", d.get("remaining")))
    if raw is None:
        log(f"{label} 🎰 抽奖次数查询失败/无字段: {str(c)[:120]}")
        return
    chances = int(raw)
    if chances <= 0:
        log(f"{label} 🎰 无抽奖次数（{chances}）")
        return
    log(f"{label} 🎰 剩余抽奖次数 {chances}，开始抽…")
    for i in range(chances):
        r = api(GR["lottery_draw"], token, "POST", {"client_token": uuid.uuid4().hex})
        code = r.get("code", r.get("_error", -1))
        rd = r.get("data") or {}
        prize = rd.get("name") or rd.get("prize") or r.get("msg", "")
        log(f"{label} 🎰 第 {i+1} 抽: code={code} {str(prize)[:60]}")
        time.sleep(random.uniform(1, 3))


def do_redeem(token: str, label: str):
    """按连续登录档位兑换奖励（7d/14d/28d）；已兑换(409)/天数不足(403)自动跳过。"""
    days = int(get_streak(token).get("days", 0))
    log(f"{label} 🎁 连续登录 {days} 天")
    for tier, need in (("7d", 7), ("14d", 14), ("28d", 28)):
        if days < need:
            log(f"{label} 🎁 档位 {tier} 需 {need} 天，跳过")
            continue
        r = api(GR["redeem"], token, "POST",
                {"tier": tier, "client_token": uuid.uuid4().hex})
        code = r.get("code", r.get("_error", -1))
        if code == 0:
            d = r.get("data") or {}
            log(f"{label} 🎁 兑换 {tier} 成功! +{d.get('credit_granted', 0)} 积分 "
                f"+{d.get('energy_granted', 0)} 能量 +{d.get('chances_granted', 0)} 抽奖")
        else:
            log(f"{label} 🎁 兑换 {tier}: code={code} msg={str(r.get('msg', ''))[:60]}")
        time.sleep(1)


def do_growth_tasks(token: str, label: str):
    """成长任务：接受 → 查看进度 → 领取已达成的。动态读取，不硬编码任务码。

    说明：纯对话类任务（如「和AI聊天5次」）依赖 --chat=N 产生真实对话来推进，
    本函数只负责接受与领取；其余靠遥测推进的任务在 --chat 之外另行处理。
    """
    r = api(GR["tasks"], token)
    if "_error" in r:
        log(f"{label} 📋 成长任务查询失败")
        return
    data = r.get("data") or {}
    tasks = data.get("tasks") or data.get("list") or []
    if not tasks:
        log(f"{label} 📋 无成长任务（响应 keys={list(data.keys())}）")
        return

    # 1) 批量接受尚未接受的任务（注意是 task_codes 数组，不是 task_code 单数）
    todo = [t.get("task_code") for t in tasks
            if t.get("task_code") and t.get("accept_status") not in ("accepted", "claimed")]
    if todo:
        ar = api(GR["accept"], token, "POST", {"task_codes": todo})
        log(f"{label} 📋 接受任务 {len(todo)} 个: code={ar.get('code')} {str(ar.get('msg',''))[:60]}")
    else:
        log(f"{label} 📋 任务均已接受过")

    # 2) 重新拉取进度，逐个领取已达成的
    time.sleep(2)
    r2 = api(GR["tasks"], token)
    tasks2 = (r2.get("data") or {}).get("tasks") or tasks
    got = 0
    for t in tasks2:
        code = t.get("task_code")
        if not code:
            continue
        name = t.get("title") or code
        prog = t.get("progress") or {}
        cur, tgt = prog.get("current", 0), prog.get("target", 0)
        st = t.get("accept_status", "")     # accepted（进行中）/ claimed（已领取）
        reward = t.get("reward_credit", 0)
        if st == "claimed":
            log(f"  ✅ {name} 已领取 (+{reward})")
            continue
        if tgt and cur >= tgt:
            cr = api(GR["claim"] + code + "/claim", token, "POST", {})
            c = cr.get("code", cr.get("_error", -1))
            m = str(cr.get("msg", ""))
            if c == 0:
                got += 1
                log(f"  🎉 {name} 达成 {cur}/{tgt} → 领取成功 +{reward} 积分")
            elif "已" in m or c == 10001:
                log(f"  📌 {name} 已领取过")
            else:
                log(f"  ⚠️ {name} 领取: code={c} msg={m[:50]}")
            time.sleep(1)
        else:
            log(f"  ·  {name} {cur}/{tgt} (+{reward} 积分)")
    log(f"{label} 📋 本轮领取 {got} 个任务奖励")


# ─── 查积分（客户端「可用积分」口径 = 当月周期剩余 CycleCapacityRemainPrecise 之和）───
def get_credits(token: str) -> int:
    r = api(EP["resource"], token, "POST", {})
    if "_error" in r:
        return -1
    accs = r.get("data", {}).get("Response", {}).get("Data", {}).get("Accounts", [])
    total = 0.0
    for a in accs:
        if a.get("CapacityUnit") != "credits" or a.get("Status", 0) != 0:
            continue
        raw = a.get("CycleCapacityRemainPrecise")
        if raw is None:
            raw = a.get("CycleCapacityRemain")
        if raw is None:
            raw = a.get("CapacityRemain", 0)
        try:
            total += float(raw)
        except (TypeError, ValueError):
            pass
    return int(round(total))


def get_usage(token: str) -> dict:
    """积分使用概况：当月周期额度 / 已用 / 剩余，以及临近失效的额度。

    字段口径：
      - CapacityUnit == "credits" 且 Status == 0 才是有效积分账户
      - CycleCapacitySizePrecise / Used / Remain：当月（各充值周期的）额度、已用、剩余
      - DeductionEndTime（毫秒）：扣减有效期，决定这笔积分什么时候失效 **
        注意不是 ExpiredTime（常为空）
    """
    r = api(EP["resource"], token, "POST", {})
    if "_error" in r:
        return {}
    accs = r.get("data", {}).get("Response", {}).get("Data", {}).get("Accounts", [])
    now = time.time()
    now_dt = datetime.now()
    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    info = {"size": 0.0, "used": 0.0, "remain": 0.0, "soon": 0.0, "earliest": 0,
            "used_all": 0.0, "wasted_month": 0.0}
    for a in accs:
        if a.get("CapacityUnit") != "credits":
            continue
        # 累计已用：包被消耗光后会从 Status==0 列表里消失，只看 live 会严重低估真实用量，
        # 所以这里不筛 Status，把所有积分包的 CapacityUsedPrecise 都算进来。
        try:
            info["used_all"] += float(a.get("CapacityUsedPrecise") or 0)
        except (TypeError, ValueError):
            pass
        if a.get("Status", 0) != 0:
            # 已失效包里，本月到期的那部分是「没用就过期作废」的额度
            end = (a.get("DeductionEndTime") or 0) / 1000
            if month_start <= end <= now:
                try:
                    info["wasted_month"] += float(a.get("CapacityRemainPrecise") or 0)
                except (TypeError, ValueError):
                    pass
            continue
        for src, dst in (("CycleCapacitySizePrecise", "size"),
                         ("CycleCapacityUsedPrecise", "used"),
                         ("CycleCapacityRemainPrecise", "remain")):
            try:
                info[dst] += float(a.get(src) or 0)
            except (TypeError, ValueError):
                pass
        end = (a.get("DeductionEndTime") or 0) / 1000
        if end > now:
            if end - now <= 7 * 86400:
                try:
                    info["soon"] += float(a.get("CycleCapacityRemainPrecise") or 0)
                except (TypeError, ValueError):
                    pass
            if info["earliest"] == 0 or end < info["earliest"]:
                info["earliest"] = end
    return info


# ─── 签到 ────────────────────────────────────────────────
def do_checkin(token: str) -> dict:
    return api(EP["checkin"], token, "POST", {})


# ─── 喵旅行 ──────────────────────────────────────────────
def get_status(token: str) -> dict:
    return api(EP["travel_status"], token)


def get_config(token: str) -> dict:
    return api(EP["travel_config"], token)


def claim_reward(token: str) -> dict:
    return api(EP["travel_claim"], token, "POST")


def depart(token: str, loc: int, dur: int) -> dict:
    return api(EP["travel_depart"], token, "POST", {"location_id": loc, "duration_hours": dur})


def pick_location(cfg: dict) -> int:
    locs = cfg.get("data", {}).get("locations", [])
    if not locs:
        return 1
    return locs[datetime.now().timetuple().tm_yday % len(locs)]["id"]


def pick_duration() -> int:
    return 4 if random.random() < FOUR_HOURS_PROB else random.randint(1, 3)


def fmt_claim(r: dict) -> str:
    if "_error" in r:
        return f"⚠️ 请求失败(code={r['_error']})"
    code = r.get("code", -1)
    msg = str(r.get("msg", r.get("message", "")))
    if code == 0 or "成功" in msg or "OK" in msg:
        c = r.get("data", {}).get("reward_credit") or r.get("data", {}).get("credit")
        return "✅ 领取成功" + (f" +{c} 积分" if c is not None else "")
    if "已" in msg or code == 10001:
        return "📌 没有待领取的奖励"
    return f"⚠️ 领取结果: code={code} msg={msg}"


def do_claim(token: str, label: str = ""):
    s = get_status(token).get("data", {})
    state = s.get("state")
    if state == "idle":
        log(f"{label} 猫猫在家，无待领奖励")
        return False
    if state == "traveling":
        now = s.get("server_now", int(time.time()))
        arrive = s.get("arrive_at", now)
        if now < arrive:
            log(f"{label} 猫猫旅行中，暂不能领")
            return False
    r = claim_reward(token)
    log(f"{label} {fmt_claim(r)}")
    return True


def do_depart(token: str, label: str = ""):
    s = get_status(token).get("data", {})
    if s.get("state") == "traveling":
        now = s.get("server_now", int(time.time()))
        arrive = s.get("arrive_at", now)
        if now < arrive:
            log(f"{label} 猫猫旅行中，无法派发")
            return False
    if s.get("daily_limit_reached"):
        log(f"{label} 今日旅行次数已用完")
        return False
    cfg = get_config(token)
    loc = pick_location(cfg)
    loc_name = next((l["name"] for l in cfg.get("data", {}).get("locations", []) if l["id"] == loc), "?")
    dur = pick_duration()
    log(f"{label} 派猫去「{loc_name}」旅行 {dur}h...")
    r = depart(token, loc, dur)
    code = r.get("code", r.get("_error", -1))
    d = r.get("data", {})
    if code == 0 or "OK" in str(r.get("msg", "")):
        aw = d.get("arrive_at")
        t = f"  预计 {datetime.fromtimestamp(aw):%H:%M} 回来" if aw else ""
        log(f"✅ 派发成功! 奖励 {d.get('reward_credit', '?')} 积分{t}")
        return True
    log(f"{label} 派发结果: code={code} msg={r.get('msg', '')}")
    return False


# ─── 多账号 token 加载（账号解耦，不读任何本地登录态目录）────────────
def load_tokens() -> list:
    """按优先级取 token：
       1) WB_TOKEN        —— 单个账号
       2) WB_TOKEN_1..N   —— 多账号环境变量（CI / GitHub Actions 用这种，不用落盘的 tokens.txt）
       3) 当前目录 tokens.txt
    """
    env = os.environ.get("WB_TOKEN")
    if env and env.strip():
        return [{"label": "账号(WB_TOKEN)", "token": env.strip()}]

    multi = []
    keys = [k for k in os.environ if k.startswith("WB_TOKEN_")]
    def _idx(k: str) -> int:
        tail = k.rsplit("_", 1)[-1]
        return int(tail) if tail.isdigit() else 999999
    for k in sorted(keys, key=_idx):
        v = (os.environ.get(k) or "").strip()
        if v:
            multi.append({"label": f"账号({k})", "token": v})
    if multi:
        return multi

    txt = os.path.join(os.getcwd(), "tokens.txt")
    if os.path.exists(txt):
        out = []
        label = "?"
        for line in open(txt, encoding="utf-8").read().splitlines():
            s = line.strip()
            if s.startswith("#"):
                if "=" in s:
                    label = s.split("=", 1)[1].strip()
                continue
            if s.startswith("WB_TOKEN_") and "=" in s:
                t = s.split("=", 1)[1].strip()
                if t:
                    out.append({"label": label, "token": t})
                    label = "?"
        if out:
            return out
    return []


def main():
    argv = sys.argv[1:]
    sel = None   # --account 的原始值：数字=序号，其它=标签关键字
    for i, a in enumerate(argv):
        if a == "--account" and i + 1 < len(argv):
            sel = argv[i + 1]
    args = [a for a in argv if a != "--account" and a != sel]

    if "--query" in args:
        mode = "query"
    elif "--usage" in args:
        mode = "usage"
    elif "--afternoon" in args:
        mode = "afternoon"
    else:
        mode = "morning"

    # 子开关解析：支持 --name 与 --name=值 两种写法
    def _flag(name):
        for a in args:
            if a == name:
                return True, None
            if a.startswith(name + "="):
                return True, a.split("=", 1)[1].strip()
        return False, None

    # --chat 与日常例行合并执行（不互斥）：默认顺带早晨签到，配 --afternoon 则含下午领奖
    has_chat, chat_val = _flag("--chat")
    chat_count = 1
    if has_chat and chat_val:
        try:
            chat_count = max(1, min(int(chat_val), 20))
        except ValueError:
            chat_count = 1
    has_tasks, _ = _flag("--tasks")
    has_lottery, _ = _flag("--lottery")
    has_redeem, _ = _flag("--redeem")
    has_makeup, makeup_val = _flag("--makeup")
    has_check, check_val = _flag("--check-expiry")
    check_days = 7
    if check_val:
        try:
            check_days = max(1, int(check_val))
        except ValueError:
            pass
    if "--all" in args:
        has_chat, has_tasks, has_lottery, has_redeem = True, True, True, True

    accounts = load_tokens()
    if not accounts:
        print("未找到 token。请任选方式提供【你自己的】WorkBuddy accessToken：")
        print("  A. 环境变量： export WB_TOKEN=<你的token>")
        print("  B. 当前目录建 tokens.txt：")
        print("       # WB_TOKEN_1 = 我的主账号")
        print("       WB_TOKEN_1=<你的token>")
        print("       # WB_TOKEN_2 = 小号")
        print("       WB_TOKEN_2=<你的token>")
        print("如何获取 token：WorkBuddy 桌面端登录态在")
        print("  ~/Library/Application Support/CodeBuddyExtension/Data/Public/auth/*.info")
        print("  取 auth.accessToken 字段（约 60 天有效，过期重新获取）。")
        sys.exit(1)

    # --list：列出已配置的账号，方便确认要切换到哪个
    if "--list" in args:
        print(f"已配置 {len(accounts)} 个账号：")
        for i, acc in enumerate(accounts, 1):
            t = acc["token"]
            masked = f"{t[:10]}...{t[-6:]}" if len(t) > 20 else t
            print(f"  [{i}] {acc['label']}   token: {masked}")
        print("\n切换到某个账号：")
        print("  --account 2            # 按序号")
        print("  --account 1234         # 按标签里的关键字（如手机尾号）")
        print("  --account 小号          # 按标签里的中文关键字")
        print("不加 --account 则默认跑全部账号。")
        return

    # 账号切换：优先按序号（数字且在有效范围内），否则按标签关键字匹配
    # 注意：账号标识常是手机尾号这类纯数字（如 5678/1234），
    # 所以「数字但序号越界」不能直接报错，要继续尝试按标签关键字匹配。
    if sel is not None:
        picked = None
        if sel.isdigit():
            idx = int(sel) - 1
            if 0 <= idx < len(accounts):
                picked = [accounts[idx]]
        if picked is None:
            kw = sel.lower()
            matched = [a for a in accounts if kw in a["label"].lower()]
            if matched:
                picked = matched
        if picked is None:
            if sel.isdigit():
                print(f"账号序号 {sel} 超出范围（1-{len(accounts)}），且没有标签包含「{sel}」。")
            else:
                print(f"没有标签包含「{sel}」的账号。")
            print("当前可用账号（用 --list 查看更详细）：")
            for i, a in enumerate(accounts, 1):
                print(f"  [{i}] {a['label']}")
            sys.exit(1)
        accounts = picked

    # ── --check-expiry：只体检 token 有效期，不执行任何业务 ──
    # 用途：CI（GitHub Actions）没有桌面端登录态、也无法自己续期，
    # 用它做「提前告警」——有 token 临近过期就以非 0 退出，
    # GitHub 会给失败的定时任务发邮件，等于零配置的提醒。
    if has_check:
        bad = 0
        for acc in accounts:
            exp = jwt_exp(acc["token"])
            days = (exp - time.time()) / 86400 if exp else -1
            until = datetime.fromtimestamp(exp).strftime("%Y-%m-%d") if exp else "-"
            if days < 0:
                log(f"🔴 {acc['label']} token 已过期（{until}）")
                bad += 1
            elif days < check_days:
                log(f"🟠 {acc['label']} token 仅剩 {days:.1f} 天（{until} 到期）")
                bad += 1
            else:
                log(f"🔐 {acc['label']} token 剩余 {days:.0f} 天（{until} 到期）")
        if bad:
            log(f"❌ {bad} 个账号的 token 将在 {check_days} 天内过期，"
                f"请更新 GitHub Secrets / tokens.txt 后重跑")
            sys.exit(1)
        log(f"✅ 所有 token 剩余有效期 > {check_days} 天")
        return

    log(f"WorkBuddy 自动日常（{mode}）共 {len(accounts)} 个账号")
    for acc in accounts:
        log(f"── {acc['label']} ──")
        token_expiry_note(acc["token"], acc["label"])
        if mode == "usage":
            u = get_usage(acc["token"])
            if not u:
                log("📊 查询失败")
                continue
            earliest = datetime.fromtimestamp(u["earliest"]).strftime("%m-%d") if u["earliest"] else "-"
            log(f"📊 剩余 {u['remain']:.0f} | 累计已用 {u['used_all']:.0f} | 本月作废 {u['wasted_month']:.0f} "
                f"| 7天内到期 {u['soon']:.0f} | 最近到期 {earliest}")
            continue
        if mode == "query":
            c = get_credits(acc["token"])
            log(f"📊 可用积分: {c}" if c >= 0 else "📊 查询失败")
            continue

        before = get_credits(acc["token"])
        if before >= 0:
            log(f"📊 执行前积分: {before}")

        # 连续登录天数（只读，供 report.py 生成日报时展示）
        _st = get_streak(acc["token"])
        if _st:
            log(f"🔥 连续登录 {_st.get('days', 0)} 天")

        if mode == "morning":
            r = do_checkin(acc["token"])
            code = r.get("code", r.get("_error", -1))
            msg = str(r.get("msg", ""))
            if code == 0:
                d = r.get("data", {})
                log(f"✅ 签到成功 +{d.get('credit', '?')} 积分, 连续 {d.get('streakDays', '?')} 天")
            elif "已签到" in msg or code == 10001:
                log("📌 今天已签到过")
            else:
                log(f"签到结果: code={code} msg={msg}")
            do_claim(acc["token"], acc["label"])
            do_depart(acc["token"], acc["label"])
        elif mode == "afternoon":
            do_claim(acc["token"], acc["label"])

        if "--open-box" in args:
            e = api(EP["energy"], acc["token"]).get("data", {}).get("balance", 0)
            if e >= 10:
                rr = api(EP["open"], acc["token"], "POST", {})
                log(f"🎁 盲盒: code={rr.get('code')} msg={rr.get('msg')}")
            else:
                log(f"能量 {e} < 10，跳过盲盒")

        if has_chat:
            chat_checkin_one(acc["token"], acc["label"], chat_count)
        if has_tasks:
            do_growth_tasks(acc["token"], acc["label"])
        if has_lottery:
            do_lottery(acc["token"], acc["label"])
        if has_redeem:
            do_redeem(acc["token"], acc["label"])
        if has_makeup:
            do_makeup(acc["token"], acc["label"], makeup_val or "")

        after = get_credits(acc["token"])
        if before >= 0 and after >= 0:
            d = int(round(after - before))
            sign = f"+{d}" if d >= 0 else str(d)
            log(f"📊 执行后积分: {after} (本次净变化 {sign})")
        else:
            log("📊 积分查询失败")

    log("全部完成")


if __name__ == "__main__":
    main()
