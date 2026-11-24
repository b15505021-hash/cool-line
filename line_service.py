"""LINE Messaging API v3 服務模組：負責合併主動推播（含快捷鍵與外部瀏覽器連結）與免費回覆 Flex 卡片。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    FlexContainer,
    FlexMessage,
    MessageAction,
    MessagingApi,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)

import config

logger = logging.getLogger(__name__)

_TYPE_LABEL_MAP = {
    "quiz": "⚡ 考試／測驗",
    "assignment": "📝 課程作業",
    "file": "📁 新增檔案",
    "announcement": "📢 課程公告",
}


def to_external_browser_url(url: str | None) -> str:
    """加上 openExternalBrowser=1，強制 LINE 以手機預設瀏覽器（Safari/Chrome）開啟 NTU COOL。"""
    base = (url or "").strip() or config.COOL_BASE_URL
    if "openExternalBrowser=1" in base:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}openExternalBrowser=1"


def build_default_quick_reply() -> QuickReply:
    """建立鍵盤上方的常用快捷鍵列（Quick Reply）。"""
    shortcuts = [
        ("📋 滑動總覽", "清單"),
        ("📅 本月日曆", "日曆"),
        ("📝 只看作業", "作業"),
        ("⚡ 只看考試", "考試"),
    ]
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label=label, text=text))
            for label, text in shortcuts
        ]
    )


def _get_messaging_api() -> MessagingApi:
    """建立 LINE MessagingApi 用戶端實例。"""
    if not config.LINE_CHANNEL_ACCESS_TOKEN:
        raise RuntimeError("尚未設定 LINE_CHANNEL_ACCESS_TOKEN。")
    configuration = Configuration(access_token=config.LINE_CHANNEL_ACCESS_TOKEN)
    api_client = ApiClient(configuration)
    return MessagingApi(api_client)


def _format_due_time(due_at: str | None) -> str:
    """將 ISO-8601 時間字串轉換為台北時間可讀格式。"""
    if not due_at:
        return "無明確期限"
    try:
        dt = datetime.fromisoformat(due_at.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        taipei_dt = dt.astimezone(config.TAIPEI_TZ)
        return taipei_dt.strftime("%m/%d (%a) %H:%M")
    except ValueError:
        return due_at


def _clean_course_name(course_name: str) -> str:
    """精簡過長的中英文並列課名，提升手機閱讀體驗。"""
    return (course_name or "未知課程").split(" ")[0].strip()


def _format_alert_block(alert: dict[str, Any], index: int) -> str:
    """將單筆通知項目格式化為簡潔文字區塊（避免課名重複，並附外部瀏覽器連結）。"""
    item_type = alert.get("item_type", "announcement")
    type_label = _TYPE_LABEL_MAP.get(item_type, "🔔 新動態")
    course_name = _clean_course_name(alert.get("course_name", "未知課程"))
    raw_title = alert.get("raw_title") or alert.get("title", "未命名項目")
    due_at = alert.get("due_at")
    summary = alert.get("summary")
    url = alert.get("url")

    is_exam = item_type == "quiz"
    prefix = "❗❗❗ " if is_exam else ""
    suffix = " ❗❗❗" if is_exam else ""

    lines = [
        f"{index}. {prefix}[{type_label}] {course_name}{suffix}",
        f"   📌 {raw_title}",
    ]
    if due_at:
        lines.append(f"   ⏰ 截止：{_format_due_time(due_at)}")
    if summary:
        lines.append(f"   💡 {summary}")
    if url:
        lines.append(f"   🔗 {to_external_browser_url(url)}")
    return "\n".join(lines)


def push_alert(alerts_list: list[dict[str, Any]], *, custom_header: str | None = None) -> bool:
    """將多筆通知合併為「單一則」Push 訊息發送（含考試緊急標頭與底部快捷鍵）。"""
    if not alerts_list:
        return False

    if not config.LINE_USER_ID:
        logger.error("未設定 LINE_USER_ID，無法發送 LINE 主動推播。")
        return False

    has_exam = any(a.get("item_type") == "quiz" for a in alerts_list)
    if custom_header:
        header = custom_header
    elif has_exam:
        header = (
            "❗❗❗❗❗❗❗❗❗❗\n"
            "🚨‼️【緊急考試通知】‼️🚨\n"
            f"❗❗ 偵測到 {len(alerts_list)} 筆新動態（含考試）❗❗\n"
            "❗❗❗❗❗❗❗❗❗❗"
        )
    else:
        header = f"🚨 NTU COOL 偵測到 {len(alerts_list)} 筆新動態！\n" + ("─" * 18)

    blocks = [_format_alert_block(alert, idx) for idx, alert in enumerate(alerts_list, start=1)]
    full_text = header + "\n\n" + "\n\n".join(blocks)

    if len(full_text) > 4800:
        full_text = full_text[:4780] + "\n\n...（內容過長，其餘項目請至 NTU COOL 查看）"

    try:
        api = _get_messaging_api()
        api.push_message(
            PushMessageRequest(
                to=config.LINE_USER_ID,
                messages=[
                    TextMessage(
                        text=full_text,
                        quick_reply=build_default_quick_reply(),
                    )
                ],
            )
        )
        logger.info("已成功發送合併 LINE Push 推播（共 %d 筆項目）。", len(alerts_list))
        return True
    except Exception as exc:
        logger.error("LINE Push 推播失敗：%s", exc)
        return False


def push_warning(message: str) -> bool:
    """發送系統警告訊息給使用者。"""
    if not config.LINE_USER_ID:
        logger.error("未設定 LINE_USER_ID，無法發送警告通知：%s", message)
        return False
    try:
        api = _get_messaging_api()
        api.push_message(
            PushMessageRequest(
                to=config.LINE_USER_ID,
                messages=[TextMessage(text=message, quick_reply=build_default_quick_reply())],
            )
        )
        return True
    except Exception as exc:
        logger.error("發送 LINE 警告通知失敗：%s", exc)
        return False


def build_todo_flex_message(items: list[dict[str, Any]]) -> FlexMessage:
    """將未到期的作業與測驗打包成 LINE Flex Message 視覺化卡片。"""
    body_contents: list[dict[str, Any]] = []

    if not items:
        body_contents.append(
            {
                "type": "text",
                "text": "🎉 太棒了！目前沒有尚未到期的作業或測驗。",
                "wrap": True,
                "size": "sm",
                "color": "#4A5568",
            }
        )
    else:
        for idx, item in enumerate(items[:10]):
            if idx > 0:
                body_contents.append({"type": "separator", "margin": "md"})

            item_type = item.get("item_type", "assignment")
            badge_text = "⚡ 測驗" if item_type == "quiz" else "📝 作業"
            badge_color = "#D97706" if item_type == "quiz" else "#2563EB"
            due_display = _format_due_time(item.get("due_at"))

            body_contents.append(
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md" if idx > 0 else "none",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": badge_text,
                                    "size": "xs",
                                    "weight": "bold",
                                    "color": badge_color,
                                    "flex": 0,
                                },
                                {
                                    "type": "text",
                                    "text": _clean_course_name(item.get("course_name", "未知課程")),
                                    "size": "xs",
                                    "color": "#718096",
                                    "margin": "sm",
                                    "wrap": False,
                                },
                            ],
                        },
                        {
                            "type": "text",
                            "text": item.get("title", "未命名項目"),
                            "size": "sm",
                            "weight": "bold",
                            "color": "#1A202C",
                            "wrap": True,
                        },
                        {
                            "type": "text",
                            "text": f"⏰ 截止：{due_display}",
                            "size": "xs",
                            "color": "#E53E3E",
                        },
                    ],
                }
            )

    bubble_dict: dict[str, Any] = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1E3A8A",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": "📚 NTU COOL 待辦清單",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#FFFFFF",
                },
                {
                    "type": "text",
                    "text": f"尚有 {len(items)} 項未到期作業／測驗",
                    "size": "xs",
                    "color": "#BFDBFE",
                    "margin": "xs",
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": body_contents,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#2563EB",
                    "height": "sm",
                    "action": {
                        "type": "uri",
                        "label": "前往 NTU COOL",
                        "uri": to_external_browser_url(config.COOL_BASE_URL),
                    },
                }
            ],
        },
    }

    return FlexMessage(
        alt_text=f"NTU COOL 待辦清單（共 {len(items)} 項）",
        contents=FlexContainer.from_dict(bubble_dict),
        quick_reply=build_default_quick_reply(),
    )


def reply_message(reply_token: str, messages: list[Any]) -> bool:
    """透過免費的 LINE Reply API 回覆使用者訊息。"""
    try:
        api = _get_messaging_api()
        api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=messages,
            )
        )
        return True
    except Exception as exc:
        logger.error("LINE Reply 回覆失敗：%s", exc)
        return False
