"""AI 重點摘要模組：使用 Google Gemini API 濃縮冗長課程公告。"""

from __future__ import annotations

import logging
import re

from google import genai

import config

logger = logging.getLogger(__name__)


def _fallback_summary(subject: str, body: str) -> str:
    """當 Gemini API 未設定或呼叫失敗時的降級摘要：截取前 100 字純文字。"""
    cleaned_body = re.sub(r"\s+", " ", (body or "")).strip()
    if not cleaned_body:
        cleaned_body = (subject or "（無內容）").strip()
    snippet = cleaned_body[:100]
    if len(cleaned_body) > 100:
        snippet += "..."
    return f"📌 {snippet}"


def summarize_announcement(subject: str, body: str) -> str:
    """使用 gemini-2.5-flash 將課程公告濃縮為不超過 60 字的繁體中文重點。

    格式目標：「📌 重點摘要｜⏰ 截止/考試時間｜⚠️ 注意事項」
    若未設定 GEMINI_API_KEY 或呼叫失敗，自動降級為截取前 100 字純文字。
    """
    if not config.GEMINI_API_KEY:
        logger.warning("未設定 GEMINI_API_KEY，改用純文字降級摘要。")
        return _fallback_summary(subject, body)

    prompt = (
        "你是台大 NTU COOL 課程助理。請將以下課程公告或通知信濃縮為「不超過 60 個繁體中文字」的精簡重點。\n"
        "請嚴格依照此格式輸出單行內容：\n"
        "📌 重點摘要｜⏰ 截止/考試時間｜⚠️ 注意事項\n"
        "（若無時間或注意事項，該欄填「無」即可；請勿輸出多餘解釋或 Markdown 符號，總字數含符號請壓在 60 字以內。）\n\n"
        f"主旨：{subject}\n"
        f"內文：{(body or '')[:2000]}"
    )

    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = (response.text or "").strip()
        if not text:
            return _fallback_summary(subject, body)
        return re.sub(r"\s+", " ", text)
    except Exception as exc:
        logger.warning("Gemini 摘要失敗，改用降級機制：%s", exc)
        return _fallback_summary(subject, body)
