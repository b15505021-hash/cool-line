"""建置《COOL-LINE 一鍵安裝精靈》獨立單一 HTML 檔案（桌面版與開源版同步產出）。

執行後會將純 JS SealedBox 加密程式庫與所有乾淨的 COOL-LINE 原始碼內嵌進單一
`.html` 檔案（無須安裝 Python、無外部 CDN 相依、支援 file:// 本機雙擊開啟），
並自動檢查確定未夾帶任何 .env 個人機密後，同時輸出至：
  1. C:\\Users\\User\\COOL-LINE\\COOL-LINE_一鍵安裝精靈.html
  2. C:\\Users\\User\\Desktop\\COOL-LINE_一鍵安裝精靈.html
"""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENDOR_DIR = BASE_DIR / "vendor"
OUTPUT_REPO_HTML = BASE_DIR / "COOL-LINE_一鍵安裝精靈.html"
OUTPUT_DESKTOP_HTML = Path(r"C:\Users\User\Desktop\COOL-LINE_一鍵安裝精靈.html")

# 嚴格使用檔案白名單，絕對不讀取 .env / *.db / __pycache__ / .git
REPO_FILE_WHITELIST: list[str] = [
    "requirements.txt",
    ".gitignore",
    ".env.example",
    "config.py",
    "database.py",
    "scraper.py",
    "ai_summarizer.py",
    "line_service.py",
    "auth_helper.py",
    "cloud_sync.py",
    "app.py",
    "test_scraper.py",
    "demo_simulate.py",
    "README.md",
    "gas/Code.gs",
    ".github/workflows/daily_cool.yml",
]


def load_clean_repo_files() -> dict[str, str]:
    """讀取開源專案白名單檔案內容。"""
    files: dict[str, str] = {}
    for rel_path in REPO_FILE_WHITELIST:
        abs_path = BASE_DIR / rel_path
        if not abs_path.is_file():
            raise FileNotFoundError(f"找不到白名單必要檔案：{abs_path}")
        files[rel_path] = abs_path.read_text(encoding="utf-8")

    # 二次防呆檢查：確認 Code.gs 範本維持佔位字元，未含任何寫死金鑰
    code_gs = files["gas/Code.gs"]
    required_placeholders = [
        "'請填入您的_LINE_CHANNEL_ACCESS_TOKEN'",
        "'請填入您的_LINE_USER_ID'",
        "'請填入您的_GEMINI_API_KEY'",
        "'請填入您的_GITHUB_REPO'",
        "'請填入您的_GITHUB_PAT'",
    ]
    for marker in required_placeholders:
        if marker not in code_gs:
            raise ValueError(f"gas/Code.gs 缺少預期佔位字元 {marker}，請先確認範本乾淨後再建置。")

    return files


def load_vendor_scripts() -> tuple[str, str]:
    """載入本地快取的純 JS TweetNaCl 與 SealedBox 程式庫。"""
    nacl_path = VENDOR_DIR / "nacl-fast.min.js"
    sealedbox_path = VENDOR_DIR / "sealedbox.web.js"
    if not nacl_path.is_file() or not sealedbox_path.is_file():
        raise FileNotFoundError(
            "找不到 vendor/nacl-fast.min.js 或 vendor/sealedbox.web.js，請先下載純 JS 套件。"
        )
    return (
        nacl_path.read_text(encoding="utf-8"),
        sealedbox_path.read_text(encoding="utf-8"),
    )


def assert_no_leaked_secrets(html_content: str) -> None:
    """掃描產出 HTML 是否意外夾帶本機 .env 中的任何機密字串。"""
    env_path = BASE_DIR / ".env"
    if not env_path.is_file():
        return

    leaks: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if len(val) >= 6 and val in html_content:
            leaks.append(key)

    if leaks:
        raise RuntimeError(
            f"❌ 安全攔截：產出的安裝精靈意外包含本機 .env 機密欄位：{', '.join(leaks)}"
        )


def escape_json_for_html_script(payload: dict[str, str]) -> str:
    """將 JSON 安全跳脫以嵌入 HTML <script type="application/json"> 標籤內。"""
    raw_json = json.dumps(payload, ensure_ascii=False)
    return raw_json.replace("</", "\\u003c/").replace("<!--", "\\u003c!--")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>COOL-LINE 一鍵安裝精靈｜台大 NTU COOL 零成本雙雲端 LINE 助理</title>
  <style>
    :root {
      --bg: #f3f6fb;
      --card: #ffffff;
      --text: #14213d;
      --muted: #5b6780;
      --border: #dce4f0;
      --primary: #0f766e;
      --primary-dark: #0b5c56;
      --primary-soft: #e6f6f4;
      --accent: #2563eb;
      --accent-soft: #eff6ff;
      --warn: #b45309;
      --warn-bg: #fffbeb;
      --warn-border: #fde68a;
      --danger: #b91c1c;
      --danger-bg: #fef2f2;
      --danger-border: #fecaca;
      --ok: #15803d;
      --ok-bg: #f0fdf4;
      --ok-border: #bbf7d0;
      --radius: 16px;
      --shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", -apple-system, BlinkMacSystemFont, sans-serif;
      background: linear-gradient(180deg, #e8f3f8 0%, var(--bg) 320px);
      color: var(--text);
      line-height: 1.65;
      padding-bottom: 64px;
    }

    .topbar {
      background: linear-gradient(135deg, #0f172a 0%, #0f766e 60%, #1d4ed8 100%);
      color: #fff;
      padding: 20px 24px 24px;
      box-shadow: 0 6px 24px rgba(15, 23, 42, 0.16);
    }
    .topbar-inner {
      max-width: 980px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }
    .brand h1 {
      margin: 0;
      font-size: 1.45rem;
      font-weight: 800;
      letter-spacing: 0.3px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand p {
      margin: 4px 0 0;
      font-size: 0.92rem;
      color: rgba(255, 255, 255, 0.86);
    }
    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .pill-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.14);
      border: 1px solid rgba(255, 255, 255, 0.25);
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 600;
    }
    .btn-ghost-light {
      background: rgba(255, 255, 255, 0.14);
      color: #fff;
      border: 1px solid rgba(255, 255, 255, 0.3);
      padding: 6px 13px;
      border-radius: 999px;
      cursor: pointer;
      font-size: 0.82rem;
      font-weight: 600;
      transition: background 0.15s;
    }
    .btn-ghost-light:hover { background: rgba(255, 255, 255, 0.26); }

    .container {
      max-width: 980px;
      margin: -14px auto 0;
      padding: 0 16px;
    }

    /* Stepper */
    .stepper {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 12px;
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 8px;
      margin-bottom: 20px;
    }
    .step-tab {
      border: 1px solid transparent;
      background: #f8fafc;
      border-radius: 12px;
      padding: 10px 8px;
      cursor: pointer;
      text-align: center;
      transition: all 0.18s;
      color: var(--muted);
      font-family: inherit;
    }
    .step-tab:hover { background: #eff6ff; color: var(--text); }
    .step-tab.active {
      background: var(--primary-soft);
      border-color: var(--primary);
      color: var(--primary-dark);
      font-weight: 700;
    }
    .step-tab.done .step-num {
      background: var(--ok);
      color: #fff;
    }
    .step-num {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 24px;
      height: 24px;
      border-radius: 999px;
      background: #cbd5e1;
      color: #fff;
      font-size: 0.78rem;
      font-weight: 700;
      margin-bottom: 4px;
    }
    .step-tab.active .step-num {
      background: var(--primary);
    }
    .step-title {
      display: block;
      font-size: 0.8rem;
      line-height: 1.25;
    }

    /* Card */
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 28px;
      display: none;
      animation: fadeIn 0.2s ease-out;
    }
    .card.active { display: block; }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .card-header {
      border-bottom: 1px solid var(--border);
      padding-bottom: 16px;
      margin-bottom: 20px;
    }
    .card-header .tag {
      display: inline-block;
      background: var(--primary-soft);
      color: var(--primary-dark);
      font-size: 0.78rem;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 999px;
      margin-bottom: 8px;
    }
    .card-header h2 {
      margin: 0;
      font-size: 1.38rem;
      color: var(--text);
    }
    .card-header p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 0.95rem;
    }

    /* Callouts & Guides */
    .callout {
      border-radius: 12px;
      padding: 14px 16px;
      margin: 14px 0;
      font-size: 0.92rem;
      border: 1px solid;
    }
    .callout-info { background: var(--accent-soft); border-color: #bfdbfe; color: #1e3a8a; }
    .callout-warn { background: var(--warn-bg); border-color: var(--warn-border); color: #78350f; }
    .callout-ok { background: var(--ok-bg); border-color: var(--ok-border); color: #14532d; }
    .callout-danger { background: var(--danger-bg); border-color: var(--danger-border); color: #7f1d1d; }

    .arch-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
      margin: 18px 0;
    }
    .arch-box {
      border: 1px solid var(--border);
      background: #f8fafc;
      border-radius: 12px;
      padding: 16px;
    }
    .arch-box .icon { font-size: 1.6rem; margin-bottom: 6px; }
    .arch-box h4 { margin: 0 0 6px; font-size: 1rem; color: var(--text); }
    .arch-box p { margin: 0; font-size: 0.86rem; color: var(--muted); }

    .guide-list {
      margin: 14px 0;
      padding: 0;
      list-style: none;
    }
    .guide-step {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      padding: 12px 14px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      margin-bottom: 10px;
    }
    .guide-badge {
      flex-shrink: 0;
      width: 26px;
      height: 26px;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      font-size: 0.84rem;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-top: 2px;
    }
    .guide-body { flex: 1; font-size: 0.93rem; }
    .guide-body strong.click {
      color: #1d4ed8;
      background: #dbeafe;
      padding: 1px 6px;
      border-radius: 5px;
    }
    .guide-body strong.copy {
      color: #065f46;
      background: #d1fae5;
      padding: 1px 6px;
      border-radius: 5px;
    }
    .guide-body strong.danger-txt {
      color: #991b1b;
      background: #fee2e2;
      padding: 1px 6px;
      border-radius: 5px;
    }

    /* Buttons */
    .btn-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 14px 0;
      align-items: center;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 11px 18px;
      border-radius: 10px;
      font-size: 0.94rem;
      font-weight: 700;
      font-family: inherit;
      cursor: pointer;
      text-decoration: none;
      border: 1px solid transparent;
      transition: all 0.15s;
    }
    .btn:disabled { opacity: 0.55; cursor: not-allowed; }
    .btn-primary { background: var(--primary); color: #fff; }
    .btn-primary:hover:not(:disabled) { background: var(--primary-dark); }
    .btn-accent { background: var(--accent); color: #fff; }
    .btn-accent:hover:not(:disabled) { background: #1d4ed8; }
    .btn-outline { background: #fff; color: var(--text); border-color: #cbd5e1; }
    .btn-outline:hover:not(:disabled) { background: #f1f5f9; }
    .btn-lg { padding: 14px 24px; font-size: 1.02rem; }

    /* Form Fields */
    .field {
      margin: 16px 0;
    }
    .field label {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: 700;
      font-size: 0.94rem;
      margin-bottom: 6px;
    }
    .input-wrap {
      position: relative;
      display: flex;
      gap: 8px;
    }
    .field input[type="text"],
    .field input[type="password"],
    .field input[type="url"] {
      width: 100%;
      padding: 11px 14px;
      border: 1.5px solid #cbd5e1;
      border-radius: 10px;
      font-size: 0.94rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: var(--text);
      background: #fff;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .field input:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.15);
    }
    .field input.valid { border-color: #16a34a; }
    .field input.invalid { border-color: #dc2626; }
    .field-msg {
      margin-top: 6px;
      font-size: 0.84rem;
      min-height: 18px;
    }
    .msg-ok { color: var(--ok); font-weight: 600; }
    .msg-warn { color: var(--warn); font-weight: 600; }
    .msg-err { color: var(--danger); font-weight: 600; }
    .msg-muted { color: var(--muted); }

    /* Code preview */
    pre.code-box {
      background: #0f172a;
      color: #e2e8f0;
      padding: 14px;
      border-radius: 10px;
      max-height: 260px;
      overflow: auto;
      font-size: 0.8rem;
      line-height: 1.45;
      display: none;
      margin-top: 10px;
    }
    pre.code-box.open { display: block; }

    /* Radio cards */
    .radio-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 8px;
    }
    .radio-card {
      border: 1.5px solid #cbd5e1;
      border-radius: 12px;
      padding: 12px 14px;
      cursor: pointer;
      display: flex;
      gap: 10px;
      align-items: flex-start;
      background: #fff;
    }
    .radio-card.selected {
      border-color: var(--primary);
      background: var(--primary-soft);
    }
    .radio-card input { margin-top: 4px; }
    .radio-card .r-title { font-weight: 700; font-size: 0.93rem; }
    .radio-card .r-desc { font-size: 0.82rem; color: var(--muted); }

    /* Deploy Terminal */
    .deploy-log {
      background: #0b1220;
      color: #d1d5db;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.84rem;
      padding: 16px;
      border-radius: 12px;
      margin-top: 16px;
      max-height: 300px;
      overflow-y: auto;
      display: none;
      line-height: 1.6;
      border: 1px solid #1e293b;
    }
    .deploy-log.open { display: block; }
    .log-ok { color: #4ade80; }
    .log-info { color: #60a5fa; }
    .log-warn { color: #fbbf24; }
    .log-err { color: #f87171; font-weight: 700; }

    /* GitHub User Card */
    .gh-profile {
      display: none;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      background: var(--ok-bg);
      border: 1px solid var(--ok-border);
      border-radius: 12px;
      margin-top: 12px;
    }
    .gh-profile.open { display: flex; }
    .gh-profile img { width: 42px; height: 42px; border-radius: 999px; border: 1px solid #cbd5e1; }

    /* Accordion */
    details.tip-box {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 14px;
      margin: 12px 0;
    }
    details.tip-box summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--text);
      font-size: 0.92rem;
    }
    details.tip-box .tip-content {
      margin-top: 10px;
      font-size: 0.89rem;
      color: var(--muted);
    }

    /* Nav footer inside card */
    .card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 26px;
      padding-top: 18px;
      border-top: 1px solid var(--border);
      flex-wrap: wrap;
    }

    .cmd-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
      margin-top: 12px;
    }
    .cmd-item {
      background: #fff;
      border: 1px solid #bbf7d0;
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 0.88rem;
    }
    .cmd-item code {
      background: #ecfdf5;
      color: #065f46;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 5px;
    }

    .status-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 10px 0 14px;
    }
    .chip {
      font-size: 0.8rem;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #f8fafc;
      color: var(--muted);
    }
    .chip.ok { background: var(--ok-bg); border-color: var(--ok-border); color: var(--ok); }
    .chip.warn { background: var(--warn-bg); border-color: var(--warn-border); color: var(--warn); }

    @media (max-width: 780px) {
      .stepper { grid-template-columns: repeat(3, 1fr); }
      .arch-grid, .radio-grid, .cmd-grid { grid-template-columns: 1fr; }
      .card { padding: 18px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <h1>🔔 COOL-LINE 一鍵安裝精靈</h1>
        <p>專為台大學生打造・建立你專屬的 0 元雙雲端 NTU COOL 死線警報 &amp; LINE 行事曆助理</p>
      </div>
      <div class="topbar-actions">
        <span class="pill-badge">🔒 本機加密直傳｜不經過第三方伺服器</span>
        <button type="button" class="btn-ghost-light" onclick="clearSavedDraft()">🧹 清除暫存資料</button>
      </div>
    </div>
  </header>

  <main class="container">
    <nav class="stepper" id="stepper" aria-label="安裝步驟">
      <button type="button" class="step-tab active" data-step="0" onclick="goStep(0)">
        <span class="step-num">0</span>
        <span class="step-title">歡迎與原理</span>
      </button>
      <button type="button" class="step-tab" data-step="1" onclick="goStep(1)">
        <span class="step-num">1</span>
        <span class="step-title">LINE 機器人</span>
      </button>
      <button type="button" class="step-tab" data-step="2" onclick="goStep(2)">
        <span class="step-num">2</span>
        <span class="step-title">Gemini AI</span>
      </button>
      <button type="button" class="step-tab" data-step="3" onclick="goStep(3)">
        <span class="step-num">3</span>
        <span class="step-title">GitHub 權杖</span>
      </button>
      <button type="button" class="step-tab" data-step="4" onclick="goStep(4)">
        <span class="step-num">4</span>
        <span class="step-title">GAS 雲端部署</span>
      </button>
      <button type="button" class="step-tab" data-step="5" onclick="goStep(5)">
        <span class="step-num">5</span>
        <span class="step-title">一鍵雲端架設</span>
      </button>
    </nav>

    <!-- STEP 0 -->
    <section class="card active" id="step-0">
      <div class="card-header">
        <span class="tag">步驟 0 / 5｜開始前先花 20 秒看懂</span>
        <h2>為什麼每個人都要建立自己的一套？（0 元、獨立、安全）</h2>
        <p>這份安裝精靈會協助您用<strong>您自己的免費雲端額度</strong>跑完整套系統，原作者完全無法看到您的密碼或信件，也不會消耗任何人的額度上限。</p>
      </div>

      <div class="arch-grid">
        <div class="arch-box">
          <div class="icon">💬</div>
          <h4>1. 您的 LINE 官方帳號</h4>
          <p>當成私人課程小助理，收到作業／小考警報，隨時回「清單」與機器人互動（每月免費 200 則主動推播，Reply 互動完全免費）。</p>
        </div>
        <div class="arch-box">
          <div class="icon">⚡</div>
          <h4>2. Google Apps Script</h4>
          <p>免費託管在您自己的 Google 帳號下，每 5 分鐘巡檢 NTU COOL 通知信並負責 LINE 4 頁日曆選單即時回應。</p>
        </div>
        <div class="arch-box">
          <div class="icon">☁️</div>
          <h4>3. GitHub Actions 自動爬蟲</h4>
          <p>每天 07:55 與 23:00 在您的<strong>私人 GitHub 倉庫</strong>自動登入 COOL 過濾已繳交作業；電腦不用開機、24 小時在線！</p>
        </div>
      </div>

      <div class="callout callout-info">
        <strong>📋 開始前請準備這 4 樣東西：</strong><br />
        ① LINE 帳號（用來建立自己的官方機器人）　
        ② Google / Gmail 帳號（放 Google Apps Script）<br />
        ③ GitHub 帳號（沒有的話步驟 3 可免費註冊）　
        ④ 台大計中帳號與密碼（僅會在最後一步於您瀏覽器內直接加密鎖進您自己的私人 GitHub）
      </div>

      <details class="tip-box">
        <summary>💡 強烈建議順手設定：讓「台大信箱的 COOL 通知信」自動轉寄到您的 Gmail（1 分鐘完成）</summary>
        <div class="tip-content">
          許多同學的 NTU COOL 通知預設寄到 <code>@ntu.edu.tw</code>。若希望每 5 分鐘也能即時偵測突襲小考與公告信，請登入台大 Webmail（<a href="https://webmail.ntu.edu.tw/" target="_blank" rel="noopener">webmail.ntu.edu.tw</a>）→ 點擊「過濾／轉寄規則」，新增規則：凡寄件者包含 <code>cool.ntu.edu.tw</code> 自動轉寄一份到您步驟 4 要使用的 Gmail 帳號（或到 NTU COOL 右上帳號設定修改聯絡信箱）。
        </div>
      </details>

      <div class="card-footer">
        <span class="msg-muted">全部流程約 5～8 分鐘，過程中所有資料只存在這台電腦的瀏覽器內。</span>
        <button type="button" class="btn btn-primary btn-lg" onclick="goStep(1)">🚀 開始申請我的 LINE 機器人 →</button>
      </div>
    </section>

    <!-- STEP 1 -->
    <section class="card" id="step-1">
      <div class="card-header">
        <span class="tag">步驟 1 / 5｜建立您的 LINE 官方帳號機器人</span>
        <h2>申請 Messaging API 並取得兩組通行證</h2>
        <p>這兩組通行證會讓系統能傳送「考試警報」和「滑動待辦清單」給您本人。</p>
      </div>

      <div class="btn-row">
        <a class="btn btn-primary" href="https://manager.line.biz/" target="_blank" rel="noopener">1️⃣ 開啟 LINE Official Account Manager ↗</a>
        <a class="btn btn-outline" href="https://developers.line.biz/console/" target="_blank" rel="noopener">2️⃣ 開啟 LINE Developers Console ↗</a>
      </div>

      <ul class="guide-list">
        <li class="guide-step">
          <div class="guide-badge">1</div>
          <div class="guide-body">
            在 <strong>LINE Official Account Manager</strong> 點 <strong class="click">建立</strong>（或「建立官方帳號」）→ 名稱填例如「COOL 課程助理」、國家選台灣、類別選教育或個人；建立完成後進右上角 <strong class="click">設定 → Messaging API → 啟用 Messaging API</strong>（若問 Provider 名稱，填英文如 <code>ntu-cool</code> 即可）。
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">2</div>
          <div class="guide-body">
            在同一個頁面的左側點選 <strong class="click">回應設定</strong>（或切換到回應模式設定）：<br />
            • <strong class="danger-txt">自動回應訊息：請務必改為「關閉 / 停用」</strong>（否則每次問清單會收到「無法個別回覆」預設罐頭）<br />
            • <strong class="copy">Webhook：請務必開啟「啟用」</strong>
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">3</div>
          <div class="guide-body">
            切換到 <strong>LINE Developers Console</strong> → 點進剛剛建立的 Provider 與 Channel：<br />
            • 在 <strong>Basic settings</strong> 分頁滑到最底下，找到 <strong class="copy">Your user ID</strong>（以 <code>U</code> 開頭共 33 碼）→ 貼到下方「欄位 ①」。<br />
            • 切換到 <strong>Messaging API</strong> 分頁 → <strong class="danger-txt">務必拿手機掃描 QR Code 加你的機器人為好友！</strong>再滑到最底下，在 <strong>Channel access token (long-lived)</strong> 按 <strong class="click">Issue</strong> → 複製長串權杖貼到下方「欄位 ②」。
          </div>
        </li>
      </ul>

      <div class="field">
        <label for="lineUserId">
          <span>欄位 ①｜Your user ID（<code>U</code> 開頭共 33 碼）</span>
        </label>
        <input type="text" id="lineUserId" placeholder="例如：U4a064xxxxxxxxxxxxxxxxxxxxxxxxxxx" oninput="validateLineInputs(); saveDraft();" />
        <div class="field-msg" id="lineUserIdMsg"></div>
      </div>

      <div class="field">
        <label for="lineToken">
          <span>欄位 ②｜Channel access token（長串字元，通常超過 150 碼）</span>
        </label>
        <input type="text" id="lineToken" placeholder="請貼上 Messaging API 分頁最底下的 Channel access token..." oninput="validateLineInputs(); saveDraft();" />
        <div class="field-msg" id="lineTokenMsg"></div>
      </div>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(0)">← 上一步</button>
        <button type="button" class="btn btn-primary" onclick="nextFromStep1()">下一步：設定 Gemini AI（可選填）→</button>
      </div>
    </section>

    <!-- STEP 2 -->
    <section class="card" id="step-2">
      <div class="card-header">
        <span class="tag">步驟 2 / 5｜選填項目（可略過）</span>
        <h2>申請免費 Gemini API 金鑰（讓公告自動濃縮成 60 字重點）</h2>
        <p>填入 Google AI Studio 免費金鑰後，收到長篇英文／中文教授公告信時，AI 會自動抓重點與截止日期。若不想申請，直接略過也完全不影響爬蟲與 LINE 清單功能！</p>
      </div>

      <div class="btn-row">
        <a class="btn btn-accent" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">🔑 前往 Google AI Studio 取得免費金鑰 ↗</a>
      </div>

      <ul class="guide-list">
        <li class="guide-step">
          <div class="guide-badge">1</div>
          <div class="guide-body">登入 Google 帳號後，點右上角 <strong class="click">Create API key</strong> → 隨意選一個專案或點建立專案 → 複製 <strong class="copy">AIza...</strong> 開頭的金鑰。</div>
        </li>
      </ul>

      <div class="field">
        <label for="geminiKey">
          <span>Gemini API Key（選填）</span>
        </label>
        <input type="text" id="geminiKey" placeholder="AIzaSy...（可留空直接略過）" oninput="validateGeminiInput(); saveDraft();" />
        <div class="field-msg" id="geminiKeyMsg"></div>
      </div>

      <div class="callout callout-ok">
        ✅ 免費版額度對個人收信摘要來說綽綽有餘；若留空未填，系統會自動擷取信件前 80 字精華作為摘要。
      </div>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(1)">← 上一步</button>
        <div class="btn-row" style="margin:0;">
          <button type="button" class="btn btn-outline" onclick="skipGeminiAndNext()">略過並下一步</button>
          <button type="button" class="btn btn-primary" onclick="goStep(3)">下一步：連結 GitHub 帳號 →</button>
        </div>
      </div>
    </section>

    <!-- STEP 3 -->
    <section class="card" id="step-3">
      <div class="card-header">
        <span class="tag">步驟 3 / 5｜連結您的 GitHub 帳號</span>
        <h2>產生一次性的自動部署權杖（已為您預先勾選好所需權限）</h2>
        <p>先登入／註冊您的 GitHub 帳號，讓我們等一下能在步驟 4 把帳號資訊直接寫進 Google Apps Script（讓 LINE「🚀 立即爬 COOL」按鈕一次可用），並在步驟 5 全自動幫您建好私人雲端爬蟲！</p>
      </div>

      <div class="btn-row">
        <a class="btn btn-outline" href="https://github.com/signup" target="_blank" rel="noopener">🆕 還沒有 GitHub 帳號？點此免費註冊 ↗</a>
        <a class="btn btn-primary" href="https://github.com/settings/tokens/new?description=COOL-LINE-AutoSetup&scopes=repo,workflow" target="_blank" rel="noopener">⚡ 一鍵開啟已預勾權限的 Token 建立頁 ↗</a>
      </div>

      <ul class="guide-list">
        <li class="guide-step">
          <div class="guide-badge">1</div>
          <div class="guide-body">
            點上面綠色按鈕登入 GitHub 後，會直接跳轉到「New personal access token (classic)」頁面，系統已幫您自動填好名稱與勾選 <strong class="copy">repo</strong> 與 <strong class="copy">workflow</strong>。
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">2</div>
          <div class="guide-body">
            將 <strong>Expiration（期限）</strong> 建議改為 <strong class="click">No expiration</strong>（或 1 year），確認 <strong class="copy">repo</strong> 與 <strong class="copy">workflow</strong> 兩大區塊皆有打勾，拉到最底部點綠色按鈕 <strong class="click">Generate token</strong>。
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">3</div>
          <div class="guide-body">
            立即複製畫面上出現的 <strong class="copy">ghp_...</strong> 開頭權杖，貼入下方欄位並按下「🔍 驗證並連結 GitHub 帳號」。
          </div>
        </li>
      </ul>

      <div class="field">
        <label for="githubToken">
          <span>GitHub Personal Access Token（需含 repo 與 workflow 權限）</span>
        </label>
        <div class="input-wrap">
          <input type="text" id="githubToken" placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" oninput="onGithubTokenChange(); saveDraft();" />
          <button type="button" class="btn btn-accent" id="btnVerifyGh" onclick="verifyGithubToken()" style="white-space:nowrap;">🔍 驗證並連結</button>
        </div>
        <div class="field-msg" id="githubTokenMsg"></div>
      </div>

      <div class="gh-profile" id="ghProfile">
        <img id="ghAvatar" src="" alt="GitHub avatar" />
        <div>
          <div style="font-weight:800; color:#14532d;" id="ghNameTitle"></div>
          <div style="font-size:0.85rem; color:#166534;" id="ghScopeSummary"></div>
        </div>
      </div>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(2)">← 上一步</button>
        <button type="button" class="btn btn-primary" onclick="nextFromStep3()">下一步：部署 Google Apps Script →</button>
      </div>
    </section>

    <!-- STEP 4 -->
    <section class="card" id="step-4">
      <div class="card-header">
        <span class="tag">步驟 4 / 5｜部署您的 Google Apps Script 與 LINE Webhook</span>
        <h2>一鍵複製「已自動填入您全部金鑰」的專屬程式碼</h2>
        <p>您完全不用自己找程式第幾行要改！下方按鈕會即時把您在步驟 1～3 填好的全部金鑰注入 <code>Code.gs</code>，複製貼上即可。</p>
      </div>

      <div class="status-chips" id="gasConfigChips"></div>

      <div class="btn-row">
        <button type="button" class="btn btn-primary btn-lg" onclick="copyPersonalizedCodeGs()">📋 一鍵複製我的專屬 Code.gs（已自動填入全部金鑰）</button>
        <a class="btn btn-accent" href="https://script.google.com/" target="_blank" rel="noopener">🚀 開啟 Google Apps Script ↗</a>
        <button type="button" class="btn btn-outline" onclick="downloadPersonalizedCodeGs()">💾 下載 Code.gs</button>
        <button type="button" class="btn btn-outline" onclick="toggleCodePreview()">👁️ 檢視程式碼</button>
      </div>
      <div class="field-msg" id="copyCodeMsg"></div>
      <pre class="code-box" id="codePreviewBox"></pre>

      <ul class="guide-list" style="margin-top:16px;">
        <li class="guide-step">
          <div class="guide-badge">1</div>
          <div class="guide-body">
            用會收到（或已設定轉寄接收）NTU COOL 通知信的 <strong>Gmail</strong> 開啟 <strong>Google Apps Script</strong> → 點左上角 <strong class="click">＋ 新專案</strong> → 編輯器內 <code>Ctrl+A</code> 全選刪除原本的 <code>myFunction</code> → <code>Ctrl+V</code> 貼上剛剛複製好的專屬 <code>Code.gs</code> → 按 <code>Ctrl+S</code> 儲存。
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">2</div>
          <div class="guide-body">
            點右上角藍色 <strong class="click">部署 → 新增部署作業</strong> → 類型齒輪選 <strong class="click">網頁應用程式</strong>：<br />
            • 執行身分：<strong>我</strong><br />
            • 誰可以存取：<strong class="danger-txt">務必選「所有人」(Anyone)</strong> → 點「部署」並完成授權。<br />
            <span style="color:#b45309; font-size:0.86rem;">💡 若看到「Google 尚未驗證此應用程式」，請點左下角 <strong>「進階」→「前往『未命名專案』（不安全）」→「允許」</strong>（這是您自己部署給自己使用的腳本，完全安全）。</span>
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">3</div>
          <div class="guide-body">
            複製部署完成畫面上的 <strong class="copy">網頁應用程式網址</strong>（必須以 <code>https://script.google.com/macros/s/</code> 開頭、<code>/exec</code> 結尾）：<br />
            • 貼進下方輸入框「GAS Webhook 網址」<br />
            • <strong>同時貼回 LINE Developers Console</strong> → 您的 Messaging API 分頁 → <strong class="click">Webhook URL</strong> → 按 Update → 確認 <strong class="copy">Use webhook</strong> 開關為綠色開啟！<br />
            <span style="font-size:0.86rem; color:#0f766e;">（此時就能立刻拿手機打開跟機器人的 LINE 聊天室傳送「<strong>清單</strong>」測試卡片回應！）</span>
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">4</div>
          <div class="guide-body">
            在 Google Apps Script 左側邊欄點 <strong class="click">⏰ 觸發條件</strong> → 右下角 <strong class="click">＋ 新增觸發條件</strong>，建立以下 <strong>2 組定時鬧鐘</strong>：<br />
            ① 選擇函式：<code>checkCoolUpdates</code> ｜ 時間驅動 → 分鐘計時器 → <strong>每 5 分鐘</strong><br />
            ② 選擇函式：<code>sendDailyMorningBriefing</code> ｜ 時間驅動 → 日計時器 → <strong>上午 8 點到 9 點</strong>
          </div>
        </li>
      </ul>

      <div class="field">
        <label for="gasUrl">
          <span>GAS Webhook 網頁應用程式網址（<code>https://script.google.com/macros/s/.../exec</code>）</span>
        </label>
        <input type="url" id="gasUrl" placeholder="https://script.google.com/macros/s/AKfycb.../exec" oninput="validateGasUrl(); saveDraft();" />
        <div class="field-msg" id="gasUrlMsg"></div>
      </div>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(3)">← 上一步</button>
        <button type="button" class="btn btn-primary" onclick="nextFromStep4()">下一步：最後一關・一鍵自動上雲端 →</button>
      </div>
    </section>

    <!-- STEP 5 -->
    <section class="card" id="step-5">
      <div class="card-header">
        <span class="tag">步驟 5 / 5｜全自動建立您的專屬 GitHub 雲端爬蟲</span>
        <h2>填寫台大計中帳密 ➔ 一鍵自動建倉庫、寫入加密金鑰並觸發首次同步</h2>
        <p>按下按鈕後，這支本機精靈會直接在您的瀏覽器與 GitHub 官方 API 通訊，幫您完成剩餘所有工程設定。</p>
      </div>

      <div class="callout callout-info">
        <strong>🔐 軍規等級端對端本機加密（Libsodium SealedBox）：</strong><br />
        您的台大帳號與密碼<strong>只會在這個網頁的記憶體中</strong>，使用您的 GitHub 倉庫公鑰（Curve25519 SealedBox）加密為不可還原的密文後直接寫入「您自己的 GitHub Repository Secrets」，<strong>不會經過任何第三方伺服器、不會寫入本機瀏覽器暫存</strong>，連原作者也完全看不到您的資料。
      </div>

      <div class="field">
        <label for="studentId">
          <span>台大計中帳號（學號，例如 <code>b12345678</code>，不含 @ntu.edu.tw）</span>
        </label>
        <input type="text" id="studentId" placeholder="例如：b12345678" oninput="validateStudentId(false); saveDraft();" onblur="validateStudentId(true); saveDraft();" />
        <div class="field-msg" id="studentIdMsg"></div>
      </div>

      <div class="field">
        <label for="studentPassword">
          <span>台大計中密碼（本機加密直傳 GitHub Secrets，不儲存於瀏覽器）</span>
        </label>
        <div class="input-wrap">
          <input type="password" id="studentPassword" placeholder="請輸入台大計中密碼..." autocomplete="off" oninput="validatePassword();" />
          <button type="button" class="btn btn-outline" id="btnTogglePw" onclick="togglePasswordVisibility()" style="white-space:nowrap;">👁️ 顯示</button>
        </div>
        <div class="field-msg" id="passwordMsg"></div>
      </div>

      <div class="field">
        <label><span>GitHub 倉庫隱私權設定</span></label>
        <div class="radio-grid">
          <label class="radio-card selected" id="cardPrivate" onclick="setRepoPrivacy(true)">
            <input type="radio" name="repoPrivacy" value="private" checked />
            <div>
              <div class="r-title">🔒 私人倉庫 Private（預設推薦）</div>
              <div class="r-desc">只有您登入 GitHub 看得到紀錄（每日兩次約耗 60 分鐘/月，免費額度每月有 2,000 分鐘非常足夠）。</div>
            </div>
          </label>
          <label class="radio-card" id="cardPublic" onclick="setRepoPrivacy(false)">
            <input type="radio" name="repoPrivacy" value="public" />
            <div>
              <div class="r-title">🌐 公開倉庫 Public</div>
              <div class="r-desc">原始碼公開但您的密碼與金鑰依舊在 Secrets 內完全加密保密，Actions 免費無限分鐘數。</div>
            </div>
          </label>
        </div>
      </div>

      <div class="btn-row" style="margin-top:20px;">
        <button type="button" class="btn btn-primary btn-lg" id="btnDeploy" onclick="deployToGitHub()">
          🚀 一鍵自動建立雲端倉庫、寫入加密金鑰並啟動爬蟲
        </button>
      </div>

      <div class="deploy-log" id="deployLog"></div>

      <div class="callout callout-ok" id="successPanel" style="display:none; margin-top:18px;">
        <h3 style="margin:0 0 8px;">🎉 大功告成！您的個人專屬 COOL-LINE 已在雲端啟動！</h3>
        <p style="margin:0 0 12px;">
          GitHub 正在首次啟動虛擬機並登入 NTU COOL 抓取未繳交作業清單（約 <strong>45～60 秒</strong>後您的手機 LINE 將收到第一封同步完成通知！）。
        </p>
        <div class="btn-row">
          <a class="btn btn-primary" id="linkActions" href="#" target="_blank" rel="noopener">👀 即時查看 GitHub Actions 爬蟲進度 ↗</a>
          <a class="btn btn-outline" id="linkRepo" href="#" target="_blank" rel="noopener">📦 前往我的 cool-line 倉庫 ↗</a>
        </div>
        <div style="margin-top:12px; font-weight:700;">📱 LINE 機器人常用指令速查：</div>
        <div class="cmd-grid">
          <div class="cmd-item">傳送 <code>清單</code> → 一次看【全部｜作業｜考試｜日曆】4 頁滑動卡片</div>
          <div class="cmd-item">傳送 <code>行事曆</code> 或 <code>今天</code> / <code>本週</code> → 快速篩選區間</div>
          <div class="cmd-item">傳送 <code>🚀 立即爬 COOL</code> → 隨時在手機一鍵手動喚醒雲端同步</div>
          <div class="cmd-item">傳送 <code>demo</code> → 一秒測試突襲小考紅色緊急警報畫面</div>
        </div>
      </div>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(4)">← 上一步</button>
        <span class="msg-muted">之後想分享給其他同學，只要直接把這份 HTML 檔案傳給對方即可！</span>
      </div>
    </section>
  </main>

  <!-- 內嵌乾淨開源專案白名單檔案（無任何個人機密） -->
  <script id="repo-files-data" type="application/json">__REPO_FILES_JSON__</script>

  <!-- 內嵌純 JS Curve25519 SealedBox 加密函式庫（零外部 CDN 相依） -->
  <script>__NACL_JS__</script>
  <script>__SEALEDBOX_JS__</script>

  <script>
    const REPO_FILES = JSON.parse(document.getElementById('repo-files-data').textContent);
    const STORAGE_KEY = 'cool_line_wizard_draft_v1';

    const state = {
      currentStep: 0,
      githubOwner: '',
      githubScopes: [],
      repoPrivate: true,
      isDeploying: false
    };

    function el(id) {
      return document.getElementById(id);
    }

    function val(id) {
      const node = el(id);
      return node ? node.value : '';
    }

    // ---------- 步驟切換與暫存 ----------
    function goStep(stepIndex) {
      state.currentStep = stepIndex;
      document.querySelectorAll('.card').forEach((c, idx) => {
        c.classList.toggle('active', idx === stepIndex);
      });
      document.querySelectorAll('.step-tab').forEach((t, idx) => {
        t.classList.toggle('active', idx === stepIndex);
      });
      if (stepIndex === 4) {
        refreshGasConfigSummary();
      }
      saveDraft();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function markStepDone(stepIndex, isDone) {
      const tab = document.querySelector(`.step-tab[data-step="${stepIndex}"]`);
      if (tab) tab.classList.toggle('done', !!isDone);
    }

    function saveDraft() {
      // 安全規範：絕不把台大密碼寫入 sessionStorage / localStorage
      try {
        const draft = {
          currentStep: state.currentStep,
          lineUserId: val('lineUserId'),
          lineToken: val('lineToken'),
          geminiKey: val('geminiKey'),
          githubToken: val('githubToken'),
          githubOwner: state.githubOwner,
          githubScopes: state.githubScopes,
          gasUrl: val('gasUrl'),
          studentId: val('studentId'),
          repoPrivate: state.repoPrivate
        };
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
      } catch (_) {}
    }

    function loadDraft() {
      try {
        const raw = sessionStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const draft = JSON.parse(raw);
        if (draft.lineUserId) el('lineUserId').value = draft.lineUserId;
        if (draft.lineToken) el('lineToken').value = draft.lineToken;
        if (draft.geminiKey) el('geminiKey').value = draft.geminiKey;
        if (draft.githubToken) el('githubToken').value = draft.githubToken;
        if (draft.githubOwner) state.githubOwner = draft.githubOwner;
        if (Array.isArray(draft.githubScopes)) state.githubScopes = draft.githubScopes;
        if (draft.gasUrl) el('gasUrl').value = draft.gasUrl;
        if (draft.studentId) el('studentId').value = draft.studentId;
        if (typeof draft.repoPrivate === 'boolean') setRepoPrivacy(draft.repoPrivate, true);

        validateLineInputs();
        validateGeminiInput();
        validateGasUrl();
        validateStudentId(false);
        if (state.githubOwner) {
          el('ghProfile').classList.add('open');
          el('ghNameTitle').textContent = `已連結 GitHub 帳號：@${state.githubOwner}`;
          el('ghScopeSummary').textContent = state.githubScopes.length
            ? `已讀取權限：${state.githubScopes.join(', ')}`
            : '若您重整過頁面，建議再點一次右側「驗證並連結」確認權杖狀態';
          markStepDone(3, true);
        }
        if (typeof draft.currentStep === 'number' && draft.currentStep >= 0 && draft.currentStep <= 5) {
          goStep(draft.currentStep);
        }
      } catch (_) {}
    }

    function clearSavedDraft() {
      sessionStorage.removeItem(STORAGE_KEY);
      ['lineUserId', 'lineToken', 'geminiKey', 'githubToken', 'gasUrl', 'studentId', 'studentPassword'].forEach(id => {
        if (el(id)) {
          el(id).value = '';
          el(id).classList.remove('valid', 'invalid');
        }
      });
      ['lineUserIdMsg', 'lineTokenMsg', 'geminiKeyMsg', 'githubTokenMsg', 'gasUrlMsg', 'studentIdMsg', 'passwordMsg', 'copyCodeMsg'].forEach(id => {
        if (el(id)) { el(id).textContent = ''; el(id).className = 'field-msg'; }
      });
      state.githubOwner = '';
      state.githubScopes = [];
      el('ghProfile').classList.remove('open');
      el('deployLog').classList.remove('open');
      el('deployLog').innerHTML = '';
      el('successPanel').style.display = 'none';
      document.querySelectorAll('.step-tab').forEach(t => t.classList.remove('done'));
      setRepoPrivacy(true, true);
      goStep(0);
    }

    // ---------- 欄位驗證 ----------
    function validateLineInputs() {
      const uid = val('lineUserId').trim();
      const tok = val('lineToken').trim();
      const uidInput = el('lineUserId');
      const uidMsg = el('lineUserIdMsg');
      const tokInput = el('lineToken');
      const tokMsg = el('lineTokenMsg');

      let uidOk = false;
      if (!uid) {
        uidInput.classList.remove('valid', 'invalid');
        uidMsg.textContent = '';
        uidMsg.className = 'field-msg';
      } else if (/^U[0-9a-f]{32}$/i.test(uid)) {
        uidInput.classList.add('valid');
        uidInput.classList.remove('invalid');
        uidMsg.textContent = '✅ 格式正確！（33 碼 User ID）';
        uidMsg.className = 'field-msg msg-ok';
        uidOk = true;
      } else {
        uidInput.classList.add('invalid');
        uidInput.classList.remove('valid');
        uidMsg.textContent = '⚠️ User ID 必須是小寫/大寫 U 開頭，加上 32 位英數字共 33 碼（在 Basic settings 最底部）。';
        uidMsg.className = 'field-msg msg-err';
      }

      let tokOk = false;
      if (!tok) {
        tokInput.classList.remove('valid', 'invalid');
        tokMsg.textContent = '';
        tokMsg.className = 'field-msg';
      } else if (tok.length <= 48) {
        tokInput.classList.add('invalid');
        tokInput.classList.remove('valid');
        tokMsg.textContent = '⚠️ 您貼到的似乎是「Channel secret（32 碼）」！請切到 Messaging API 分頁最下方點 Issue 複製長串的 Channel access token。';
        tokMsg.className = 'field-msg msg-warn';
      } else if (tok.length < 100) {
        tokInput.classList.add('invalid');
        tokInput.classList.remove('valid');
        tokMsg.textContent = '⚠️ 這組權杖長度似乎不完整，請確認是否有完整複製 Channel access token。';
        tokMsg.className = 'field-msg msg-err';
      } else {
        tokInput.classList.add('valid');
        tokInput.classList.remove('invalid');
        tokMsg.textContent = `✅ 格式正確！（已貼入 ${tok.length} 字元長效權杖）`;
        tokMsg.className = 'field-msg msg-ok';
        tokOk = true;
      }

      markStepDone(1, uidOk && tokOk);
      return uidOk && tokOk;
    }

    function nextFromStep1() {
      if (!validateLineInputs()) {
        alert('請先確認「Your user ID」與「Channel access token」皆已正確填寫！');
        return;
      }
      goStep(2);
    }

    function validateGeminiInput() {
      const key = val('geminiKey').trim();
      const input = el('geminiKey');
      const msg = el('geminiKeyMsg');
      if (!key) {
        input.classList.remove('valid', 'invalid');
        msg.textContent = '尚未填入（沒關係，這項可留空略過）';
        msg.className = 'field-msg msg-muted';
        return true;
      }
      if (/^AIza[0-9A-Za-z_-]{20,}$/.test(key)) {
        input.classList.add('valid');
        input.classList.remove('invalid');
        msg.textContent = '✅ Gemini API Key 格式正確！';
        msg.className = 'field-msg msg-ok';
        markStepDone(2, true);
        return true;
      }
      input.classList.add('invalid');
      input.classList.remove('valid');
      msg.textContent = '⚠️ Gemini 金鑰通常是 AIza 開頭，請確認是否多複製了空白或貼錯欄位。';
      msg.className = 'field-msg msg-warn';
      return false;
    }

    function skipGeminiAndNext() {
      el('geminiKey').value = '';
      validateGeminiInput();
      markStepDone(2, true);
      saveDraft();
      goStep(3);
    }

    function onGithubTokenChange() {
      const tok = val('githubToken').trim();
      const msg = el('githubTokenMsg');
      if (!tok) {
        el('githubToken').classList.remove('valid', 'invalid');
        msg.textContent = '';
        msg.className = 'field-msg';
        el('ghProfile').classList.remove('open');
        state.githubOwner = '';
        markStepDone(3, false);
      } else {
        msg.textContent = '💡 貼上後請點擊右側「🔍 驗證並連結」確認 GitHub 權限是否齊全。';
        msg.className = 'field-msg msg-muted';
      }
    }

    async function verifyGithubToken() {
      const tok = val('githubToken').trim();
      const msg = el('githubTokenMsg');
      const btn = el('btnVerifyGh');
      if (!tok) {
        msg.textContent = '❌ 請先貼上 GitHub Personal Access Token！';
        msg.className = 'field-msg msg-err';
        return false;
      }

      btn.disabled = true;
      btn.textContent = '⏳ 驗證中...';
      try {
        const resp = await fetch('https://api.github.com/user', {
          headers: {
            'Authorization': `Bearer ${tok}`,
            'Accept': 'application/vnd.github+json'
          }
        });
        if (!resp.ok) {
          throw new Error(`GitHub 拒絕連線（HTTP ${resp.status}），請確認 Token 是否貼錯或已過期。`);
        }
        const user = await resp.json();
        const scopeHeader = resp.headers.get('X-OAuth-Scopes');
        state.githubOwner = user.login || '';
        state.githubScopes = scopeHeader
          ? scopeHeader.split(',').map(s => s.trim()).filter(Boolean)
          : [];

        if (user.avatar_url) {
          el('ghAvatar').src = user.avatar_url;
          el('ghAvatar').style.display = 'block';
        } else {
          el('ghAvatar').style.display = 'none';
        }

        if (scopeHeader !== null) {
          const hasRepo = state.githubScopes.includes('repo') || state.githubScopes.includes('public_repo');
          const hasWorkflow = state.githubScopes.includes('workflow');
          if (!hasRepo || !hasWorkflow) {
            const missing = [!hasRepo ? 'repo' : '', !hasWorkflow ? 'workflow' : ''].filter(Boolean).join('、');
            el('ghProfile').classList.remove('open');
            el('githubToken').classList.add('invalid');
            el('githubToken').classList.remove('valid');
            msg.textContent = `❌ 帳號 @${state.githubOwner} 驗證成功，但此 Token 漏勾了「${missing}」權限！無法上傳 Actions 排程，請重新點上方綠色按鈕產生 Token。`;
            msg.className = 'field-msg msg-err';
            markStepDone(3, false);
            return false;
          }
          el('ghScopeSummary').textContent = `權限檢查通過（具備 ${state.githubScopes.join(', ')}）`;
        } else {
          el('ghScopeSummary').textContent = '已連結（Fine-grained Token 請確認具備 Contents / Actions / Secrets 讀寫權限）';
        }

        el('ghNameTitle').textContent = `✅ 已成功連結 GitHub 帳號：@${state.githubOwner}`;
        el('ghProfile').classList.add('open');
        el('githubToken').classList.add('valid');
        el('githubToken').classList.remove('invalid');
        msg.textContent = `✅ 驗證成功！步驟 4 的專屬 Code.gs 將自動為您填入 ${state.githubOwner}/cool-line！`;
        msg.className = 'field-msg msg-ok';
        markStepDone(3, true);
        saveDraft();
        return true;
      } catch (err) {
        el('ghProfile').classList.remove('open');
        el('githubToken').classList.add('invalid');
        el('githubToken').classList.remove('valid');
        msg.textContent = `❌ ${err.message}`;
        msg.className = 'field-msg msg-err';
        markStepDone(3, false);
        return false;
      } finally {
        btn.disabled = false;
        btn.textContent = '🔍 驗證並連結';
      }
    }

    async function nextFromStep3() {
      if (!state.githubOwner) {
        const ok = await verifyGithubToken();
        if (!ok) return;
      }
      goStep(4);
    }

    // ---------- 專屬 Code.gs 產生與複製 ----------
    function buildPersonalizedCodeGs() {
      let code = REPO_FILES['gas/Code.gs'];
      const token = val('lineToken').trim() || '請填入您的_LINE_CHANNEL_ACCESS_TOKEN';
      const userId = val('lineUserId').trim() || '請填入您的_LINE_USER_ID';
      const gemini = val('geminiKey').trim() || '請填入您的_GEMINI_API_KEY';
      const ghOwner = state.githubOwner.trim();
      const ghToken = val('githubToken').trim();
      const ghRepo = ghOwner ? `${ghOwner}/cool-line` : '請填入您的_GITHUB_REPO';
      const ghPat = ghToken || '請填入您的_GITHUB_PAT';

      // 一律使用函式回傳字串做 replace，防止金鑰含 $ 字元被 JS 特殊取代符號破壞
      code = code.replace("'請填入您的_LINE_CHANNEL_ACCESS_TOKEN'", () => JSON.stringify(token));
      code = code.replace("'請填入您的_LINE_USER_ID'", () => JSON.stringify(userId));
      code = code.replace("'請填入您的_GEMINI_API_KEY'", () => JSON.stringify(gemini));
      code = code.replace("'請填入您的_GITHUB_REPO'", () => JSON.stringify(ghRepo));
      code = code.replace("'請填入您的_GITHUB_PAT'", () => JSON.stringify(ghPat));
      return code;
    }

    function refreshGasConfigSummary() {
      const chips = [
        { label: 'LINE User ID', ok: /^U[0-9a-f]{32}$/i.test(val('lineUserId').trim()) },
        { label: 'LINE Access Token', ok: val('lineToken').trim().length >= 100 },
        { label: val('geminiKey').trim() ? 'Gemini API Key' : 'Gemini Key（已略過，改用純文字摘要）', ok: true, warn: !val('geminiKey').trim() },
        { label: state.githubOwner ? `GitHub (${state.githubOwner}/cool-line)` : 'GitHub 尚未連結', ok: !!state.githubOwner },
      ];
      el('gasConfigChips').innerHTML = chips.map(c => {
        const cls = c.warn ? 'chip warn' : (c.ok ? 'chip ok' : 'chip');
        const icon = c.warn ? 'ℹ️' : (c.ok ? '✅' : '⏳');
        return `<span class="${cls}">${icon} ${c.label}</span>`;
      }).join('');

      if (el('codePreviewBox').classList.contains('open')) {
        el('codePreviewBox').textContent = buildPersonalizedCodeGs();
      }
    }

    async function copyPersonalizedCodeGs() {
      const code = buildPersonalizedCodeGs();
      const msg = el('copyCodeMsg');
      let copied = false;

      if (navigator.clipboard && window.isSecureContext !== false) {
        try {
          await navigator.clipboard.writeText(code);
          copied = true;
        } catch (_) {}
      }
      if (!copied) {
        const ta = document.createElement('textarea');
        ta.value = code;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        try {
          copied = document.execCommand('copy');
        } catch (_) {
          copied = false;
        }
        document.body.removeChild(ta);
      }

      if (copied) {
        msg.textContent = '✅ 已將您的專屬 Code.gs 完整複製到剪貼簿！請到 Google Apps Script 按 Ctrl+A → Ctrl+V 覆蓋貼上。';
        msg.className = 'field-msg msg-ok';
      } else {
        msg.textContent = '⚠️ 瀏覽器限制自動複製，請改點「💾 下載 Code.gs」或「👁️ 檢視程式碼」手動全選複製！';
        msg.className = 'field-msg msg-warn';
      }
    }

    function downloadPersonalizedCodeGs() {
      const code = buildPersonalizedCodeGs();
      const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'Code.gs';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }

    function toggleCodePreview() {
      const box = el('codePreviewBox');
      box.classList.toggle('open');
      if (box.classList.contains('open')) {
        box.textContent = buildPersonalizedCodeGs();
      }
    }

    function validateGasUrl() {
      const raw = val('gasUrl').trim();
      const input = el('gasUrl');
      const msg = el('gasUrlMsg');
      if (!raw) {
        input.classList.remove('valid', 'invalid');
        msg.textContent = '';
        msg.className = 'field-msg';
        markStepDone(4, false);
        return false;
      }
      if (/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(raw)) {
        input.classList.add('valid');
        input.classList.remove('invalid');
        msg.textContent = '✅ GAS Webhook 網址格式正確！（記得也要把這串貼進 LINE Developers 的 Webhook URL 並開啟 Use webhook 喔）';
        msg.className = 'field-msg msg-ok';
        markStepDone(4, true);
        return true;
      }
      input.classList.add('invalid');
      input.classList.remove('valid');
      if (raw.endsWith('/dev')) {
        msg.textContent = '⚠️ 您複製到 /dev 測試網址了！必須是正式部署產生的 .../exec 結尾網址才行。';
      } else if (raw.includes('/home/projects/') || raw.endsWith('/edit')) {
        msg.textContent = '⚠️ 這是 Google Apps Script 編輯器網址，不是部署後的網頁應用程式網址（正確格式應為 https://script.google.com/macros/s/.../exec）。';
      } else {
        msg.textContent = '⚠️ 網址必須以 https://script.google.com/macros/s/ 開頭，並以 /exec 結尾。';
      }
      msg.className = 'field-msg msg-err';
      markStepDone(4, false);
      return false;
    }

    function nextFromStep4() {
      if (!validateGasUrl()) {
        alert('請先完成 Google Apps Script 部署，並貼入正確的 .../exec 網址！');
        return;
      }
      goStep(5);
    }

    // ---------- 步驟 5 欄位與 GitHub 全自動部署引擎 ----------
    function validateStudentId(normalizeNow) {
      let sid = val('studentId').trim();
      const input = el('studentId');
      const msg = el('studentIdMsg');

      if (normalizeNow && sid.includes('@')) {
        sid = sid.split('@')[0].trim();
        input.value = sid;
        msg.textContent = `💡 已為您自動移除 @ 後綴，保留計中帳號「${sid}」`;
        msg.className = 'field-msg msg-ok';
        input.classList.add('valid');
        input.classList.remove('invalid');
        return true;
      }
      if (!sid) {
        input.classList.remove('valid', 'invalid');
        msg.textContent = '';
        msg.className = 'field-msg';
        return false;
      }
      if (sid.includes('@')) {
        input.classList.remove('valid');
        msg.textContent = '💡 請填寫學號／計中帳號即可，無須包含 @ntu.edu.tw（離開輸入框會自動修正）。';
        msg.className = 'field-msg msg-warn';
        return true;
      }
      input.classList.add('valid');
      input.classList.remove('invalid');
      msg.textContent = `✅ 將使用計中帳號「${sid}」自動登入 NTU COOL`;
      msg.className = 'field-msg msg-ok';
      return true;
    }

    function validatePassword() {
      const pw = val('studentPassword');
      const input = el('studentPassword');
      const msg = el('passwordMsg');
      if (!pw) {
        input.classList.remove('valid', 'invalid');
        msg.textContent = '';
        msg.className = 'field-msg';
        return false;
      }
      input.classList.add('valid');
      input.classList.remove('invalid');
      msg.textContent = '🔒 密碼已就緒（不會儲存於瀏覽器，僅在按下部署時本機加密上傳）';
      msg.className = 'field-msg msg-ok';
      return true;
    }

    function togglePasswordVisibility() {
      const pw = el('studentPassword');
      const btn = el('btnTogglePw');
      const show = pw.type === 'password';
      pw.type = show ? 'text' : 'password';
      btn.textContent = show ? '🙈 隱藏' : '👁️ 顯示';
    }

    function setRepoPrivacy(isPrivate, silent) {
      state.repoPrivate = !!isPrivate;
      el('cardPrivate').classList.toggle('selected', state.repoPrivate);
      el('cardPublic').classList.toggle('selected', !state.repoPrivate);
      el('cardPrivate').querySelector('input').checked = state.repoPrivate;
      el('cardPublic').querySelector('input').checked = !state.repoPrivate;
      if (!silent) saveDraft();
    }

    // 二進位／UTF-8 Base64 工具（大檔案分塊避免 stack overflow，完整支援繁體中文）
    function base64ToUint8(b64) {
      const bin = atob(b64);
      const out = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
      return out;
    }

    function uint8ToBase64(bytes) {
      let bin = '';
      const chunk = 0x8000;
      for (let i = 0; i < bytes.length; i += chunk) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
      }
      return btoa(bin);
    }

    function utf8ToBase64(str) {
      return uint8ToBase64(new TextEncoder().encode(str));
    }

    function sealSecretForGitHub(plainText, repoPublicKeyB64) {
      if (!window.sealedBox || typeof window.sealedBox.seal !== 'function') {
        throw new Error('本機 SealedBox 加密函式庫未正確載入，請重新整理頁面。');
      }
      const msgBytes = new TextEncoder().encode(plainText);
      const pubKeyBytes = base64ToUint8(repoPublicKeyB64);
      const sealed = window.sealedBox.seal(msgBytes, pubKeyBytes);
      return uint8ToBase64(sealed);
    }

    function sleep(ms) {
      return new Promise(resolve => setTimeout(resolve, ms));
    }

    function appendLog(text, level = 'info') {
      const box = el('deployLog');
      box.classList.add('open');
      const line = document.createElement('div');
      line.className = `log-${level}`;
      line.textContent = text;
      box.appendChild(line);
      box.scrollTop = box.scrollHeight;
    }

    async function ghFetch(token, path, options = {}) {
      const url = path.startsWith('http') ? path : `https://api.github.com${path}`;
      const headers = Object.assign(
        {
          'Authorization': `Bearer ${token}`,
          'Accept': 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28'
        },
        options.headers || {}
      );
      if (options.body && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
      }
      const resp = await fetch(url, Object.assign({}, options, { headers }));
      let data = null;
      const text = await resp.text();
      if (text) {
        try { data = JSON.parse(text); } catch (_) { data = { message: text }; }
      }
      return { ok: resp.ok, status: resp.status, data, headers: resp.headers };
    }

    async function deployToGitHub() {
      if (state.isDeploying) return;

      // 強制整理學號格式並檢查全欄位
      validateStudentId(true);
      const lineUserId = val('lineUserId').trim();
      const lineToken = val('lineToken').trim();
      const ghToken = val('githubToken').trim();
      const gasUrl = val('gasUrl').trim();
      const studentId = val('studentId').trim();
      const studentPassword = val('studentPassword');

      if (!/^U[0-9a-f]{32}$/i.test(lineUserId) || lineToken.length < 100) {
        alert('步驟 1 的 LINE 設定尚未完成或格式有誤，請先檢查步驟 1！');
        goStep(1);
        return;
      }
      if (!ghToken) {
        alert('步驟 3 的 GitHub Token 尚未填寫，請先完成步驟 3！');
        goStep(3);
        return;
      }
      if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(gasUrl)) {
        alert('步驟 4 的 GAS Webhook 網址尚未填寫或格式有誤，請先完成步驟 4！');
        goStep(4);
        return;
      }
      if (!studentId || !studentPassword) {
        alert('請填寫您的台大計中帳號與密碼！');
        return;
      }

      // 安全防線：確認要推送到 GitHub 倉庫的 Code.gs 維持乾淨佔位範本
      if (!REPO_FILES['gas/Code.gs'].includes("'請填入您的_LINE_CHANNEL_ACCESS_TOKEN'")) {
        alert('內部檢查失敗：範本 gas/Code.gs 異常，已中止上傳以防金鑰外洩。');
        return;
      }

      const btn = el('btnDeploy');
      const logBox = el('deployLog');
      logBox.innerHTML = '';
      el('successPanel').style.display = 'none';
      state.isDeploying = true;
      btn.disabled = true;
      btn.textContent = '⏳ 正在自動建置雲端倉庫與加密寫入金鑰...';

      try {
        // 階段 1：確認 GitHub 身分
        appendLog('▶ [1/5] 驗證您的 GitHub 帳號身分...', 'info');
        const userRes = await ghFetch(ghToken, '/user');
        if (!userRes.ok) {
          throw new Error(`GitHub 帳號驗證失敗（HTTP ${userRes.status}）：${userRes.data?.message || ''}`);
        }
        const owner = userRes.data.login;
        state.githubOwner = owner;
        appendLog(`  ✅ 已確認部署目標帳號：@${owner}`, 'ok');

        // 階段 2：建立或接續現有 cool-line 倉庫
        appendLog(`▶ [2/5] 正在準備雲端倉庫 ${owner}/cool-line (${state.repoPrivate ? 'Private' : 'Public'})...`, 'info');
        let branch = 'main';
        const createRes = await ghFetch(ghToken, '/user/repos', {
          method: 'POST',
          body: JSON.stringify({
            name: 'cool-line',
            description: 'COOL-LINE 台大 NTU COOL 智慧死線警報與 LINE 互動行事曆機器人',
            private: state.repoPrivate,
            auto_init: true
          })
        });

        if (createRes.ok) {
          branch = createRes.data.default_branch || 'main';
          appendLog(`  ✅ 成功建立全新倉庫 ${owner}/cool-line（分支：${branch}）！`, 'ok');
          await sleep(1600);
        } else if (createRes.status === 422) {
          appendLog(`  ℹ️ 偵測到 ${owner}/cool-line 已存在，改用既有倉庫進行覆蓋更新...`, 'warn');
          const repoRes = await ghFetch(ghToken, `/repos/${owner}/cool-line`);
          if (!repoRes.ok) {
            throw new Error(`無法存取既有倉庫 ${owner}/cool-line（HTTP ${repoRes.status}）：${repoRes.data?.message || ''}`);
          }
          branch = repoRes.data.default_branch || 'main';
        } else {
          throw new Error(`建立 GitHub 倉庫失敗（HTTP ${createRes.status}）：${createRes.data?.message || ''}`);
        }

        // 確認預設分支存在初始 commit（若使用者之前建了完全空白的倉庫，先補 README 初始化）
        let refRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/ref/heads/${branch}`);
        if (!refRes.ok && (refRes.status === 404 || refRes.status === 409)) {
          appendLog('  ℹ️ 偵測到既有倉庫為全空狀態，正在補上初始檔案...', 'warn');
          const initPut = await ghFetch(ghToken, `/repos/${owner}/cool-line/contents/README.md`, {
            method: 'PUT',
            body: JSON.stringify({
              message: 'chore: initialize cool-line repository',
              content: utf8ToBase64(REPO_FILES['README.md']),
              branch
            })
          });
          if (!initPut.ok) {
            throw new Error(`初始化空倉庫失敗（HTTP ${initPut.status}）：${initPut.data?.message || ''}`);
          }
          await sleep(1200);
          refRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/ref/heads/${branch}`);
        }
        if (!refRes.ok) {
          throw new Error(`讀取分支 ${branch} 失敗（HTTP ${refRes.status}）：${refRes.data?.message || ''}`);
        }
        const headSha = refRes.data.object.sha;

        // 階段 3a：透過 Git Data API 一次提交除 workflow 外的所有乾淨專案檔案
        const workflowPath = '.github/workflows/daily_cool.yml';
        const nonWorkflowPaths = Object.keys(REPO_FILES).filter(p => p !== workflowPath);
        appendLog(`▶ [3/5] 正在打包上傳 ${nonWorkflowPaths.length} 份 COOL-LINE 主程式至 GitHub...`, 'info');

        const headCommitRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/commits/${headSha}`);
        if (!headCommitRes.ok) {
          throw new Error(`讀取最新 Commit 失敗（HTTP ${headCommitRes.status}）：${headCommitRes.data?.message || ''}`);
        }
        const baseTreeSha = headCommitRes.data.tree.sha;

        const treeRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/trees`, {
          method: 'POST',
          body: JSON.stringify({
            base_tree: baseTreeSha,
            tree: nonWorkflowPaths.map(filePath => ({
              path: filePath,
              mode: '100644',
              type: 'blob',
              content: REPO_FILES[filePath]
            }))
          })
        });
        if (!treeRes.ok) {
          throw new Error(`建立檔案樹失敗（HTTP ${treeRes.status}）：${treeRes.data?.message || ''}`);
        }

        const commitRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/commits`, {
          method: 'POST',
          body: JSON.stringify({
            message: 'feat: deploy COOL-LINE bot via setup wizard',
            tree: treeRes.data.sha,
            parents: [headSha]
          })
        });
        if (!commitRes.ok) {
          throw new Error(`建立 Commit 失敗（HTTP ${commitRes.status}）：${commitRes.data?.message || ''}`);
        }

        const patchRefRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/refs/heads/${branch}`, {
          method: 'PATCH',
          body: JSON.stringify({ sha: commitRes.data.sha, force: false })
        });
        if (!patchRefRes.ok) {
          throw new Error(`更新分支指標失敗（HTTP ${patchRefRes.status}）：${patchRefRes.data?.message || ''}`);
        }
        appendLog(`  ✅ 已成功提交全部主程式與乾淨版 Code.gs 範本！`, 'ok');

        // 階段 3b：單獨透過 Contents API 上傳 GitHub Actions Workflow（需 workflow scope）
        appendLog('▶ [3/5] 正在註冊每日 07:55 與 23:00 GitHub Actions 自動爬蟲排程...', 'info');
        let existingWfSha = null;
        const wfCheck = await ghFetch(ghToken, `/repos/${owner}/cool-line/contents/${workflowPath}?ref=${encodeURIComponent(branch)}`);
        if (wfCheck.ok && wfCheck.data?.sha) {
          existingWfSha = wfCheck.data.sha;
        }
        const wfBody = {
          message: 'ci: enable daily NTU COOL auto-sync workflow',
          content: utf8ToBase64(REPO_FILES[workflowPath]),
          branch
        };
        if (existingWfSha) wfBody.sha = existingWfSha;

        const wfPutRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/contents/${workflowPath}`, {
          method: 'PUT',
          body: JSON.stringify(wfBody)
        });
        if (!wfPutRes.ok) {
          if (wfPutRes.status === 403 || wfPutRes.status === 404) {
            throw new Error(
              `上傳 GitHub Actions 工作流失敗（HTTP ${wfPutRes.status}）！這通常是步驟 3 建立 Token 時漏勾選「workflow」權限所致，請回到步驟 3 用一鍵連結重新產生含 repo + workflow 的 Token。`
            );
          }
          throw new Error(`上傳工作流失敗（HTTP ${wfPutRes.status}）：${wfPutRes.data?.message || ''}`);
        }
        appendLog('  ✅ GitHub Actions 自動排程註冊完成！', 'ok');

        // 階段 4：取得倉庫公鑰並本機 SealedBox 加密寫入 5 組 Secrets
        appendLog('▶ [4/5] 正在本機執行 Libsodium SealedBox 加密並寫入 5 組機密環境變數...', 'info');
        const pkRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/actions/secrets/public-key`);
        if (!pkRes.ok) {
          throw new Error(`讀取倉庫 Secrets 公鑰失敗（HTTP ${pkRes.status}）：${pkRes.data?.message || ''}`);
        }
        const { key_id: keyId, key: pubKeyB64 } = pkRes.data;

        const secretsToUpload = [
          ['NTU_STUDENT_ID', studentId],
          ['NTU_PASSWORD', studentPassword],
          ['LINE_CHANNEL_ACCESS_TOKEN', lineToken],
          ['LINE_USER_ID', lineUserId],
          ['GAS_WEBHOOK_URL', gasUrl]
        ];

        for (const [secName, secVal] of secretsToUpload) {
          const encryptedValue = sealSecretForGitHub(secVal, pubKeyB64);
          const putSec = await ghFetch(ghToken, `/repos/${owner}/cool-line/actions/secrets/${secName}`, {
            method: 'PUT',
            body: JSON.stringify({ encrypted_value: encryptedValue, key_id: keyId })
          });
          if (!putSec.ok) {
            throw new Error(`寫入 Secret [${secName}] 失敗（HTTP ${putSec.status}）：${putSec.data?.message || ''}`);
          }
          appendLog(`  🔐 已完成本機加密並寫入 Secret：${secName}`, 'ok');
        }

        // 階段 5：觸發首次雲端登入同步（GitHub 索引工作流需要約 2~4 秒，自動重試）
        appendLog('▶ [5/5] 正在通知 GitHub Actions 啟動首次 NTU COOL 自動登入測試...', 'info');
        await sleep(2000);
        let dispatched = false;
        let lastDispatchStatus = 0;
        let lastDispatchMsg = '';

        for (let attempt = 1; attempt <= 5; attempt++) {
          const dispRes = await ghFetch(
            ghToken,
            `/repos/${owner}/cool-line/actions/workflows/daily_cool.yml/dispatches`,
            {
              method: 'POST',
              body: JSON.stringify({ ref: branch })
            }
          );
          if (dispRes.ok || dispRes.status === 204) {
            dispatched = true;
            break;
          }
          lastDispatchStatus = dispRes.status;
          lastDispatchMsg = dispRes.data?.message || '';
          appendLog(`  ⏳ GitHub 正在建立工作流索引，等待重試（第 ${attempt}/5 次）...`, 'warn');
          await sleep(2500);
        }

        el('linkActions').href = `https://github.com/${owner}/cool-line/actions`;
        el('linkRepo').href = `https://github.com/${owner}/cool-line`;
        el('successPanel').style.display = 'block';
        markStepDone(5, true);

        if (dispatched) {
          appendLog('🎉 全部 5 個步驟成功完成！GitHub 虛擬機已開始登入您的 NTU COOL，請留意手機 LINE 通知！', 'ok');
        } else {
          appendLog(
            `⚠️ 倉庫與 5 組 Secrets 已全部建立完成，但自動觸發首次執行回傳 HTTP ${lastDispatchStatus}（${lastDispatchMsg}）。請點下方「即時查看 GitHub Actions 爬蟲進度」後手動按一次 Run workflow 即可！`,
            'warn'
          );
        }
      } catch (err) {
        appendLog(`❌ 部署中斷：${err.message}`, 'err');
        alert(`部署過程發生狀況：\n${err.message}`);
      } finally {
        state.isDeploying = false;
        btn.disabled = false;
        btn.textContent = '🚀 一鍵自動建立雲端倉庫、寫入加密金鑰並啟動爬蟲';
      }
    }

    // 啟動載入暫存進度
    loadDraft();
  </script>
</body>
</html>
"""


def build() -> None:
    repo_files = load_clean_repo_files()
    nacl_js, sealedbox_js = load_vendor_scripts()

    repo_json_escaped = escape_json_for_html_script(repo_files)
    html_output = (
        HTML_TEMPLATE
        .replace("__REPO_FILES_JSON__", repo_json_escaped)
        .replace("__NACL_JS__", nacl_js)
        .replace("__SEALEDBOX_JS__", sealedbox_js)
    )

    assert_no_leaked_secrets(html_output)

    for target_path in (OUTPUT_REPO_HTML, OUTPUT_DESKTOP_HTML):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(html_output, encoding="utf-8")
        print(f"Generated: {target_path} ({len(html_output.encode('utf-8')):,} bytes)")


if __name__ == "__main__":
    build()
