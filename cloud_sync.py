"""雲端／排程專用同步腳本：登入 NTU COOL 過濾「已繳交作業」，同步至 GAS 並發送早晚死線提醒。"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

import auth_helper
import config
import line_service
import scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_iso(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _format_taipei_display(dt: datetime) -> str:
    taipei_dt = dt.astimezone(config.TAIPEI_TZ)
    return taipei_dt.strftime("%m/%d (%a) %H:%M")


def fetch_unsubmitted_tasks() -> list[dict[str, Any]]:
    """透過 Canvas API 取得所有「尚未截止且尚未繳交」的作業與測驗。"""
    try:
        courses = scraper.fetch_active_courses()
    except scraper.SessionExpiredError:
        logger.info("Session 無效或尚未登入，啟動 Playwright 自動登入台大 SSO...")
        auth_helper.refresh_cool_cookie()
        courses = scraper.fetch_active_courses()

    now_taipei = config.get_taipei_now()
    today_start = datetime(
        now_taipei.year, now_taipei.month, now_taipei.day, 0, 0, 0, tzinfo=config.TAIPEI_TZ
    )

    unsubmitted: list[dict[str, Any]] = []

    for course in courses:
        cid = course["id"]
        cname = course.get("name", f"課程 {cid}")
        short_cname = cname.split(" ")[0][:12]

        # 1. 抓取作業並直接帶入個人繳交狀態 (include[]=submission)
        assignments = scraper._cool_get_json(
            f"{config.COOL_API_BASE_URL}/courses/{cid}/assignments?include[]=submission&per_page=50",
            allow_disabled_tab=True,
        )
        if isinstance(assignments, list):
            for a in assignments:
                due_dt = _parse_iso(a.get("due_at"))
                if due_dt is None or due_dt < today_start:
                    continue

                submission = a.get("submission") or {}
                workflow_state = submission.get("workflow_state", "unsubmitted")
                submitted_at = submission.get("submitted_at")
                # 若已繳交或已批改，直接略過！
                if workflow_state in ("submitted", "graded", "pending_review") or submitted_at:
                    continue

                raw_title = (a.get("name") or "未命名作業").strip()
                is_exam = any(
                    kw in raw_title.lower()
                    for kw in ("quiz", "exam", "midterm", "小考", "期中考", "期末考", "隨堂考", "測驗", "考試")
                )
                direct_url = line_service.to_external_browser_url(a.get("html_url") or config.COOL_BASE_URL)
                unsubmitted.append(
                    {
                        "id": f"canvas_assign_{a['id']}",
                        "title": f"[{short_cname}] {raw_title}"[:36],
                        "raw_title": raw_title,
                        "category": "exam" if is_exam else "homework",
                        "dueMs": int(due_dt.timestamp() * 1000),
                        "dueDisplay": _format_taipei_display(due_dt),
                        "done": False,
                        "url": direct_url,
                        "course_name": cname,
                    }
                )

        # 2. 抓取線上測驗（同時檢查是否已有提交紀錄）
        quizzes = scraper._cool_get_json(
            f"{config.COOL_API_BASE_URL}/courses/{cid}/quizzes?per_page=30",
            allow_disabled_tab=True,
        )
        if isinstance(quizzes, list):
            for q in quizzes:
                due_dt = _parse_iso(q.get("due_at") or q.get("lock_at"))
                if due_dt is None or due_dt < today_start:
                    continue
                raw_title = (q.get("title") or "未命名測驗").strip()
                direct_url = line_service.to_external_browser_url(q.get("html_url") or config.COOL_BASE_URL)
                unsubmitted.append(
                    {
                        "id": f"canvas_quiz_{q['id']}",
                        "title": f"[{short_cname}] {raw_title}"[:36],
                        "raw_title": raw_title,
                        "category": "exam",
                        "dueMs": int(due_dt.timestamp() * 1000),
                        "dueDisplay": _format_taipei_display(due_dt),
                        "done": False,
                        "url": direct_url,
                        "course_name": cname,
                    }
                )

    unsubmitted.sort(key=lambda x: x["dueMs"])
    return unsubmitted


def sync_to_gas_webhook(tasks: list[dict[str, Any]]) -> bool:
    """將真實未繳交清單（以及備援 Token）同步給 GAS Webhook。"""
    gas_url = os.getenv("GAS_WEBHOOK_URL", "").strip()
    if not gas_url:
        logger.info("未設定 GAS_WEBHOOK_URL，略過同步至 GAS。")
        return False

    payload: dict[str, Any] = {
        "sync_source": "canvas_api",
        "sync_secret": config.LINE_USER_ID,
        # 自動幫 GAS 補齊雲端屬性中的 Token，避免重貼程式碼忘記填 Token 而已讀不回
        "line_token": config.LINE_CHANNEL_ACCESS_TOKEN,
        "gemini_key": config.GEMINI_API_KEY,
        "tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "category": t["category"],
                "dueMs": t["dueMs"],
                "dueDisplay": t["dueDisplay"],
                "done": False,
                "url": t.get("url") or line_service.to_external_browser_url(config.COOL_BASE_URL),
            }
            for t in tasks
        ],
    }
    resp = requests.post(gas_url, json=payload, timeout=20, allow_redirects=True)
    logger.info("同步至 GAS 回應狀態：%s (%s)", resp.status_code, resp.text[:40])
    return resp.status_code == 200


def main() -> int:
    try:
        tasks = fetch_unsubmitted_tasks()
        logger.info("共偵測到 %d 筆未過期且尚未繳交的作業／測驗。", len(tasks))
        for t in tasks[:10]:
            logger.info(" - [%s] %s (%s)", t["category"], t["title"], t["dueDisplay"])

        sync_to_gas_webhook(tasks)

        # 檢查今日截止的未繳交項目，依時段發送「早安死線早報」或「睡前最後搶救提醒」
        now_taipei = config.get_taipei_now()
        today_str = now_taipei.strftime("%m/%d")
        today_label = now_taipei.strftime("%m/%d (%a)")
        is_night = now_taipei.hour >= 21

        due_today = [t for t in tasks if t["dueDisplay"].startswith(today_str)]
        if due_today and config.LINE_CHANNEL_ACCESS_TOKEN and config.LINE_USER_ID:
            has_exam = any(t["category"] == "exam" for t in due_today)
            if has_exam:
                header = (
                    "❗❗❗❗❗❗❗❗❗❗\n"
                    f"🚨‼️【今日緊急死線提醒（{today_label}）】‼️🚨\n"
                    f"❗❗ 尚有 {len(due_today)} 項今日截止且未完成（含考試）❗❗\n"
                    "❗❗❗❗❗❗❗❗❗❗"
                )
            elif is_night:
                header = (
                    f"🔥【睡前最後搶救提醒（{today_label}）】\n"
                    f"距離今日死線只剩最後一小時，尚有 {len(due_today)} 項作業未繳交！\n"
                    + ("─" * 18)
                )
            else:
                header = (
                    f"☀️【早安死線提醒（{today_label}）】\n"
                    f"今日共有 {len(due_today)} 項作業尚未在 NTU COOL 繳交：\n"
                    + ("─" * 18)
                )

            alerts = [
                {
                    "course_name": t["course_name"],
                    "item_type": "quiz" if t["category"] == "exam" else "assignment",
                    "raw_title": t["raw_title"],
                    "title": t["title"],
                    "due_at": datetime.fromtimestamp(
                        t["dueMs"] / 1000, tz=timezone.utc
                    ).isoformat(),
                    "url": t["url"],
                    "summary": "尚未繳交，點下方連結可直接用外部瀏覽器開啟該作業頁！",
                }
                for t in due_today
            ]
            line_service.push_alert(alerts, custom_header=header)

        return 0
    except Exception as exc:
        logger.exception("雲端同步失敗：%s", exc)
        if config.LINE_CHANNEL_ACCESS_TOKEN and config.LINE_USER_ID:
            line_service.push_warning(f"⚠️ COOL-LINE 自動登入同步失敗：\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
