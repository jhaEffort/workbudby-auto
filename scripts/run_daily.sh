#!/bin/bash
# WorkBuddy 每日自动化 —— 合并版单一入口（本机用；CI 直接用 .github/workflows）
#
# 一条链路：auto_daily.py → report.py → notify.py（微信）
# 按当前时间自动选模式：
#   < 12:00  → --all              （签到 + 领旧奖 + 派猫 + 对话打卡 + 成长任务 + 抽奖 + 兑换）
#   >= 12:00 → --afternoon --chat （领奖 + 再补一次对话打卡）
#
# 目录约定：
#   SCRIPT_DIR = 本脚本所在目录（放 auto_daily.py / report.py / notify.py）
#   WORK_DIR   = 当前工作目录（放 tokens.txt）—— 由 launchd 的 WorkingDirectory 指定
#
# 用法：
#   cd <放 tokens.txt 的目录> && bash <repo>/scripts/run_daily.sh
#   WB_NO_PUSH=1 bash run_daily.sh        # 只跑不推送（调试）
#   PYTHON=/usr/bin/python3 bash run_daily.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK_DIR="$(pwd)"
PY="${PYTHON:-python3}"
LOG="$WORK_DIR/daily.log"

TMP=$(mktemp /tmp/wb_daily.XXXXXX)

HOUR=$(date +%H)
if [ "$HOUR" -lt 12 ]; then
  MODE="--all"
  MODE_NAME="早晨例行"
else
  MODE="--afternoon --chat"
  MODE_NAME="下午领奖"
fi

{
  echo "=========================================="
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] WorkBuddy 每日任务开始（${MODE_NAME}）"
  echo "=========================================="
  echo ""

  "$PY" "$SCRIPT_DIR/auto_daily.py" $MODE 2>&1 || echo "⚠️ auto_daily.py 执行出错，继续生成日报..."

  echo ""
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 任务结束"
  echo "=========================================="
} | tee -a "$LOG" | tee "$TMP"

# 生成日报并推送（WB_NO_PUSH=1 时只渲染不推送）
"$PY" "$SCRIPT_DIR/report.py" "$TMP" >> "$LOG" 2>&1 || true

rm -f "$TMP"
