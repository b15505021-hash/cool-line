"""自動建立並綁定 LINE 底部常駐 6 格圖文選單（Rich Menu）。

透過 Playwright 渲染高解析度 SVG + Noto Sans TC 選單圖片（1200x810），
在 Windows 與 GitHub Actions Ubuntu 皆能穩定產出無亂碼圖檔並設為預設選單。
"""

from __future__ import annotations

import logging
import requests
from playwright.sync_api import sync_playwright

import config

logger = logging.getLogger(__name__)

RICH_MENU_NAME = "COOL-LINE_RICH_MENU_V1"
LINE_API_BASE = "https://api.line.me/v2/bot"
LINE_DATA_API_BASE = "https://api-data.line.me/v2/bot"

RICH_MENU_HTML = """<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="UTF-8" />
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@700;900&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: 1200px;
    height: 810px;
    overflow: hidden;
    font-family: 'Noto Sans TC', 'Microsoft JhengHei', 'PingFang TC', sans-serif;
    background: #0f172a;
    padding: 16px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: repeat(2, 1fr);
    gap: 14px;
    width: 100%;
    height: 100%;
  }
  .cell {
    border-radius: 26px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
    position: relative;
    border: 2px solid rgba(255,255,255,0.14);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.2);
    color: #ffffff;
    text-align: center;
  }
  .c1 { background: linear-gradient(145deg, #0f766e, #0d9488); }
  .c2 { background: linear-gradient(145deg, #1d4ed8, #2563eb); }
  .c3 { background: linear-gradient(145deg, #b45309, #d97706); }
  .c4 { background: linear-gradient(145deg, #4338ca, #6366f1); }
  .c5 { background: linear-gradient(145deg, #047857, #10b981); }
  .c6 { background: linear-gradient(145deg, #1e293b, #334155); }
  .icon-box {
    width: 96px;
    height: 96px;
    border-radius: 24px;
    background: rgba(255,255,255,0.16);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 18px;
  }
  svg { width: 54px; height: 54px; stroke: #fff; stroke-width: 2.2; fill: none; stroke-linecap: round; stroke-linejoin: round; }
  .title { font-size: 40px; font-weight: 900; letter-spacing: 1px; margin-bottom: 8px; }
  .sub { font-size: 23px; font-weight: 700; color: rgba(255,255,255,0.85); }
</style>
</head>
<body>
  <div class="grid">
    <div class="cell c1">
      <div class="icon-box">
        <svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="13" y2="16"/></svg>
      </div>
      <div class="title">滑動總覽</div>
      <div class="sub">全部・作業・考試・日曆</div>
    </div>
    <div class="cell c2">
      <div class="icon-box">
        <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><circle cx="12" cy="15" r="2"/></svg>
      </div>
      <div class="title">本月日曆</div>
      <div class="sub">一覽整月死線分布</div>
    </div>
    <div class="cell c3">
      <div class="icon-box">
        <svg viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
      </div>
      <div class="title">立即爬 COOL</div>
      <div class="sub">手動喚醒雲端同步</div>
    </div>
    <div class="cell c4">
      <div class="icon-box">
        <svg viewBox="0 0 24 24"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
      </div>
      <div class="title">本週戰況</div>
      <div class="sub">未來 7 天截止清單</div>
    </div>
    <div class="cell c5">
      <div class="icon-box">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
      </div>
      <div class="title">新增待辦</div>
      <div class="sub">選日期加入個人提醒</div>
    </div>
    <div class="cell c6">
      <div class="icon-box">
        <svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      </div>
      <div class="title">開啟 COOL</div>
      <div class="sub">外部瀏覽器直達首頁</div>
    </div>
  </div>
</body>
</html>
"""


def _render_rich_menu_png() -> bytes:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            try:
                browser = p.chromium.launch(headless=True, channel="chrome")
            except Exception:
                browser = p.chromium.launch(headless=True, channel="msedge")
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 810}, device_scale_factor=1)
            page.set_content(RICH_MENU_HTML, wait_until="networkidle", timeout=20000)
            try:
                page.evaluate("() => document.fonts && document.fonts.ready")
            except Exception:
                pass
            return page.screenshot(type="png")
        finally:
            browser.close()


def ensure_rich_menu(force: bool = False) -> str | None:
    """檢查並自動安裝預設 6 格圖文選單，若已存在同名選單則直接略過。"""
    token = (config.LINE_CHANNEL_ACCESS_TOKEN or "").strip()
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}"}

    try:
        cur_res = requests.get(f"{LINE_API_BASE}/user/all/richmenu", headers=headers, timeout=10)
        if cur_res.status_code == 200 and not force:
            cur_id = cur_res.json().get("richMenuId", "")
            if cur_id:
                meta_res = requests.get(f"{LINE_API_BASE}/richmenu/{cur_id}", headers=headers, timeout=10)
                if meta_res.status_code == 200 and meta_res.json().get("name") == RICH_MENU_NAME:
                    logger.info("LINE Rich Menu 已是最新版 (%s)，無須重建。", cur_id)
                    return cur_id

        logger.info("正在產生並上傳 LINE 6 格常駐圖文選單 (Rich Menu)...")
        png_bytes = _render_rich_menu_png()

        menu_spec = {
            "size": {"width": 1200, "height": 810},
            "selected": True,
            "name": RICH_MENU_NAME,
            "chatBarText": "📂 開啟／收合 COOL 快捷選單",
            "areas": [
                {
                    "bounds": {"x": 0, "y": 0, "width": 400, "height": 405},
                    "action": {"type": "message", "label": "滑動總覽", "text": "清單"},
                },
                {
                    "bounds": {"x": 400, "y": 0, "width": 400, "height": 405},
                    "action": {"type": "message", "label": "本月日曆", "text": "日曆"},
                },
                {
                    "bounds": {"x": 800, "y": 0, "width": 400, "height": 405},
                    "action": {"type": "message", "label": "立即爬 COOL", "text": "立即爬 COOL"},
                },
                {
                    "bounds": {"x": 0, "y": 405, "width": 400, "height": 405},
                    "action": {"type": "message", "label": "本週戰況", "text": "本週"},
                },
                {
                    "bounds": {"x": 400, "y": 405, "width": 400, "height": 405},
                    "action": {
                        "type": "datetimepicker",
                        "label": "新增待辦",
                        "data": "action=pick_date",
                        "mode": "datetime",
                    },
                },
                {
                    "bounds": {"x": 800, "y": 405, "width": 400, "height": 405},
                    "action": {
                        "type": "uri",
                        "label": "開啟 NTU COOL",
                        "uri": "https://cool.ntu.edu.tw/?openExternalBrowser=1",
                    },
                },
            ],
        }

        create_res = requests.post(
            f"{LINE_API_BASE}/richmenu",
            headers={**headers, "Content-Type": "application/json"},
            json=menu_spec,
            timeout=15,
        )
        create_res.raise_for_status()
        new_id = create_res.json()["richMenuId"]

        img_res = requests.post(
            f"{LINE_DATA_API_BASE}/richmenu/{new_id}/content",
            headers={**headers, "Content-Type": "image/png"},
            data=png_bytes,
            timeout=25,
        )
        img_res.raise_for_status()

        bind_res = requests.post(
            f"{LINE_API_BASE}/user/all/richmenu/{new_id}",
            headers=headers,
            timeout=15,
        )
        bind_res.raise_for_status()

        list_res = requests.get(f"{LINE_API_BASE}/richmenu/list", headers=headers, timeout=10)
        if list_res.status_code == 200:
            for item in list_res.json().get("richmenus", []):
                old_id = item.get("richMenuId")
                if old_id and old_id != new_id and str(item.get("name", "")).startswith("COOL-LINE_RICH_MENU"):
                    requests.delete(f"{LINE_API_BASE}/richmenu/{old_id}", headers=headers, timeout=10)

        logger.info("✅ 已成功啟用 LINE 底部 6 格常駐圖文選單：%s", new_id)
        return new_id
    except Exception as exc:
        logger.warning("設定 LINE Rich Menu 略過（不影響主流程）：%s", exc)
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_rich_menu(force=True)
