"""雲端／排程專用同步腳本：登入 NTU COOL 過濾「已繳交作業」，同步至 GAS 並發送早晚死線提醒。"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import auth_helper
import config
import line_service
import rich_menu
import scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_EXAM_KEYWORDS = ("quiz", "exam", "midterm", "final", "小考", "期中考", "期末考", "隨堂考", "測驗", "考試")
_NON_EXAM_SURVEY_KEYWORDS = (
    "參訪",
    "報名",
    "問卷",
    "調查",
    "心得",
    "回饋",
    "意見",
    "簽到",
    "點名",
    "分組",
    "survey",
    "feedback",
    "questionnaire",
    "attendance",
    "signup",
    "sign-up",
)


def _is_real_exam(raw_title: str, quiz_type: str = "", default_exam: bool = False) -> bool:
    """判斷是否為真正的考試／小考（排除用 Quiz 製作的參訪報名表或問卷）。"""
    lower = raw_title.lower()
    if quiz_type in ("survey", "graded_survey"):
        return False
    if any(kw in lower for kw in _NON_EXAM_SURVEY_KEYWORDS):
        return False
    if default_exam:
        return True
    return any(kw in lower for kw in _EXAM_KEYWORDS)


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


def fetch_recent_files(courses: list[dict[str, Any]], hours: int = 16) -> list[dict[str, Any]]:
    """偵測過去 N 小時內教授默默上傳至 COOL /files 的新講義或檔案。"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent_files: list[dict[str, Any]] = []

    for course in courses:
        cid = course["id"]
        cname = course.get("name", f"課程 {cid}")
        files = scraper._cool_get_json(
            f"{config.COOL_API_BASE_URL}/courses/{cid}/files?sort=created_at&order=desc&per_page=5",
            allow_disabled_tab=True,
        )
        if not isinstance(files, list):
            continue
        for f in files:
            created_dt = _parse_iso(f.get("created_at") or f.get("updated_at"))
            if created_dt is None or created_dt < cutoff:
                continue
            fname = f.get("display_name") or f.get("filename") or "未命名檔案"
            file_url = f.get("url") or f"{config.COOL_BASE_URL}/courses/{cid}/files"
            recent_files.append(
                {
                    "course_name": cname,
                    "item_type": "file",
                    "raw_title": fname,
                    "title": fname,
                    "due_at": None,
                    "url": line_service.to_external_browser_url(file_url),
                    "summary": "教授剛上傳的新課程檔案／講義（點下方連結直接開啟）",
                }
            )
    return recent_files


def fetch_unsubmitted_tasks() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """透過 Canvas API 取得 (尚未繳交作業測驗清單, 近期新上傳檔案清單)。"""
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
    submitted_quiz_ids: set[Any] = set()
    seen_quiz_ids: set[Any] = set()

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
                quiz_id = a.get("quiz_id")
                # 若已繳交或已批改，記錄 quiz_id 並直接略過！
                if workflow_state in ("submitted", "graded", "pending_review") or submitted_at:
                    if quiz_id:
                        submitted_quiz_ids.add(quiz_id)
                    continue

                raw_title = (a.get("name") or "未命名作業").strip()
                is_exam = _is_real_exam(raw_title, default_exam=bool(quiz_id))
                if quiz_id:
                    seen_quiz_ids.add(quiz_id)
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

        # 2. 抓取線上測驗（排除已繳交、排除重複項目、排除問卷／參訪報名表）
        quizzes = scraper._cool_get_json(
            f"{config.COOL_API_BASE_URL}/courses/{cid}/quizzes?per_page=30",
            allow_disabled_tab=True,
        )
        if isinstance(quizzes, list):
            for q in quizzes:
                qid = q.get("id")
                if qid in submitted_quiz_ids or qid in seen_quiz_ids:
                    continue
                due_dt = _parse_iso(q.get("due_at") or q.get("lock_at"))
                if due_dt is None or due_dt < today_start:
                    continue
                raw_title = (q.get("title") or "未命名測驗").strip()
                is_exam = _is_real_exam(
                    raw_title,
                    quiz_type=str(q.get("quiz_type") or ""),
                    default_exam=True,
                )
                direct_url = line_service.to_external_browser_url(q.get("html_url") or config.COOL_BASE_URL)
                unsubmitted.append(
                    {
                        "id": f"canvas_quiz_{q['id']}",
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

    unsubmitted.sort(key=lambda x: x["dueMs"])
    recent_files = fetch_recent_files(courses, hours=16)
    return unsubmitted, recent_files


def sync_to_gas_webhook(
    tasks: list[dict[str, Any]] | None,
    mark_morning_date: str | None = None,
    mark_weekly_date: str | None = None,
) -> dict[str, str]:
    """將真實未繳交清單（以及備援 Token / 日期標記）同步給 GAS Webhook。"""
    gas_url = os.getenv("GAS_WEBHOOK_URL", "").strip()
    if not gas_url:
        logger.info("未設定 GAS_WEBHOOK_URL，略過同步至 GAS。")
        return {}

    payload: dict[str, Any] = {
        "sync_source": "canvas_api",
        "sync_secret": config.LINE_USER_ID,
        # 自動幫 GAS 補齊雲端屬性中的 Token，避免重貼程式碼忘記填 Token 而已讀不回
        "line_token": config.LINE_CHANNEL_ACCESS_TOKEN,
        "gemini_key": config.GEMINI_API_KEY,
    }
    if tasks is not None:
        payload["tasks"] = [
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
        ]
    if mark_morning_date:
        payload["mark_morning_date"] = mark_morning_date
    if mark_weekly_date:
        payload["mark_weekly_date"] = mark_weekly_date

    resp = requests.post(gas_url, json=payload, timeout=20, allow_redirects=True)
    logger.info("同步至 GAS 回應狀態：%s (%s)", resp.status_code, resp.text[:80])
    if resp.status_code == 200:
        try:
            data = resp.json()
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except ValueError:
            pass
    return {}


def mark_gas_push_dates(morning_date: str | None = None, weekly_date: str | None = None) -> None:
    """僅回寫今日早報或週報已推播標記，不覆蓋任務清單。"""
    try:
        sync_to_gas_webhook(None, mark_morning_date=morning_date, mark_weekly_date=weekly_date)
    except Exception as exc:
        logger.warning("回寫 GAS 推播日期標記失敗（不影響主流程）：%s", exc)


def main() -> int:
    try:
        tasks, recent_files = fetch_unsubmitted_tasks()
        logger.info("共偵測到 %d 筆未繳交作業／測驗、%d 筆新上傳檔案。", len(tasks), len(recent_files))
        for t in tasks[:10]:
            logger.info(" - [%s] %s (%s)", t["category"], t["title"], t["dueDisplay"])

        sync_state = sync_to_gas_webhook(tasks)

        # 自動檢查並安裝 LINE 底部 6 格常駐圖文選單（若已是最新版會直接略過）
        rich_menu.ensure_rich_menu(force=False)

        now_taipei = config.get_taipei_now()
        today_date = now_taipei.date()
        today_iso = today_date.isoformat()
        two_days_date = today_date + timedelta(days=2)
        today_label = now_taipei.strftime("%m/%d (%a)")
        two_days_label = (now_taipei + timedelta(days=2)).strftime("%m/%d (%a)")

        is_manual = os.getenv("TRIGGER_EVENT") == "workflow_dispatch"
        # 嚴格區分時段：排程若因 GitHub Actions 排隊飄移到下午（11:00～17:59），不再重發早安報平安
        is_morning_window = 5 <= now_taipei.hour < 11
        is_sunday_digest_window = now_taipei.weekday() == 6 and 18 <= now_taipei.hour < 21
        is_night_window = now_taipei.hour >= 21

        already_sent_morning = sync_state.get("last_morning_date") == today_iso
        already_sent_weekly = sync_state.get("last_weekly_date") == today_iso

        def _task_taipei_date(task: dict[str, Any]):
            return datetime.fromtimestamp(
                task["dueMs"] / 1000, tz=timezone.utc
            ).astimezone(config.TAIPEI_TZ).date()

        # 分支 A：每週日晚上 20:00 本週戰況總覽（未來 7 天所有未繳交作業與考試）
        if not is_manual and is_sunday_digest_window and not already_sent_weekly:
            if config.LINE_CHANNEL_ACCESS_TOKEN and config.LINE_USER_ID:
                week_tasks = [t for t in tasks if 0 <= (_task_taipei_date(t) - today_date).days <= 7]
                if week_tasks:
                    lines: list[str] = []
                    for idx, t in enumerate(week_tasks[:12], start=1):
                        days_left = (_task_taipei_date(t) - today_date).days
                        days_hint = "今日截止" if days_left == 0 else f"剩 {days_left} 天"
                        badge = "⚡ 考試" if t["category"] == "exam" else "📝 作業"
                        lines.append(
                            f"{idx}. [{badge}] {t['title']}\n   ⏰ {t['dueDisplay']}（{days_hint}）"
                        )
                    more_note = f"\n（尚有 {len(week_tasks) - 12} 項未列出）" if len(week_tasks) > 12 else ""
                    weekly_msg = (
                        f"📊【週日晚間・未來 7 天戰況總覽（{today_label}）】\n"
                        f"未來一週共有 {len(week_tasks)} 項未繳交作業／測驗，幫您提早排好進度：\n"
                        + ("─" * 18)
                        + "\n"
                        + "\n".join(lines)
                        + more_note
                        + "\n\n點下方選單「📋 滑動總覽」或「📅 本月日曆」可隨時檢視並點擊直達 COOL！"
                    )
                else:
                    weekly_msg = (
                        f"📊【週日晚間・未來 7 天戰況總覽（{today_label}）】\n"
                        "恭喜！未來一週（7 天內）目前完全沒有未繳交的作業或考試，祝您新的一週順心！"
                    )
                line_service.push_warning(weekly_msg)
                mark_gas_push_dates(weekly_date=today_iso)
            return 0

        # 分支 B：早上早報時段 / 晚上睡前搶救 / 下午僅推新檔案 / 手動觸發
        can_send_morning_alerts = is_manual or (is_morning_window and not already_sent_morning)
        due_today = (
            [t for t in tasks if _task_taipei_date(t) == today_date]
            if (can_send_morning_alerts or is_night_window)
            else []
        )
        due_in_two_days = (
            [t for t in tasks if _task_taipei_date(t) == two_days_date]
            if can_send_morning_alerts
            else []
        )

        alerts: list[dict[str, Any]] = [
            {
                "course_name": t["course_name"],
                "item_type": "quiz" if t["category"] == "exam" else "assignment",
                "raw_title": t["raw_title"],
                "title": t["title"],
                "due_at": datetime.fromtimestamp(
                    t["dueMs"] / 1000, tz=timezone.utc
                ).isoformat(),
                "url": t["url"],
                "summary": "🔥 今日截止且尚未繳交，點下方連結可直接用外部瀏覽器開啟該作業頁！",
            }
            for t in due_today
        ]
        alerts.extend(
            [
                {
                    "course_name": t["course_name"],
                    "item_type": "quiz" if t["category"] == "exam" else "assignment",
                    "raw_title": t["raw_title"],
                    "title": f"【2天後截止】{t['title']}",
                    "due_at": datetime.fromtimestamp(
                        t["dueMs"] / 1000, tz=timezone.utc
                    ).isoformat(),
                    "url": t["url"],
                    "summary": "⏳ 距離截止只剩 2 天！尚未在 NTU COOL 繳交，提醒您提早安排時間完成。",
                }
                for t in due_in_two_days
            ]
        )
        alerts.extend(recent_files[:5])

        if alerts and config.LINE_CHANNEL_ACCESS_TOKEN and config.LINE_USER_ID:
            has_exam_today = any(t["category"] == "exam" for t in due_today)
            extra_parts: list[str] = []
            if due_in_two_days:
                extra_parts.append(f"{len(due_in_two_days)} 項 2 天後（{two_days_label}）截止")
            if recent_files:
                extra_parts.append(f"{len(recent_files)} 份新檔案")
            extra_suffix = f" ＋ {'、'.join(extra_parts)}" if extra_parts else ""

            if has_exam_today:
                header = (
                    "❗❗❗❗❗❗❗❗❗❗\n"
                    f"🚨‼️【今日緊急死線提醒（{today_label}）】‼️🚨\n"
                    f"❗❗ 尚有 {len(due_today)} 項今日截止（含考試）{extra_suffix} ❗❗\n"
                    "❗❗❗❗❗❗❗❗❗❗"
                )
            elif is_night_window and due_today:
                header = (
                    f"🔥【睡前最後搶救提醒（{today_label}）】\n"
                    f"距離今日死線只剩最後一小時，尚有 {len(due_today)} 項作業未繳交！\n"
                    + ("─" * 18)
                )
            elif due_today:
                header = (
                    f"☀️【早安死線提醒（{today_label}）】\n"
                    f"今日共有 {len(due_today)} 項未繳交作業{extra_suffix}：\n"
                    + ("─" * 18)
                )
            elif due_in_two_days:
                file_suffix = f"（另含 {len(recent_files)} 份新檔案）" if recent_files else ""
                header = (
                    f"⏰【作業／測驗截止前 2 天預告（{two_days_label} 截止）】\n"
                    f"尚有 {len(due_in_two_days)} 項未繳交項目將於兩天後截止{file_suffix}，提醒您提早準備：\n"
                    + ("─" * 18)
                )
            else:
                header = (
                    f"📁【NTU COOL 新上傳講義／檔案通知（{today_label}）】\n"
                    f"偵測到 {len(recent_files)} 份最新上傳檔案：\n"
                    + ("─" * 18)
                )

            line_service.push_alert(alerts, custom_header=header)
            if is_morning_window:
                mark_gas_push_dates(morning_date=today_iso)
        elif (
            (is_manual or (is_morning_window and not already_sent_morning))
            and config.LINE_CHANNEL_ACCESS_TOKEN
            and config.LINE_USER_ID
        ):
            if is_manual:
                title_line = f"✅【NTU COOL 雲端爬蟲更新完成（{today_label}）】"
            else:
                title_line = f"☀️【早安報平安（{today_label}）】"

            upcoming_lines: list[str] = []
            for idx, t in enumerate(tasks[:3], start=1):
                due_d = _task_taipei_date(t)
                days_left = (due_d - today_date).days
                days_hint = f"剩 {days_left} 天" if days_left > 0 else "今日截止"
                badge = "⚡ 考試" if t["category"] == "exam" else "📝 作業"
                upcoming_lines.append(
                    f"{idx}. [{badge}] {t['title']}\n   ⏳ {t['dueDisplay']}（{days_hint}）"
                )

            if upcoming_lines:
                body = (
                    f"{title_line}\n"
                    "今天與兩天後皆沒有截止項目，機器人持續為您監控中！\n\n"
                    f"📌 最近 {len(upcoming_lines)} 筆即將截止的未繳交項目：\n"
                    + "\n".join(upcoming_lines)
                    + f"\n\n點下方選單「滑動總覽」可查看全部 {len(tasks)} 項清單！"
                )
            else:
                body = (
                    f"{title_line}\n"
                    "目前 NTU COOL 上完全沒有尚未繳交的作業或考試，祝您今天順心！"
                )
            line_service.push_warning(body)
            if is_morning_window:
                mark_gas_push_dates(morning_date=today_iso)

        return 0
    except Exception as exc:
        logger.exception("雲端同步失敗：%s", exc)
        if config.LINE_CHANNEL_ACCESS_TOKEN and config.LINE_USER_ID:
            line_service.push_warning(f"⚠️ COOL-LINE 自動登入同步失敗：\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
