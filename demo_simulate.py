"""期末 Demo Day 一鍵模擬腳本：模擬突襲小考與 Gemini 公告濃縮，並發送真實 LINE 推播。"""

from __future__ import annotations

import sys
from datetime import timedelta

import ai_summarizer
import config
import database
import line_service


def main() -> int:
    print("🚀 開始執行 COOL-LINE Demo 模擬展示...\n")

    if not config.LINE_CHANNEL_ACCESS_TOKEN or not config.LINE_USER_ID:
        print("❌ 請先在 .env 中設定 LINE_CHANNEL_ACCESS_TOKEN 與 LINE_USER_ID。")
        return 1

    now = config.get_taipei_now()
    quiz_due = (now + timedelta(minutes=10)).isoformat()
    demo_suffix = now.strftime("%Y%m%d%H%M%S")

    # 1. 模擬「偵測到課堂突襲小考」
    quiz_alert = {
        "uid": f"demo_quiz_{demo_suffix}",
        "course_name": "工程數學（一）",
        "item_type": "quiz",
        "title": "第 12 週課堂突襲小考（限時 10 分鐘作答）",
        "due_at": quiz_due,
        "url": f"{config.COOL_BASE_URL}",
        "summary": None,
    }

    # 寫入本地資料庫，方便後續在 LINE 輸入「作業」或「考試」直接測試 Reply Flex 卡片
    database.mark_as_notified(
        item_uid=quiz_alert["uid"],
        course_name=quiz_alert["course_name"],
        item_type="quiz",
        title=f"[Demo] {quiz_alert['title']}",
        due_at=quiz_due,
    )

    # 2. 模擬「助教公告經 Gemini 濃縮」
    raw_subject = "【重要公告】下週期中考考場異動與補交作業說明"
    raw_body = (
        "各位同學好：\n"
        "原訂於本週五（11/27）下午 13:20 在綜合教學館 102 教室舉行的期中考試，"
        "因人數較多且冷氣維修，考場將全面更換至「博雅教學館 101 室」，請務必提早 15 分鐘入場就座。"
        "考試範圍為第 1 章至第 5 章，可以攜帶一張雙面 A4 手寫大抄與無程式功能計算機，嚴禁使用手機或智慧手錶。"
        "另外，第三次作業（HW3）的繳交期限配合期中考順延至下週一（11/30）晚上 23:59，請同學上傳單一 PDF 檔至 COOL 作業區，逾期將扣總分 20%。\n"
        "祝大家考試順利！\n課程助教 敬上"
    )

    print("🤖 正在呼叫 Gemini 2.5 Flash 濃縮助教公告...")
    summarized_text = ai_summarizer.summarize_announcement(raw_subject, raw_body)
    print(f"📝 濃縮結果：{summarized_text}\n")

    announcement_alert = {
        "uid": f"demo_mail_{demo_suffix}",
        "course_name": "計算機概論",
        "item_type": "announcement",
        "title": raw_subject,
        "due_at": None,
        "url": f"{config.COOL_BASE_URL}",
        "summary": summarized_text,
    }

    # 3. 合併推播至手機 LINE
    print("📲 正在合併推播至您的 LINE...")
    success = line_service.push_alert([quiz_alert, announcement_alert])

    if success:
        print("✅ 模擬推播發送成功！請檢查您的手機 LINE 訊息。")
        print("💡 提示：您現在也可以在 LINE 聊天室傳送「考試」或「作業」，測試免費 Reply API 的 Flex 卡片回覆！")
        return 0

    print("❌ 模擬推播發送失敗，請確認 .env 中的 LINE 設定是否正確。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
