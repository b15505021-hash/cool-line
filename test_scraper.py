"""單獨測試 NTU COOL Cookie 連線與本學期課程列表抓取的測試腳本。"""

from __future__ import annotations

import argparse
import sys

import config
import scraper


def main() -> int:
    parser = argparse.ArgumentParser(description="測試 NTU COOL API 連線並列出進行中課程")
    parser.add_argument(
        "--cookie",
        type=str,
        default="",
        help="選填：直接指定 _normandy_session 值（未指定時會讀取 .env 的 COOL_SESSION_COOKIE）",
    )
    args = parser.parse_args()

    if args.cookie.strip():
        config.update_cool_session_cookie(args.cookie.strip())

    if not config.get_cool_session_cookie():
        manual_cookie = input("請貼上從瀏覽器取得的 _normandy_session Cookie 值：").strip()
        if not manual_cookie:
            print("❌ 未提供 Cookie，無法進行測試。")
            return 1
        config.update_cool_session_cookie(manual_cookie)

    print("🔍 正在連線至 NTU COOL API...")
    try:
        courses = scraper.fetch_active_courses()
    except scraper.SessionExpiredError as exc:
        print(f"❌ Session 無效或已過期：{exc}")
        print("請重新登入 https://cool.ntu.edu.tw 並更新 _normandy_session。")
        return 1
    except Exception as exc:
        print(f"❌ 連線發生錯誤：{exc}")
        return 1

    if not courses:
        print("⚠️ 連線成功，但未找到任何進行中（active）課程。")
        return 0

    print(f"\n✅ 連線成功！共找到 {len(courses)} 門本學期進行中課程：\n")
    for idx, course in enumerate(courses, start=1):
        course_id = course.get("id")
        course_code = course.get("course_code", "無課號")
        name = course.get("name", "未命名課程")
        print(f"{idx:>2}. [ID: {course_id}] ({course_code}) {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
