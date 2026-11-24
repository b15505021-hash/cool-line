"""雙軌資料擷取模組：主軌透過 Canvas REST API 輪詢 NTU COOL，副軌透過 Gmail IMAP 讀取通知信。"""

from __future__ import annotations

import email
import hashlib
import imaplib
import logging
from email.header import decode_header
from email.message import Message
from typing import Any

import requests
from bs4 import BeautifulSoup

import ai_summarizer
import config
import database

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


class SessionExpiredError(Exception):
    """當 NTU COOL Session Cookie 過期或無效（HTTP 401/403）時拋出。"""


def _build_cool_headers() -> dict[str, str]:
    """組裝帶有最新 _normandy_session 的 HTTP 請求標頭。"""
    cookie = config.get_cool_session_cookie()
    if not cookie:
        raise SessionExpiredError("尚未設定 COOL_SESSION_COOKIE。")
    return {
        "Cookie": f"_normandy_session={cookie}",
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }


def _cool_get_json(url: str, *, allow_disabled_tab: bool = False) -> Any:
    """向 NTU COOL Canvas API 發送 GET 請求並解析 JSON。

    Args:
        url: 完整 API URL。
        allow_disabled_tab: 若為 True，遇到單一課程停用功能頁籤造成的 403/404 時回傳空串列，
            但若回應明確顯示未登入（unauthenticated）或 HTTP 401，仍會拋出 SessionExpiredError。
    """
    resp = requests.get(url, headers=_build_cool_headers(), timeout=REQUEST_TIMEOUT)

    if resp.status_code == 401:
        raise SessionExpiredError(f"NTU COOL 回傳 HTTP 401（Cookie 已失效）: {url}")

    if resp.status_code == 403:
        body_lower = resp.text.lower()
        if not allow_disabled_tab or "unauthenticated" in body_lower or "login" in body_lower:
            raise SessionExpiredError(f"NTU COOL 回傳 HTTP 403（權限不足或 Cookie 已失效）: {url}")
        logger.debug("課程端點可能被教師隱藏（HTTP 403），略過：%s", url)
        return []

    if resp.status_code == 404 and allow_disabled_tab:
        logger.debug("課程端點不存在或未開放（HTTP 404），略過：%s", url)
        return []

    resp.raise_for_status()
    return resp.json()


def fetch_active_courses() -> list[dict[str, Any]]:
    """取得目前學期進行中（active）的課程清單。"""
    url = f"{config.COOL_API_BASE_URL}/courses?enrollment_state=active&per_page=50"
    data = _cool_get_json(url, allow_disabled_tab=False)
    if not isinstance(data, list):
        return []
    # 過濾掉沒有名稱的異常課程物件
    return [c for c in data if isinstance(c, dict) and c.get("id") and c.get("name")]


def poll_canvas_api() -> list[dict[str, Any]]:
    """主軌：輪詢 NTU COOL Canvas REST API，回傳尚未通知過的新項目清單。"""
    new_alerts: list[dict[str, Any]] = []
    courses = fetch_active_courses()

    for course in courses:
        course_id = course["id"]
        course_name = course.get("name", f"課程 {course_id}")

        # 1. 線上測驗（專抓沒寄信的課堂突襲小考）
        quizzes = _cool_get_json(
            f"{config.COOL_API_BASE_URL}/courses/{course_id}/quizzes?per_page=20",
            allow_disabled_tab=True,
        )
        if isinstance(quizzes, list):
            for quiz in quizzes:
                quiz_id = quiz.get("id")
                if not quiz_id:
                    continue
                uid = f"quiz_{quiz_id}"
                if not database.is_notified(uid):
                    title = quiz.get("title") or "未命名測驗"
                    due_at = quiz.get("due_at") or quiz.get("lock_at")
                    database.mark_as_notified(uid, course_name, "quiz", title, due_at)
                    new_alerts.append(
                        {
                            "uid": uid,
                            "course_name": course_name,
                            "item_type": "quiz",
                            "title": title,
                            "due_at": due_at,
                            "url": quiz.get("html_url"),
                            "summary": None,
                        }
                    )

        # 2. 作業與死線
        assignments = _cool_get_json(
            f"{config.COOL_API_BASE_URL}/courses/{course_id}/assignments?per_page=20",
            allow_disabled_tab=True,
        )
        if isinstance(assignments, list):
            for assign in assignments:
                assign_id = assign.get("id")
                if not assign_id:
                    continue
                uid = f"assign_{assign_id}"
                if not database.is_notified(uid):
                    title = assign.get("name") or "未命名作業"
                    due_at = assign.get("due_at")
                    database.mark_as_notified(uid, course_name, "assignment", title, due_at)
                    new_alerts.append(
                        {
                            "uid": uid,
                            "course_name": course_name,
                            "item_type": "assignment",
                            "title": title,
                            "due_at": due_at,
                            "url": assign.get("html_url"),
                            "summary": None,
                        }
                    )

        # 3. 最新上傳檔案（專抓只傳檔案不建作業的隱藏任務）
        files = _cool_get_json(
            f"{config.COOL_API_BASE_URL}/courses/{course_id}/files"
            "?sort=created_at&order=desc&per_page=5",
            allow_disabled_tab=True,
        )
        if isinstance(files, list):
            for file_obj in files:
                file_id = file_obj.get("id")
                if not file_id:
                    continue
                uid = f"file_{file_id}"
                if not database.is_notified(uid):
                    title = file_obj.get("display_name") or file_obj.get("filename") or "未命名檔案"
                    database.mark_as_notified(uid, course_name, "file", title, None)
                    new_alerts.append(
                        {
                            "uid": uid,
                            "course_name": course_name,
                            "item_type": "file",
                            "title": title,
                            "due_at": None,
                            "url": file_obj.get("url"),
                            "summary": None,
                        }
                    )

    return new_alerts


def _decode_mime_header(raw_value: str | None) -> str:
    """解碼 RFC 2047 MIME 編碼的信件主旨或標頭。"""
    if not raw_value:
        return ""
    parts: list[str] = []
    for chunk, encoding in decode_header(raw_value):
        if isinstance(chunk, bytes):
            charset = encoding or "utf-8"
            try:
                parts.append(chunk.decode(charset, errors="replace"))
            except LookupError:
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _extract_email_body(msg: Message) -> str:
    """從 Email Message 中擷取純文字內容（優先 text/plain，若僅有 HTML 則以 BeautifulSoup 清除標籤）。"""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" in disposition.lower():
                continue

            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")

            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload is not None:
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

    if plain_parts:
        raw_text = "\n".join(plain_parts).strip()
        # 有些信件的 text/plain 內仍夾雜簡易 HTML，保險起見再清理一次
        return BeautifulSoup(raw_text, "html.parser").get_text(separator="\n", strip=True)

    if html_parts:
        soup = BeautifulSoup("\n".join(html_parts), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    return ""


def poll_gmail_imap() -> list[dict[str, Any]]:
    """副軌：透過 Gmail IMAP 抓取來自 ntu-cool@cool.ntu.edu.tw 的未讀通知信。"""
    if not (config.GMAIL_ADDRESS and config.GMAIL_APP_PASSWORD):
        logger.debug("未設定 Gmail IMAP 帳號或應用程式密碼，略過副軌讀信。")
        return []

    new_alerts: list[dict[str, Any]] = []
    mail: imaplib.IMAP4_SSL | None = None

    try:
        mail = imaplib.IMAP4_SSL(config.GMAIL_IMAP_HOST)
        mail.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        mail.select("INBOX")

        status, message_ids = mail.search(
            None,
            f'(UNSEEN FROM "{config.COOL_NOTIFICATION_SENDER}")',
        )
        if status != "OK" or not message_ids or not message_ids[0]:
            return []

        for msg_num in message_ids[0].split():
            fetch_status, msg_data = mail.fetch(msg_num, "(RFC822)")
            if fetch_status != "OK" or not msg_data:
                continue

            raw_bytes = None
            for item in msg_data:
                if isinstance(item, tuple) and len(item) >= 2:
                    raw_bytes = item[1]
                    break
            if not raw_bytes:
                continue

            msg = email.message_from_bytes(raw_bytes)
            subject = _decode_mime_header(msg.get("Subject")) or "NTU COOL 通知信"
            message_id = (msg.get("Message-ID") or "").strip()
            body = _extract_email_body(msg)

            uid_seed = message_id or f"{subject}|{msg.get('Date', '')}"
            uid_hash = hashlib.sha256(uid_seed.encode("utf-8")).hexdigest()[:16]
            uid = f"mail_{uid_hash}"

            if not database.is_notified(uid):
                summary = ai_summarizer.summarize_announcement(subject, body)
                database.mark_as_notified(uid, "NTU COOL 通知信", "announcement", subject, None)
                new_alerts.append(
                    {
                        "uid": uid,
                        "course_name": "NTU COOL 通知信",
                        "item_type": "announcement",
                        "title": subject,
                        "due_at": None,
                        "url": config.COOL_BASE_URL,
                        "summary": summary,
                    }
                )
    except Exception as exc:
        logger.warning("Gmail IMAP 讀取失敗：%s", exc)
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass

    return new_alerts


def scan_all_sources() -> list[dict[str, Any]]:
    """執行雙軌掃描（Canvas API 主軌 + Gmail IMAP 副軌），回傳所有新發現項目。"""
    alerts = poll_canvas_api()
    mail_alerts = poll_gmail_imap()
    alerts.extend(mail_alerts)
    return alerts
