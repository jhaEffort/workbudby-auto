#!/usr/bin/env python3
"""报表推送模块（零依赖，纯标准库；不含任何密钥）。

支持两个渠道，全部通过【环境变量】配置，避免把密钥写进代码或仓库：

  1. 微信 Server酱   —— 环境变量 SCT_SENDKEY
  2. 微信 PushPlus   —— 环境变量 PUSHPLUS_TOKEN
  3. 邮件 SMTP       —— 环境变量 SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS / SMTP_TO

本机使用也可以建 .notify.json（该文件已在 .gitignore 中，切勿提交）：
{
  "wechat": {"enabled": true, "provider": "serverchan", "sendkey": "..."}
}

优先级：环境变量 > .notify.json。CI（GitHub Actions）一律用环境变量（配成 Secrets）。

用法：
  from notify import notify
  notify("标题", "内容")
"""
import json
import os
import sys
import urllib.request
import urllib.error
import smtplib
import ssl
from email.mime.text import MIMEText
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / ".notify.json"
REQUEST_TIMEOUT = 15


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _post_json(url: str, payload: dict) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"},
                                 method="POST", data=data)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            resp.read()
        return True
    except Exception as e:
        print(f"[notify] 推送失败: {e}", file=sys.stderr)
        return False


def _send_wechat(provider: str, sendkey: str, title: str, content: str) -> bool:
    if not sendkey:
        return False
    if provider == "pushplus":
        return _post_json("http://www.pushplus.plus/send",
                          {"token": sendkey, "title": title, "content": content, "template": "txt"})
    # 默认 Server酱
    return _post_json(f"https://sctapi.ftqq.com/{sendkey}.send",
                      {"title": title, "desp": content})


def _send_email(host, port, user, pwd, to, title, content) -> bool:
    if not (host and user and pwd):
        return False
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = user
    msg["To"] = to or user
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, int(port or 465), context=ctx, timeout=REQUEST_TIMEOUT) as s:
            s.login(user, pwd)
            s.sendmail(user, [to or user], msg.as_string())
        return True
    except Exception as e:
        print(f"[notify] 邮件发送失败: {e}", file=sys.stderr)
        return False


def notify(title: str, content: str) -> None:
    """推送报表。任意渠道配置好即推送；都没配则只留日志不推送。"""
    cfg = _load_config()
    wc = cfg.get("wechat", {})
    em = cfg.get("email", {})

    # 环境变量优先（CI 用 Secrets，本机用 .notify.json）
    sct = os.environ.get("SCT_SENDKEY", "").strip()
    pushplus = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    provider = (wc.get("provider") or "serverchan").lower()
    sendkey = wc.get("sendkey", "").strip() if wc.get("enabled") else ""

    any_ok = False
    if sct:
        any_ok = _send_wechat("serverchan", sct, title, content) or any_ok
        print("[notify] 微信(Server酱/环境变量)推送完成", file=sys.stderr)
    if pushplus:
        any_ok = _send_wechat("pushplus", pushplus, title, content) or any_ok
        print("[notify] 微信(PushPlus/环境变量)推送完成", file=sys.stderr)
    if not (sct or pushplus) and sendkey:
        any_ok = _send_wechat(provider, sendkey, title, content) or any_ok
        print("[notify] 微信(.notify.json)推送完成", file=sys.stderr)

    smtp_host = os.environ.get("SMTP_HOST", em.get("smtp_host", "")).strip()
    smtp_user = os.environ.get("SMTP_USER", em.get("username", "")).strip()
    smtp_pass = os.environ.get("SMTP_PASS", em.get("password", "")).strip()
    if smtp_host and smtp_user and smtp_pass:
        ok = _send_email(smtp_host, os.environ.get("SMTP_PORT", em.get("smtp_port", 465)),
                         smtp_user, smtp_pass,
                         os.environ.get("SMTP_TO", em.get("to", "")).strip(),
                         title, content)
        any_ok = ok or any_ok

    if not any_ok:
        print("[notify] 未配置任何推送渠道，报表仅记录到日志。", file=sys.stderr)


if __name__ == "__main__":
    notify("测试推送", "如果你收到这条，说明推送已配置好。")
