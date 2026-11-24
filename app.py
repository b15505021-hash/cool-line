"""COOL-LINE Flask 主程式與智慧動態排程器。"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, time, timedelta
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, abort, jsonify, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

import auth_helper
import config
import database
import line_service
import scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
handler = WebhookHandler(config.LINE_CHANNEL_SECRET or "placeholder-secret")

_scan_lock = threading.Lock()
_cookie_warning_sent = False
_scheduler: BackgroundScheduler | None = None
_POLL_JOB_ID = "cool_dynamic_poll"

_TRIGGER_KEYWORDS = ("作業", "考試", "檢查", "check")


def _execute_scan_with_retry() -> list[dict[str, Any]]:
    """執行雙軌掃描；若遭遇 SessionExpiredError，嘗試自動重登並重試一次。"""
    global _cookie_warning_sent
    try:
        alerts = scraper.scan_all_sources()
        _cookie_warning_sent = False
        return alerts
    except scraper.SessionExpiredError as exc:
        logger.warning("偵測到 Session 過期：%s，準備嘗試自動重登...", exc)
        try:
            auth_helper.refresh_cool_cookie()
            alerts = scraper.scan_all_sources()
            _cookie_warning_sent = False
            return alerts
        except Exception as auth_exc:
            logger.error("自動重登或重試掃描失敗：%s", auth_exc)
            if not _cookie_warning_sent:
                line_service.push_warning(
                    "⚠️ NTU COOL Session Cookie 已失效，且自動重登失敗！\n"
                    f"原因：{auth_exc}\n"
                    "請手動更新 .env 中的 COOL_SESSION_COOKIE。"
                )
                _cookie_warning_sent = True
            raise


def run_scan(send_push: bool = True) -> dict[str, Any]:
    """安全執行一次完整掃描（含併發鎖保護），並視需要發送合併 LINE Push 推播。"""
    with _scan_lock:
        try:
            alerts = _execute_scan_with_retry()
            pushed = False
            if send_push and alerts:
                pushed = line_service.push_alert(alerts)
            return {
                "ok": True,
                "new_count": len(alerts),
                "pushed": pushed,
                "alerts": alerts,
            }
        except scraper.SessionExpiredError as exc:
            return {"ok": False, "error": f"Session 失效：{exc}", "new_count": 0, "pushed": False}
        except Exception as exc:
            logger.exception("掃描過程發生未預期錯誤：%s", exc)
            return {"ok": False, "error": str(exc), "new_count": 0, "pushed": False}


def _compute_next_run_time(now: datetime | None = None) -> tuple[datetime, str]:
    """依據課表警戒時段計算下一次輪詢時間，確保準時切換高頻模式。"""
    current = now or config.get_taipei_now()
    if config.is_in_class_schedule(current):
        return (
            current + timedelta(seconds=config.CLASS_POLL_INTERVAL_SECONDS),
            f"上課高頻警戒模式（每 {config.CLASS_POLL_INTERVAL_SECONDS} 秒）",
        )

    default_next = current + timedelta(seconds=config.NORMAL_POLL_INTERVAL_SECONDS)

    # 若接下來 20 分鐘內剛好進入上課時段，提前在開課當下喚醒切換為 30 秒高頻輪詢
    weekday_map = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today_key = weekday_map[current.weekday()]
    for start_str, _ in config.CLASS_SCHEDULE.get(today_key, []):
        hour_str, minute_str = start_str.split(":")
        slot_start = datetime.combine(
            current.date(),
            time(hour=int(hour_str), minute=int(minute_str)),
            tzinfo=config.TAIPEI_TZ,
        )
        if current < slot_start < default_next:
            return slot_start, "即將進入上課時段（準時切換高頻）"

    return default_next, "一般省電模式（每 20 分鐘）"


def _scheduled_poll_job() -> None:
    """排程器執行的定期輪詢任務，結束後動態安排下一次執行時間。"""
    try:
        result = run_scan(send_push=True)
        logger.info(
            "排程掃描完成：新項目 %d 筆，已推播=%s",
            result.get("new_count", 0),
            result.get("pushed", False),
        )
    finally:
        _schedule_next_poll()


def _schedule_next_poll() -> None:
    """安排下一次動態輪詢任務。"""
    if _scheduler is None or not _scheduler.running:
        return
    next_run, mode_label = _compute_next_run_time()
    logger.debug("下一次輪詢時間：%s（%s）", next_run.strftime("%Y-%m-%d %H:%M:%S"), mode_label)
    _scheduler.add_job(
        _scheduled_poll_job,
        trigger="date",
        run_date=next_run,
        id=_POLL_JOB_ID,
        replace_existing=True,
    )


def start_scheduler() -> BackgroundScheduler:
    """初始化資料庫並啟動 APScheduler 智慧動態排程器。"""
    global _scheduler
    database.init_db()

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone=config.TAIPEI_TZ)
    _scheduler.start()

    # 啟動後 5 秒執行第一次掃描，之後依課表自動切換 30 秒 / 20 分鐘頻率
    first_run = config.get_taipei_now() + timedelta(seconds=5)
    _scheduler.add_job(
        _scheduled_poll_job,
        trigger="date",
        run_date=first_run,
        id=_POLL_JOB_ID,
        replace_existing=True,
    )
    logger.info("APScheduler 動態輪詢排程器已啟動。")
    return _scheduler


@app.route("/ping", methods=["GET"])
def ping():
    """健康檢查端點（供外部定時器如 cron-job.org 呼叫防止休眠）。"""
    now = config.get_taipei_now()
    return jsonify(
        {
            "status": "ok",
            "service": "COOL-LINE",
            "taipei_time": now.isoformat(),
            "in_class_schedule": config.is_in_class_schedule(now),
        }
    )


@app.route("/trigger", methods=["GET"])
def trigger():
    """外部觸發檢查端點（可由 cron-job.org 定時呼叫並兼作防休眠心跳）。"""
    result = run_scan(send_push=True)
    status_code = 200 if result.get("ok") else 500
    return jsonify(
        {
            "status": "ok" if result.get("ok") else "error",
            "new_count": result.get("new_count", 0),
            "pushed": result.get("pushed", False),
            "error": result.get("error"),
        }
    ), status_code


@app.route("/callback", methods=["POST"])
def callback():
    """接收 LINE Messaging API Webhook 事件。"""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("LINE Webhook 簽章驗證失敗。")
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent) -> None:
    """處理使用者傳送的文字訊息，支援即時查詢與免費 Reply API 回覆 Flex 卡片。"""
    text = (event.message.text or "").strip()
    text_lower = text.lower()

    if any(keyword in text_lower for keyword in _TRIGGER_KEYWORDS):
        # 立即執行一次掃描（先不主動 Push，改透過免費 Reply API 一次回覆使用者）
        scan_result = run_scan(send_push=False)
        upcoming_items = database.get_upcoming_items()
        flex_card = line_service.build_todo_flex_message(upcoming_items)

        messages: list[Any] = []
        if not scan_result.get("ok"):
            messages.append(
                TextMessage(
                    text=f"⚠️ 本次即時掃描遇到狀況：{scan_result.get('error')}\n以下為目前本地資料庫紀錄："
                )
            )
        elif scan_result.get("new_count", 0) > 0:
            messages.append(
                TextMessage(
                    text=f"🔍 即時掃描完成！剛發現 {scan_result['new_count']} 筆新動態，已同步更新待辦清單："
                )
            )

        messages.append(flex_card)
        line_service.reply_message(event.reply_token, messages)
    else:
        line_service.reply_message(
            event.reply_token,
            [
                TextMessage(
                    text=(
                        "👋 我是 COOL-LINE 課程小幫手！\n"
                        "輸入「作業」、「考試」、「檢查」或「check」，即可免費即時查詢未到期任務卡片。"
                    )
                )
            ],
        )


if __name__ == "__main__":
    start_scheduler()
    port = int(os.getenv("PORT", "5000"))
    # 使用 use_reloader=False 避免 Flask reloader 造成 APScheduler 被啟動兩次
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
