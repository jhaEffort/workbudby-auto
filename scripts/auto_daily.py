#!/usr/bin/env python3
"""WorkBuddy 多账号自动日常：签到 + 喵旅行 + 查积分（账号解耦版，跨平台）。

跨平台：仅依赖 Python 3 标准库，macOS / Windows / Linux 通用；Windows 上命令用 python 而非 python3。

不内置任何登录信息。首次使用需提供【你自己的】accessToken：
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
  python3 auto_daily.py --chat        # 连续登录对话打卡（ACP 直写云端会话，三账号统一）
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
  - 「连续登录」的对话打卡是另一回事（需真实对话/ACP），用独立的 --chat 子命令做。

--chat 说明（连续登录对话打卡）：
  增长中心「连续登录」没有可程序化打卡的接口，后端只对当日产生「真实对话」的账号自动 +1。
  本模式用 ACP 协议（StreamableHTTP + SSE + JSON-RPC prompt）直写该账号的云端会话：
    1) GET /console/as/conversations/{cid}/session  换 ACP 专用 JWT + worker link + sessionId
    2) GET {link}(SSE) 从响应头取 Acp-Connection-Id
    3) POST {link} 发 initialize / notifications/initialized / prompt 三步（均 202）
  实测三账号均可用，但「是否计入连续登录」需次日打开增长中心核对（早期为待验证项）。
  副作用：会在该账号某个云端会话里多一条打卡消息（复用现有会话，创建专用会话的 API 未开放）。
"""
import json
import sys
import os
import time
import random
import urllib.request
import urllib.error
from datetime import datetime

API = "https://www.codebuddy.cn"
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


# ─── 连续登录对话打卡（ACP 协议直写云端会话，不依赖客户端在线）────────────
# 增长中心「连续登录」没有可程序化打卡的接口，后端只对当日产生「真实对话」的账号自动 +1。
# 唯一的纯服务端路径是 ACP（StreamableHTTP + SSE + JSON-RPC prompt）：
#   1) GET /console/as/conversations/{cid}/session  -> 换 ACP 专用 JWT + worker link + sessionId
#   2) GET {link}(SSE) 取响应头 Acp-Connection-Id
#   3) POST {link} 发 initialize / notifications/initialized / prompt 三步 JSON-RPC（均 202）
# 注意：复用现有云端会话（创建专用会话的 API 未开放），会在该会话里多一条打卡消息。
ACP_HOST = "https://workbuddy.cn"
CONV_LIST = f"{ACP_HOST}/console/as/conversations/"


def acp_sse_get(link: str, acp_token: str) -> str:
    """GET link(SSE)，从响应头取 Acp-Connection-Id。不读 body。"""
    req = urllib.request.Request(link, headers={
        "Authorization": f"Bearer {acp_token}",
        "Accept": "text/event-stream",
        "User-Agent": "WorkBuddy-Desktop",
    }, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            cid = resp.headers.get("Acp-Connection-Id")
            try:
                resp.read(1)
            except Exception:
                pass
            return cid or ""
    except urllib.error.HTTPError as e:
        if e.code == 401:
            log("ACP: token 失效(401)，请刷新 accessToken")
        else:
            log(f"ACP SSE GET HTTP {e.code}")
        return ""
    except Exception as e:
        log(f"ACP SSE GET 失败: {e}")
        return ""


def acp_post(link: str, acp_token: str, conn_id: str, payload: dict) -> bool:
    req = urllib.request.Request(link, headers={
        "Authorization": f"Bearer {acp_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Acp-Connection-Id": conn_id or "",
        "User-Agent": "WorkBuddy-Desktop",
    }, data=json.dumps(payload).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status in (200, 202)
    except urllib.error.HTTPError as e:
        log(f"ACP POST {payload.get('method')} HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
        return False
    except Exception as e:
        log(f"ACP POST {payload.get('method')} 失败: {e}")
        return False


def pick_conversation(token: str):
    """列出云端会话，挑一个写入打卡消息：优先 'new conversation'，否则最近创建，否则第一个。"""
    r = api(CONV_LIST, token)
    if "_error" in r:
        return None
    convs = (r.get("data") or {}).get("conversations", [])
    if not convs:
        return None
    target = next((c for c in convs if c.get("name") == "new conversation"), None)
    if target is None:
        target = max(convs, key=lambda c: c.get("createdAt", 0)) or convs[0]
    return target


def chat_checkin_one(token: str, label: str = "") -> bool:
    """对一个账号做 ACP 对话打卡，返回是否成功发出 prompt。"""
    conv = pick_conversation(token)
    if not conv:
        log(f"{label} 无云端会话，ACP 对话打卡不可用（需先在客户端发起过一次对话）")
        return False
    cid = conv.get("id")
    s = api(f"{CONV_LIST}{cid}/session", token)
    if "_error" in s:
        return False
    d = s.get("data", s)
    link = d.get("link")
    acp_token = d.get("token")
    sid = d.get("sessionId")
    if not (link and acp_token and sid):
        log(f"{label} ACP 会话字段缺失: {list(d.keys())}")
        return False
    conn_id = acp_sse_get(link, acp_token)
    if not conn_id:
        return False
    text = "早安，今日连续登录打卡完成（WorkBuddy 自动脚本）"
    steps = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "wb-checkin", "version": "1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "prompt",
         "params": {"sessionId": sid, "prompt": [{"type": "text", "text": text}], "_meta": {}}},
    ]
    ok = all(acp_post(link, acp_token, conn_id, p) for p in steps)
    log(f"{label} 对话打卡已发往会话 {str(cid)[:12]}… {'✅' if ok else '⚠️'}")
    return ok


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
    args = set(a for a in sys.argv[1:] if not a.startswith("--account"))
    sel = None   # --account 的原始值：数字=序号，其它=标签关键字
    for i, a in enumerate(sys.argv):
        if a == "--account" and i + 1 < len(sys.argv):
            sel = sys.argv[i + 1]

    if "--query" in args:
        mode = "query"
    elif "--usage" in args:
        mode = "usage"
    elif "--afternoon" in args:
        mode = "afternoon"
    else:
        mode = "morning"
    # --chat 与日常例行合并执行（不互斥）：默认顺带早晨签到，配 --afternoon 则含下午领奖
    chat = "--chat" in args

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

    log(f"WorkBuddy 自动日常（{mode}）共 {len(accounts)} 个账号")
    for acc in accounts:
        log(f"── {acc['label']} ──")
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

        if chat:
            chat_checkin_one(acc["token"], acc["label"])

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
