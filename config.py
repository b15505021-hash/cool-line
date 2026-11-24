"""設定載入與課表警戒時段管理模組。"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv, set_key

# 專案根目錄與 .env 路徑
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DB_PATH = BASE_DIR / "cool_tracker.db"

# 載入 .env 環境變數（若已存在系統環境變數，以 .env 或系統變數為主）
load_dotenv(dotenv_path=ENV_PATH)

# 台北時區 (UTC+8)
TAIPEI_TZ = timezone(timedelta(hours=8))

# NTU COOL 與 Gmail 相關常數
COOL_BASE_URL = "https://cool.ntu.edu.tw"
COOL_API_BASE_URL = f"{COOL_BASE_URL}/api/v1"
GMAIL_IMAP_HOST = "imap.gmail.com"
COOL_NOTIFICATION_SENDER = "ntu-cool@cool.ntu.edu.tw"

# 各項環境變數讀取
COOL_SESSION_COOKIE: str = os.getenv("COOL_SESSION_COOKIE", "").strip()
NTU_STUDENT_ID: str = os.getenv("NTU_STUDENT_ID", "").strip()
NTU_PASSWORD: str = os.getenv("NTU_PASSWORD", "").strip()

LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "").strip()
LINE_USER_ID: str = os.getenv("LINE_USER_ID", "").strip()

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "").strip()
GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "").strip()

# 每週上課高頻警戒時段設定
# Key 為英文星期縮寫（Mon, Tue, Wed, Thu, Fri, Sat, Sun）
# Value 為 (開始時間, 結束時間) 的 24 小時制字串列表
CLASS_SCHEDULE: dict[str, list[tuple[str, str]]] = {
    "Mon": [("13:20", "15:10")],
    "Thu": [("13:20", "14:10")],
}

# 輪詢頻率設定（秒）
CLASS_POLL_INTERVAL_SECONDS = 30        # 上課高頻警戒時段：每 30 秒檢查一次
NORMAL_POLL_INTERVAL_SECONDS = 20 * 60  # 非上課時段：每 20 分鐘檢查一次

# 星期索引對應英文縮寫（datetime.weekday(): 0=Mon ... 6=Sun）
_WEEKDAY_MAP = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse_hhmm(hhmm: str) -> time:
    """將 HH:MM 字串轉為 datetime.time 物件。"""
    hour_str, minute_str = hhmm.strip().split(":")
    return time(hour=int(hour_str), minute=int(minute_str))


def get_taipei_now() -> datetime:
    """取得目前台北時間 (UTC+8)。"""
    return datetime.now(TAIPEI_TZ)


def is_in_class_schedule(now: datetime | None = None) -> bool:
    """判斷指定時間（預設為現在台北時間）是否位於 CLASS_SCHEDULE 上課時段內。"""
    current = now or get_taipei_now()
    day_key = _WEEKDAY_MAP[current.weekday()]
    slots = CLASS_SCHEDULE.get(day_key, [])
    current_time = current.time().replace(tzinfo=None)

    for start_str, end_str in slots:
        start_t = _parse_hhmm(start_str)
        end_t = _parse_hhmm(end_str)
        if start_t <= current_time <= end_t:
            return True
    return False


def get_cool_session_cookie() -> str:
    """取得目前記憶體中最新的 COOL_SESSION_COOKIE。"""
    return COOL_SESSION_COOKIE


def update_cool_session_cookie(new_cookie: str) -> None:
    """更新記憶體、環境變數與 .env 檔案中的 COOL_SESSION_COOKIE。"""
    global COOL_SESSION_COOKIE
    cleaned = new_cookie.strip()
    COOL_SESSION_COOKIE = cleaned
    os.environ["COOL_SESSION_COOKIE"] = cleaned

    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    set_key(str(ENV_PATH), "COOL_SESSION_COOKIE", cleaned)
