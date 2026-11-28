"""建置《COOL-LINE 一鍵安裝精靈 v2（新手超防呆 4 步驟圖文版）》獨立單一 HTML 檔案。

特色：
  1. 濃縮為 4 大步驟（免設 Gemini、GAS 自動建立排程鬧鐘、附模擬畫面圖解與防呆指正）。
  2. 內嵌純 JS Curve25519 SealedBox 加密函式庫與全部乾淨開源檔案（零外部 CDN 相依）。
  3. 步驟 4 部署後內建「GitHub Actions 即時監看＋帳密一鍵修復重測」，大幅降低安裝失敗率。
  4. 內建自動防洩密掃描，確保 0 夾帶任何本機 .env 個人機密。
  5. 同時輸出至專案目錄與 Windows 實際桌面路徑（支援 D:\桌面 與預設 Desktop）。
"""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENDOR_DIR = BASE_DIR / "vendor"
OUTPUT_REPO_HTML = BASE_DIR / "COOL-LINE_一鍵安裝精靈.html"
OUTPUT_DESKTOP_TARGETS: list[Path] = [
    Path(r"C:\Users\User\Desktop\COOL-LINE_一鍵安裝精靈.html"),
    Path(r"D:\桌面\COOL-LINE_一鍵安裝精靈.html"),
]

# 嚴格使用檔案白名單，絕對不讀取 .env / *.db / __pycache__ / .git / gas_token.json
REPO_FILE_WHITELIST: list[str] = [
    "requirements.txt",
    ".gitignore",
    ".env.example",
    "config.py",
    "database.py",
    "scraper.py",
    "ai_summarizer.py",
    "line_service.py",
    "rich_menu.py",
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
  <title>COOL-LINE 一鍵安裝精靈（超簡單 4 步驟圖文版）</title>
  <style>
    :root {
      --bg: #f1f5f9;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --border: #dbe3ee;
      --primary: #0f766e;
      --primary-dark: #115e59;
      --primary-soft: #e6f7f5;
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
      --shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", -apple-system, BlinkMacSystemFont, sans-serif;
      background: linear-gradient(180deg, #e0f2fe 0%, var(--bg) 280px);
      color: var(--text);
      line-height: 1.65;
      padding-bottom: 72px;
    }

    .topbar {
      background: linear-gradient(135deg, #0f172a 0%, #0f766e 58%, #1d4ed8 100%);
      color: #fff;
      padding: 20px 24px 28px;
      box-shadow: 0 6px 24px rgba(15, 23, 42, 0.16);
    }
    .topbar-inner {
      max-width: 960px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .brand h1 {
      margin: 0;
      font-size: 1.45rem;
      font-weight: 800;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand p {
      margin: 4px 0 0;
      font-size: 0.92rem;
      color: rgba(255, 255, 255, 0.88);
    }
    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .btn-ghost-light {
      background: rgba(255, 255, 255, 0.15);
      color: #fff;
      border: 1px solid rgba(255, 255, 255, 0.3);
      padding: 7px 14px;
      border-radius: 999px;
      cursor: pointer;
      font-size: 0.84rem;
      font-weight: 700;
      font-family: inherit;
      transition: background 0.15s;
    }
    .btn-ghost-light:hover { background: rgba(255, 255, 255, 0.28); }

    .container {
      max-width: 960px;
      margin: -16px auto 0;
      padding: 0 16px;
    }

    /* Stepper: 5 tabs (0 + 4 steps) */
    .stepper {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 12px;
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      margin-bottom: 20px;
    }
    .step-tab {
      border: 1.5px solid transparent;
      background: #f8fafc;
      border-radius: 12px;
      padding: 10px 6px;
      cursor: pointer;
      text-align: center;
      transition: all 0.16s;
      color: var(--muted);
      font-family: inherit;
    }
    .step-tab:hover { background: #eff6ff; color: var(--text); }
    .step-tab.active {
      background: var(--primary-soft);
      border-color: var(--primary);
      color: var(--primary-dark);
      font-weight: 800;
    }
    .step-tab.done .step-num { background: var(--ok); }
    .step-num {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 24px;
      height: 24px;
      border-radius: 999px;
      background: #94a3b8;
      color: #fff;
      font-size: 0.8rem;
      font-weight: 800;
      margin-bottom: 4px;
    }
    .step-tab.active .step-num { background: var(--primary); }
    .step-title { display: block; font-size: 0.82rem; line-height: 1.25; }

    /* Cards */
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
      padding-bottom: 14px;
      margin-bottom: 20px;
    }
    .card-header .tag {
      display: inline-block;
      background: var(--primary-soft);
      color: var(--primary-dark);
      font-size: 0.8rem;
      font-weight: 800;
      padding: 3px 11px;
      border-radius: 999px;
      margin-bottom: 8px;
    }
    .card-header h2 { margin: 0; font-size: 1.4rem; }
    .card-header p { margin: 6px 0 0; color: var(--muted); font-size: 0.95rem; }

    /* Visual Mockup Box (畫出網頁實際畫面，讓新手絕對不會點錯) */
    .mockup-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin: 14px 0;
    }
    .mockup-box {
      border: 1.5px dashed #93c5fd;
      background: #f8fbff;
      border-radius: 12px;
      padding: 13px 15px;
      font-size: 0.86rem;
    }
    .mockup-title {
      font-weight: 800;
      color: #1e40af;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.88rem;
    }
    .mock-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 6px 10px;
      margin-top: 6px;
    }
    .pill-off { background: #fee2e2; color: #991b1b; font-weight: 800; padding: 2px 8px; border-radius: 6px; font-size: 0.78rem; }
    .pill-on { background: #dcfce7; color: #166534; font-weight: 800; padding: 2px 8px; border-radius: 6px; font-size: 0.78rem; }
    .pill-code { background: #e0e7ff; color: #3730a3; font-family: monospace; font-weight: 700; padding: 2px 8px; border-radius: 6px; font-size: 0.78rem; }

    /* Callouts */
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
    .arch-box .icon { font-size: 1.7rem; margin-bottom: 6px; }
    .arch-box h4 { margin: 0 0 6px; font-size: 1rem; }
    .arch-box p { margin: 0; font-size: 0.86rem; color: var(--muted); }

    /* Step Guide List */
    .guide-list { margin: 14px 0; padding: 0; list-style: none; }
    .guide-step {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      padding: 13px 15px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      margin-bottom: 10px;
    }
    .guide-badge {
      flex-shrink: 0;
      width: 28px;
      height: 28px;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      font-weight: 800;
      font-size: 0.86rem;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-top: 2px;
    }
    .guide-body { flex: 1; font-size: 0.94rem; }
    strong.click { color: #1d4ed8; background: #dbeafe; padding: 1px 7px; border-radius: 6px; }
    strong.copy { color: #065f46; background: #d1fae5; padding: 1px 7px; border-radius: 6px; }
    strong.danger-txt { color: #991b1b; background: #fee2e2; padding: 1px 7px; border-radius: 6px; }

    /* Buttons */
    .btn-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 14px 0; align-items: center; }
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
    .btn-warn { background: #d97706; color: #fff; }
    .btn-warn:hover:not(:disabled) { background: #b45309; }
    .btn-outline { background: #fff; color: var(--text); border-color: #cbd5e1; }
    .btn-outline:hover:not(:disabled) { background: #f1f5f9; }
    .btn-lg { padding: 14px 24px; font-size: 1.03rem; }

    /* Form Fields */
    .field { margin: 16px 0; }
    .field label {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: 700;
      font-size: 0.95rem;
      margin-bottom: 6px;
    }
    .input-wrap { display: flex; gap: 8px; }
    .field input[type="text"],
    .field input[type="password"],
    .field input[type="url"] {
      width: 100%;
      padding: 12px 14px;
      border: 1.5px solid #cbd5e1;
      border-radius: 10px;
      font-size: 0.94rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: var(--text);
      background: #fff;
    }
    .field input:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.16);
    }
    .field input.valid { border-color: #16a34a; background: #fcfffd; }
    .field input.invalid { border-color: #dc2626; background: #fffafa; }
    .field-msg { margin-top: 6px; font-size: 0.86rem; min-height: 18px; }
    .msg-ok { color: var(--ok); font-weight: 700; }
    .msg-warn { color: var(--warn); font-weight: 700; }
    .msg-err { color: var(--danger); font-weight: 700; }
    .msg-muted { color: var(--muted); }

    .check-confirm {
      display: flex;
      align-items: center;
      gap: 10px;
      background: #fffbeb;
      border: 1.5px solid #fde68a;
      border-radius: 12px;
      padding: 12px 14px;
      margin-top: 14px;
      cursor: pointer;
      font-weight: 700;
      font-size: 0.92rem;
      color: #78350f;
    }
    .check-confirm input { width: 18px; height: 18px; cursor: pointer; }

    /* Code preview */
    pre.code-box {
      background: #0f172a;
      color: #e2e8f0;
      padding: 14px;
      border-radius: 10px;
      max-height: 240px;
      overflow: auto;
      font-size: 0.8rem;
      line-height: 1.45;
      display: none;
      margin-top: 10px;
    }
    pre.code-box.open { display: block; }

    /* Radio cards */
    .radio-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px; }
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
    .radio-card.selected { border-color: var(--primary); background: var(--primary-soft); }
    .radio-card input { margin-top: 4px; }
    .radio-card .r-title { font-weight: 700; font-size: 0.93rem; }
    .radio-card .r-desc { font-size: 0.82rem; color: var(--muted); }

    /* Deploy Terminal & Live Monitor */
    .deploy-log {
      background: #0b1220;
      color: #d1d5db;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.85rem;
      padding: 16px;
      border-radius: 12px;
      margin-top: 16px;
      max-height: 320px;
      overflow-y: auto;
      display: none;
      line-height: 1.65;
      border: 1px solid #1e293b;
    }
    .deploy-log.open { display: block; }
    .log-ok { color: #4ade80; }
    .log-info { color: #60a5fa; }
    .log-warn { color: #fbbf24; }
    .log-err { color: #f87171; font-weight: 700; }

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

    details.tip-box {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 11px 15px;
      margin: 12px 0;
    }
    details.tip-box summary { cursor: pointer; font-weight: 700; color: var(--text); font-size: 0.92rem; }
    details.tip-box .tip-content { margin-top: 10px; font-size: 0.89rem; color: var(--muted); }

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

    .cmd-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 12px; }
    .cmd-item { background: #fff; border: 1px solid #bbf7d0; border-radius: 10px; padding: 10px 12px; font-size: 0.88rem; }
    .cmd-item code { background: #ecfdf5; color: #065f46; font-weight: 700; padding: 2px 6px; border-radius: 5px; }

    .status-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 14px; }
    .chip { font-size: 0.82rem; font-weight: 700; padding: 4px 11px; border-radius: 999px; border: 1px solid var(--border); background: #f8fafc; color: var(--muted); }
    .chip.ok { background: var(--ok-bg); border-color: var(--ok-border); color: var(--ok); }
    .chip.warn { background: var(--warn-bg); border-color: var(--warn-border); color: var(--warn); }

    /* FAQ Modal */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.55);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 16px;
      z-index: 999;
    }
    .modal-backdrop.open { display: flex; }
    .modal-card {
      background: #fff;
      border-radius: 16px;
      max-width: 680px;
      width: 100%;
      max-height: 85vh;
      overflow-y: auto;
      padding: 24px;
      box-shadow: 0 20px 50px rgba(15, 23, 42, 0.28);
    }
    .modal-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 12px;
      margin-bottom: 14px;
    }
    .modal-head h3 { margin: 0; font-size: 1.2rem; }
    .faq-item {
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      margin-bottom: 10px;
      background: #f8fafc;
      font-size: 0.9rem;
    }
    .faq-item strong { display: block; color: var(--danger); margin-bottom: 4px; }

    @media (max-width: 780px) {
      .stepper { grid-template-columns: repeat(3, 1fr); }
      .arch-grid, .mockup-grid, .radio-grid, .cmd-grid { grid-template-columns: 1fr; }
      .card { padding: 18px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <h1>🔔 COOL-LINE 超簡單安裝精靈</h1>
        <p>只要 4 個步驟・免寫程式・完全免費｜打造你專屬的台大 NTU COOL 死線警報 &amp; LINE 行事曆助理</p>
      </div>
      <div class="topbar-actions">
        <button type="button" class="btn-ghost-light" onclick="toggleFaq(true)">🆘 卡關了？常見問題急救箱</button>
        <button type="button" class="btn-ghost-light" onclick="clearSavedDraft()">🧹 重設全部</button>
      </div>
    </div>
  </header>

  <main class="container">
    <nav class="stepper" id="stepper" aria-label="安裝步驟">
      <button type="button" class="step-tab active" data-step="0" onclick="goStep(0)">
        <span class="step-num">0</span>
        <span class="step-title">開始前看一眼</span>
      </button>
      <button type="button" class="step-tab" data-step="1" onclick="goStep(1)">
        <span class="step-num">1</span>
        <span class="step-title">LINE 機器人</span>
      </button>
      <button type="button" class="step-tab" data-step="2" onclick="goStep(2)">
        <span class="step-num">2</span>
        <span class="step-title">GitHub 授權</span>
      </button>
      <button type="button" class="step-tab" data-step="3" onclick="goStep(3)">
        <span class="step-num">3</span>
        <span class="step-title">GAS 貼上部署</span>
      </button>
      <button type="button" class="step-tab" data-step="4" onclick="goStep(4)">
        <span class="step-num">4</span>
        <span class="step-title">一鍵完成測試</span>
      </button>
    </nav>

    <!-- STEP 0 -->
    <section class="card active" id="step-0">
      <div class="card-header">
        <span class="tag">開始前 15 秒｜完全免程式背景、總共只要 4 步</span>
        <h2>這個精靈會幫你做什麼？</h2>
        <p>不用裝任何軟體、不用懂程式、<strong>完全免費（$0）</strong>。所有帳號與密碼只存在「你自己的電腦瀏覽器與你自己的私人帳號」裡，連分享這份檔案給你的朋友都看不到！</p>
      </div>

      <div class="arch-grid">
        <div class="arch-box">
          <div class="icon">📱</div>
          <h4>步驟 1：開一隻你的 LINE 機器人</h4>
          <p>建立一個私人 LINE 官方帳號，複製兩組通行證貼進來（約 2 分鐘）。</p>
        </div>
        <div class="arch-box">
          <div class="icon">🔑</div>
          <h4>步驟 2 &amp; 3：連 GitHub 與貼上程式</h4>
          <p>精靈會自動幫你把金鑰填進程式碼，你只要按「複製 → 貼上 → 部署」，<strong>連鬧鐘排程都幫你自動裝好</strong>！</p>
        </div>
        <div class="arch-box">
          <div class="icon">🚀</div>
          <h4>步驟 4：一鍵自動上雲端＋即時檢查</h4>
          <p>輸入台大計中帳密按下按鈕，精靈幫你建好私人雲端並<strong>直接在畫面上監看首次爬蟲成功</strong>！</p>
        </div>
      </div>

      <div class="callout callout-ok">
        <strong>✨ 裝好之後你會獲得什麼？</strong><br />
        • 每天早上 <strong>07:55 早安報平安</strong>（列出最近 3 筆作業）＋ <strong>作業截止前 2 天預告</strong> ＋ <strong>當天死線 &amp; 23:00 最後一小時搶救</strong><br />
        • 自動過濾掉 <strong>已經在 NTU COOL 交完的作業</strong>，交完就消失不吵你<br />
        • 在 LINE 輸入「<strong>清單</strong>」直接滑動看【全部｜作業｜考試｜本月日曆】，點作業名稱直達繳交頁面！
      </div>

      <div class="callout callout-info">
        <strong>📋 請準備這 4 個帳號（全部免費）：</strong>
        ① 你的 LINE 帳號　② 你的 Google / Gmail 帳號　③ GitHub 帳號（沒辦過步驟 2 有註冊連結）　④ 台大計中帳號密碼
      </div>

      <div class="card-footer">
        <span class="msg-muted">💡 過程中隨時可以點右上角「🆘 卡關了？」看解答，重整網頁也不會不見進度。</span>
        <button type="button" class="btn btn-primary btn-lg" onclick="goStep(1)">🚀 開始第 1 步：建立 LINE 機器人 →</button>
      </div>
    </section>

    <!-- STEP 1 -->
    <section class="card" id="step-1">
      <div class="card-header">
        <span class="tag">步驟 1 / 4｜建立你的專屬 LINE 機器人（約 2 分鐘）</span>
        <h2>跟著 3 個動作點，複製「兩組通行證」貼進下方</h2>
        <p>這一步最容易填錯的是把 <code>Channel secret</code>（短的）當成 <code>Channel access token</code>（超長的），下方輸入框會即時幫你檢查！</p>
      </div>

      <div class="btn-row">
        <a class="btn btn-primary" href="https://manager.line.biz/" target="_blank" rel="noopener">1️⃣ 開啟 LINE 官方帳號後台 (manager.line.biz) ↗</a>
        <a class="btn btn-accent" href="https://developers.line.biz/console/" target="_blank" rel="noopener">2️⃣ 開啟 LINE Developers 後台 ↗</a>
      </div>

      <ul class="guide-list">
        <li class="guide-step">
          <div class="guide-badge">1</div>
          <div class="guide-body">
            打開 <strong>1️⃣ LINE 官方帳號後台</strong> 用你的 LINE 登入 → 點 <strong class="click">建立</strong>（建立一般官方帳號）→ 帳號名稱隨便填（例如「我的 COOL 助理」）、公司／業種隨便選「教育」或「個人」→ 建立完成後點「前往管理畫面」。
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">2</div>
          <div class="guide-body">
            進到管理畫面後，點右上角齒輪 <strong class="click">⚙️ 設定</strong> → 左側選單點 <strong class="click">Messaging API</strong> → 按 <strong class="click">啟用 Messaging API</strong>（若問 Provider 名稱，填英文如 <code>ntu-cool</code>，隱私權網址留白直接確定）。<br />
            接著點左側 <strong class="click">回應設定</strong>，照右邊小圖把這兩個開關調成一樣：
          </div>
        </li>
      </ul>

      <div class="mockup-grid">
        <div class="mockup-box">
          <div class="mockup-title">🖼️ 官方帳號「回應設定」長這樣（必改！）</div>
          <div class="mock-row">
            <span>自動回應訊息 (Auto-reply)</span>
            <span class="pill-off">❌ 關閉 / 停用</span>
          </div>
          <div class="mock-row">
            <span>Webhook</span>
            <span class="pill-on">✅ 開啟 / 啟用</span>
          </div>
        </div>
        <div class="mockup-box">
          <div class="mockup-title">🖼️ LINE Developers 兩個分頁要複製什麼？</div>
          <div class="mock-row">
            <span><strong>Basic settings</strong> 最底部</span>
            <span class="pill-code">Your user ID (U開頭33碼)</span>
          </div>
          <div class="mock-row">
            <span><strong>Messaging API</strong> 最底部</span>
            <span class="pill-code">點 Issue ➔ 超長 Token</span>
          </div>
        </div>
      </div>

      <ul class="guide-list">
        <li class="guide-step">
          <div class="guide-badge">3</div>
          <div class="guide-body">
            打開 <strong>2️⃣ LINE Developers 後台</strong> → 點進剛剛建立的 Provider 與 Channel：<br />
            • 在 <strong>Basic settings</strong> 分頁拉到最最最底下 → 複製 <strong class="copy">Your user ID</strong>（<code>U</code> 開頭 33 碼）貼到下方欄位 ①。<br />
            • 切到 <strong>Messaging API</strong> 分頁 → <strong class="danger-txt">立刻拿手機掃頁面上的 QR Code 加這個機器人為好友！</strong>（沒加好友會收不到訊息！）<br />
            • 同頁拉到最底下，在 <strong>Channel access token (long-lived)</strong> 按 <strong class="click">Issue</strong> → 複製超長那一串貼到下方欄位 ②。
          </div>
        </li>
      </ul>

      <div class="field">
        <label for="lineUserId">
          <span>欄位 ①｜Your user ID（<code>U</code> 開頭共 33 碼，在 Basic settings 最底）</span>
        </label>
        <input type="text" id="lineUserId" placeholder="例如：U4a064xxxxxxxxxxxxxxxxxxxxxxxxxxx" oninput="validateLineInputs(); saveDraft();" />
        <div class="field-msg" id="lineUserIdMsg"></div>
      </div>

      <div class="field">
        <label for="lineToken">
          <span>欄位 ②｜Channel access token（超長 170+ 碼，在 Messaging API 最底按 Issue）</span>
        </label>
        <input type="text" id="lineToken" placeholder="請貼上點 Issue 產生的超長 Channel access token..." oninput="validateLineInputs(); saveDraft();" />
        <div class="field-msg" id="lineTokenMsg"></div>
      </div>

      <label class="check-confirm">
        <input type="checkbox" id="chkLineFriend" onchange="saveDraft();" />
        <span>☑️ 我已用手機掃描 QR Code 加這個機器人為好友，並且把「自動回應訊息」關掉了！</span>
      </label>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(0)">← 上一步</button>
        <button type="button" class="btn btn-primary btn-lg" onclick="nextFromStep1()">下一步：連結 GitHub 帳號 →</button>
      </div>
    </section>

    <!-- STEP 2 -->
    <section class="card" id="step-2">
      <div class="card-header">
        <span class="tag">步驟 2 / 4｜連結你的 GitHub 帳號（約 1 分鐘）</span>
        <h2>點一顆按鈕產生授權碼，貼上就會自動幫你驗證！</h2>
        <p>GitHub 是全世界工程師都在用的免費雲端空間，每天 07:55 與 23:00 會自動在你的私人空間幫你登入 NTU COOL 抓作業，電腦關機也會跑！</p>
      </div>

      <div class="btn-row">
        <a class="btn btn-outline" href="https://github.com/signup" target="_blank" rel="noopener">🆕 還沒辦過 GitHub？點此 30 秒免費註冊 ↗</a>
        <a class="btn btn-primary btn-lg" href="https://github.com/settings/tokens/new?description=COOL-LINE-AutoSetup&scopes=repo,workflow" target="_blank" rel="noopener">⚡ 一鍵開啟「已勾好權限」的授權碼頁面 ↗</a>
      </div>

      <div class="mockup-grid">
        <div class="mockup-box">
          <div class="mockup-title">🖼️ 點上面綠色按鈕後，畫面照這樣確認</div>
          <div class="mock-row">
            <span>Expiration（效期）</span>
            <span class="pill-on">選 No expiration</span>
          </div>
          <div class="mock-row">
            <span>Select scopes（權限）</span>
            <span class="pill-on">✅ repo ＋ ✅ workflow</span>
          </div>
        </div>
        <div class="mockup-box">
          <div class="mockup-title">🖼️ 拉到網頁最底部按綠色按鈕</div>
          <div class="mock-row">
            <span>按下底部按鈕</span>
            <span class="pill-on">Generate token</span>
          </div>
          <div class="mock-row">
            <span>複製綠色框框裡的字</span>
            <span class="pill-code">ghp_xxxxxxxxxxxx</span>
          </div>
        </div>
      </div>

      <div class="callout callout-warn">
        ⚠️ <strong>小提醒</strong>：如果點綠色按鈕時你還沒登入 GitHub，登入完之後請<strong>再回來點一次上面的綠色按鈕</strong>，系統才會自動幫你勾好 <code>repo</code> 和 <code>workflow</code> 兩個權限！
      </div>

      <div class="field">
        <label for="githubToken">
          <span>貼上剛剛複製的 GitHub 授權碼（<code>ghp_...</code> 開頭，貼上後自動驗證）</span>
        </label>
        <div class="input-wrap">
          <input type="text" id="githubToken" placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" oninput="onGithubTokenInput(); saveDraft();" />
          <button type="button" class="btn btn-accent" id="btnVerifyGh" onclick="verifyGithubToken()" style="white-space:nowrap;">🔍 驗證連線</button>
        </div>
        <div class="field-msg" id="githubTokenMsg"></div>
      </div>

      <div class="gh-profile" id="ghProfile">
        <img id="ghAvatar" src="" alt="GitHub avatar" />
        <div>
          <div style="font-weight:800; color:#14532d;" id="ghNameTitle"></div>
          <div style="font-size:0.86rem; color:#166534;" id="ghScopeSummary"></div>
        </div>
      </div>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(1)">← 上一步</button>
        <button type="button" class="btn btn-primary btn-lg" onclick="nextFromStep2()">下一步：貼上 Google Apps Script →</button>
      </div>
    </section>

    <!-- STEP 3 -->
    <section class="card" id="step-3">
      <div class="card-header">
        <span class="tag">步驟 3 / 4｜貼上 Google Apps Script（最關鍵一步，已簡化免設鬧鐘！）</span>
        <h2>一鍵複製專屬程式碼 → 貼進 Google → 按部署！</h2>
        <p>你的全部金鑰都已經自動填好在程式碼裡了，而且<strong>新版程式會自動幫你裝好 5 分鐘排程鬧鐘，完全不用自己去設觸發條件！</strong></p>
      </div>

      <div class="status-chips" id="gasConfigChips"></div>

      <div class="btn-row">
        <button type="button" class="btn btn-primary btn-lg" onclick="copyPersonalizedCodeGs()">📋 第 1 動作：一鍵複製我的專屬程式碼</button>
        <a class="btn btn-accent btn-lg" href="https://script.google.com/" target="_blank" rel="noopener">🚀 第 2 動作：開啟 Google Apps Script ↗</a>
        <button type="button" class="btn btn-outline" onclick="downloadPersonalizedCodeGs()">💾 下載備份</button>
        <button type="button" class="btn btn-outline" onclick="toggleCodePreview()">👁️ 檢視</button>
      </div>
      <div class="field-msg" id="copyCodeMsg"></div>
      <pre class="code-box" id="codePreviewBox"></pre>

      <ul class="guide-list" style="margin-top:14px;">
        <li class="guide-step">
          <div class="guide-badge">1</div>
          <div class="guide-body">
            點上方藍色按鈕打開 Google Apps Script → 點左上角 <strong class="click">＋ 新專案</strong> → 在編輯區按 <code>Ctrl+A</code>（Mac 用 <code>Cmd+A</code>）全選刪掉原本的 <code>myFunction</code> → 按 <code>Ctrl+V</code>（<code>Cmd+V</code>）貼上 → 按 <code>Ctrl+S</code> 存檔。
          </div>
        </li>
        <li class="guide-step">
          <div class="guide-badge">2</div>
          <div class="guide-body">
            點右上角藍色 <strong class="click">部署 → 新增部署作業</strong> → 點左上角小齒輪 ⚙️ 選 <strong class="click">網頁應用程式</strong>，並對照下圖設定（<strong class="danger-txt">「所有人」沒選到的話 LINE 會已讀不回！</strong>）：
          </div>
        </li>
      </ul>

      <div class="mockup-grid">
        <div class="mockup-box">
          <div class="mockup-title">🖼️ 部署設定務必長這樣！</div>
          <div class="mock-row">
            <span>執行身分 (Execute as)</span>
            <span class="pill-on">我 (Me)</span>
          </div>
          <div class="mock-row">
            <span>誰可以存取 (Who has access)</span>
            <span class="pill-off">⚠️ 必選「所有人」(Anyone)</span>
          </div>
        </div>
        <div class="mockup-box">
          <div class="mockup-title">🖼️ 看到「Google 尚未驗證」不要怕！</div>
          <div class="mock-row">
            <span>第 1 下：點左下角灰色小字</span>
            <span class="pill-code">進階 (Advanced)</span>
          </div>
          <div class="mock-row">
            <span>第 2 下：點最下方連結再按允許</span>
            <span class="pill-on">前往『未命名專案』(不安全) ➔ 允許</span>
          </div>
        </div>
      </div>

      <ul class="guide-list">
        <li class="guide-step">
          <div class="guide-badge">3</div>
          <div class="guide-body">
            部署完成後，複製畫面上那串 <strong class="copy">網頁應用程式網址</strong>（一定是 <code>https://script.google.com/macros/s/.../exec</code> 結尾）：<br />
            ① 先貼進下方輸入框，再按旁邊的 <strong>「🧪 測試網址」</strong>（看到綠色「✅ COOL-LINE 雲端部署成功」就代表權限 100% 正確，而且鬧鐘已經自動裝好！）。<br />
            ② 再把<strong>同一串網址</strong>貼回步驟 1 的 <strong>LINE Developers → Messaging API → Webhook URL</strong> 按 Update，確認下方的 <strong class="copy">Use webhook</strong> 開關是綠色開啟！
          </div>
        </li>
      </ul>

      <div class="field">
        <label for="gasUrl">
          <span>貼上你的 GAS 網頁應用程式網址（<code>.../exec</code> 結尾）</span>
        </label>
        <div class="input-wrap">
          <input type="url" id="gasUrl" placeholder="https://script.google.com/macros/s/AKfycb.../exec" oninput="validateGasUrl(); saveDraft();" />
          <button type="button" class="btn btn-accent" id="btnTestGas" onclick="openGasHealthCheck()" style="white-space:nowrap;">🧪 測試網址</button>
          <button type="button" class="btn btn-outline" onclick="copyGasUrlForLine()" style="white-space:nowrap;">📋 複製去貼 LINE</button>
        </div>
        <div class="field-msg" id="gasUrlMsg"></div>
      </div>

      <label class="check-confirm">
        <input type="checkbox" id="chkLineWebhook" onchange="saveDraft();" />
        <span>☑️ 我已把這串 <code>.../exec</code> 網址貼回 LINE Developers 的 Webhook URL，並打開「Use webhook」開關！</span>
      </label>

      <details class="tip-box" style="margin-top:16px;">
        <summary>✨ 進階選填（可完全略過）：加入免費 Gemini AI 摘要金鑰 ／ 設定台大信箱轉寄</summary>
        <div class="tip-content">
          <p style="margin-top:0;"><strong>1. 免費 Gemini AI 摘要（選填）</strong>：不填也沒關係，系統會自動擷取信件前 80 字重點。若想讓 AI 濃縮公告，點 <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a> 建立金鑰貼在下方，再重按一次上方「一鍵複製程式碼」覆蓋即可：</p>
          <input type="text" id="geminiKey" style="width:100%;padding:9px 12px;border:1px solid #cbd5e1;border-radius:8px;font-family:monospace;" placeholder="AIzaSy...（選填，留空完全不影響使用）" oninput="refreshGasConfigSummary(); saveDraft();" />
          <p style="margin-top:12px;"><strong>2. 突襲小考即時收信通知（建議有空順手設）</strong>：登入 <a href="https://webmail.ntu.edu.tw/" target="_blank" rel="noopener">台大 Webmail</a> → 設定轉寄規則，將 <code>cool.ntu.edu.tw</code> 的信件自動轉寄到剛剛部署 GAS 的那個 Gmail，就能每 5 分鐘偵測突襲小考通知信！</p>
        </div>
      </details>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(2)">← 上一步</button>
        <button type="button" class="btn btn-primary btn-lg" onclick="nextFromStep3()">下一步：最後一關・輸入台大帳密一鍵完成 →</button>
      </div>
    </section>

    <!-- STEP 4 -->
    <section class="card" id="step-4">
      <div class="card-header">
        <span class="tag">步驟 4 / 4｜最後一步！輸入台大計中帳密 ➔ 一鍵自動完工</span>
        <h2>自動幫你架設私人雲端爬蟲，並現場監看測試結果！</h2>
        <p>按下按鈕後，精靈會在你電腦本機端用軍規加密（Curve25519 SealedBox）把帳密鎖進「你自己的私人 GitHub」，並立即幫你啟動第一次爬蟲測試。</p>
      </div>

      <div class="callout callout-info">
        🔒 <strong>隱私保證</strong>：台大密碼<strong>絕不會存進瀏覽器暫存</strong>、不會傳給原作者、也不會出現在任何程式碼裡，只會加密鎖進你個人 GitHub 的 Secrets 保險箱。
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
          <span>台大計中密碼（本機加密直傳你的 GitHub，不留存於電腦）</span>
        </label>
        <div class="input-wrap">
          <input type="password" id="studentPassword" placeholder="請輸入台大計中密碼..." autocomplete="off" oninput="validatePassword();" />
          <button type="button" class="btn btn-outline" id="btnTogglePw" onclick="togglePasswordVisibility()" style="white-space:nowrap;">👁️ 顯示</button>
        </div>
        <div class="field-msg" id="passwordMsg"></div>
      </div>

      <div class="field">
        <label><span>GitHub 倉庫隱私權（維持預設即可）</span></label>
        <div class="radio-grid">
          <label class="radio-card selected" id="cardPrivate" onclick="setRepoPrivacy(true)">
            <input type="radio" name="repoPrivacy" value="private" checked />
            <div>
              <div class="r-title">🔒 私人倉庫 Private（推薦）</div>
              <div class="r-desc">只有自己看得到，免費額度每月 2,000 分鐘綽綽有餘（本系統每月僅用約 60 分鐘）。</div>
            </div>
          </label>
          <label class="radio-card" id="cardPublic" onclick="setRepoPrivacy(false)">
            <input type="radio" name="repoPrivacy" value="public" />
            <div>
              <div class="r-title">🌐 公開倉庫 Public</div>
              <div class="r-desc">密碼與金鑰依舊在 Secrets 內完全保密，Actions 免費無限分鐘數。</div>
            </div>
          </label>
        </div>
      </div>

      <div class="btn-row" style="margin-top:20px;">
        <button type="button" class="btn btn-primary btn-lg" id="btnDeploy" onclick="deployToGitHub()">
          🚀 一鍵自動安裝至雲端並現場測試！
        </button>
        <button type="button" class="btn btn-warn" id="btnRetryCreds" style="display:none;" onclick="updateCredentialsAndRerun()">
          🔄 只更新台大帳密並重新測試
        </button>
      </div>

      <div class="deploy-log" id="deployLog"></div>

      <!-- 失敗即時診斷卡片 -->
      <div class="callout callout-danger" id="failurePanel" style="display:none; margin-top:16px;">
        <h3 style="margin:0 0 8px;">❌ 雲端首次爬蟲測試失敗了（別擔心，通常 30 秒就能修好！）</h3>
        <p style="margin:0 0 10px;">最常見的原因如下，請對照檢查：</p>
        <ol style="margin:0 0 12px; padding-left:20px;">
          <li><strong>台大計中帳號或密碼打錯</strong>（佔 80%！學號不可含 <code>@ntu.edu.tw</code>，且注意大小寫）→ 直接在上方重打帳密，點橘色按鈕 <strong>「🔄 只更新台大帳密並重新測試」</strong>！</li>
          <li><strong>NTU COOL 剛好網路延遲</strong> → 點橘色按鈕直接重跑一次通常就會過。</li>
          <li>想看詳細錯誤紀錄可點下方按鈕前往 GitHub Actions 頁面。</li>
        </ol>
        <a class="btn btn-outline" id="linkFailActions" href="#" target="_blank" rel="noopener">🔍 查看 GitHub Actions 詳細紀錄 ↗</a>
      </div>

      <!-- 成功慶祝卡片 -->
      <div class="callout callout-ok" id="successPanel" style="display:none; margin-top:18px;">
        <h3 style="margin:0 0 8px;">🎉 大功告成！您的專屬 COOL-LINE 已經成功上線並通過雲端測試！</h3>
        <p style="margin:0 0 12px;" id="successSubtitle">
          請打開手機 LINE 查看剛剛收到的同步通知，現在就可以試試傳送 <strong>「清單」</strong> 體驗 4 頁滑動卡片與本月日曆！
        </p>
        <div class="btn-row">
          <a class="btn btn-primary" id="linkActions" href="#" target="_blank" rel="noopener">👀 查看 GitHub Actions 紀錄 ↗</a>
          <a class="btn btn-outline" id="linkRepo" href="#" target="_blank" rel="noopener">📦 前往我的 cool-line 倉庫 ↗</a>
        </div>
        <div style="margin-top:12px; font-weight:800;">📱 LINE 機器人常用指令速查：</div>
        <div class="cmd-grid">
          <div class="cmd-item">傳送 <code>清單</code> → 一次滑動看【全部｜作業｜考試｜日曆】</div>
          <div class="cmd-item">傳送 <code>今天</code> / <code>本週</code> / <code>課名</code> → 快速篩選作業</div>
          <div class="cmd-item">點選 <code>🚀 立即爬 COOL</code> → 交完作業隨時手動立即同步</div>
          <div class="cmd-item">傳送 <code>demo</code> → 立刻預覽突襲小考紅色緊急警報</div>
        </div>
      </div>

      <div class="card-footer">
        <button type="button" class="btn btn-outline" onclick="goStep(3)">← 上一步</button>
        <span class="msg-muted">想分享給其他同學？直接把這份 HTML 檔案傳給對方即可，不會用到你的任何額度！</span>
      </div>
    </section>
  </main>

  <!-- 常見問題急救箱 Modal -->
  <div class="modal-backdrop" id="faqModal" onclick="if(event.target===this) toggleFaq(false)">
    <div class="modal-card">
      <div class="modal-head">
        <h3>🆘 安裝卡關？5 大常見問題急救箱</h3>
        <button type="button" class="btn btn-outline" onclick="toggleFaq(false)" style="padding:6px 12px;">✕ 關閉</button>
      </div>
      <div class="faq-item">
        <strong>Q1：我在 LINE 傳「清單」，機器人卻「已讀不回」或回系統罐頭訊息？</strong>
        ① 回到 <b>LINE Official Account Manager → 回應設定</b>，確認「自動回應訊息」已<b>關閉</b>、「Webhook」已<b>開啟</b>。<br />
        ② 回到 <b>LINE Developers → Messaging API</b>，確認 <b>Webhook URL</b> 貼的是 <code>.../exec</code> 且 <b>Use webhook</b> 開關是綠色的。<br />
        ③ 確認步驟 3 的 GAS 部署時，「誰可以存取」有選 <b>所有人 (Anyone)</b>（可在步驟 3 按「🧪 測試網址」看到綠色成功頁就代表對了）。
      </div>
      <div class="faq-item">
        <strong>Q2：步驟 1 一直說我貼錯 Channel access token？</strong>
        LINE Developers 有兩個很像的東西：<b>Basic settings</b> 裡的 <code>Channel secret</code>（32 碼短的）是錯的！要切到旁邊 <b>Messaging API</b> 分頁拉到最最底下，按 <code>Issue</code> 才會出現超過 150 碼的 <code>Channel access token</code>。
      </div>
      <div class="faq-item">
        <strong>Q3：步驟 3 按部署時跳出紅字「Google 尚未驗證這個應用程式」？</strong>
        這是正常現象（因為這支腳本是你自己建立給自己用的，沒上架商店）。只要點左下角灰色小字 <b>「進階 (Advanced)」</b> → 點 <b>「前往『未命名專案』（不安全）」</b> → 點 <b>「允許」</b> 即可。
      </div>
      <div class="faq-item">
        <strong>Q4：步驟 4 出現「缺少 workflow 權限」或 HTTP 403 / 404？</strong>
        這是步驟 2 產生 GitHub Token 時漏勾了 <code>workflow</code>。回到步驟 2 重新點綠色「一鍵開啟已勾好權限的授權碼頁面」產生新 Token 貼上即可。
      </div>
      <div class="faq-item">
        <strong>Q5：安裝中途關掉網頁，或想重來怎麼辦？</strong>
        直接重跑一次即可！這支精靈支援重複覆蓋更新，不會把你原本的 GitHub 倉庫弄壞。
      </div>
    </div>
  </div>

  <!-- 內嵌乾淨開源專案白名單檔案（無任何個人機密） -->
  <script id="repo-files-data" type="application/json">__REPO_FILES_JSON__</script>

  <!-- 內嵌純 JS Curve25519 SealedBox 加密函式庫（零外部 CDN 相依） -->
  <script>__NACL_JS__</script>
  <script>__SEALEDBOX_JS__</script>

  <script>
    const REPO_FILES = JSON.parse(document.getElementById('repo-files-data').textContent);
    const STORAGE_KEY = 'cool_line_wizard_draft_v2';

    const state = {
      currentStep: 0,
      githubOwner: '',
      githubScopes: [],
      repoPrivate: true,
      isDeploying: false,
      verifyTimer: null,
      lastBranch: 'main'
    };

    function el(id) { return document.getElementById(id); }
    function val(id) { const n = el(id); return n ? n.value : ''; }

    function toggleFaq(open) {
      el('faqModal').classList.toggle('open', !!open);
    }

    // ---------- 步驟切換與暫存 ----------
    function goStep(stepIndex) {
      state.currentStep = stepIndex;
      document.querySelectorAll('.card').forEach((c, idx) => c.classList.toggle('active', idx === stepIndex));
      document.querySelectorAll('.step-tab').forEach((t, idx) => t.classList.toggle('active', idx === stepIndex));
      if (stepIndex === 3) refreshGasConfigSummary();
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
          chkLineFriend: !!el('chkLineFriend')?.checked,
          geminiKey: val('geminiKey'),
          githubToken: val('githubToken'),
          githubOwner: state.githubOwner,
          githubScopes: state.githubScopes,
          gasUrl: val('gasUrl'),
          chkLineWebhook: !!el('chkLineWebhook')?.checked,
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
        const d = JSON.parse(raw);
        if (d.lineUserId) el('lineUserId').value = d.lineUserId;
        if (d.lineToken) el('lineToken').value = d.lineToken;
        if (d.chkLineFriend) el('chkLineFriend').checked = true;
        if (d.geminiKey) el('geminiKey').value = d.geminiKey;
        if (d.githubToken) el('githubToken').value = d.githubToken;
        if (d.githubOwner) state.githubOwner = d.githubOwner;
        if (Array.isArray(d.githubScopes)) state.githubScopes = d.githubScopes;
        if (d.gasUrl) el('gasUrl').value = d.gasUrl;
        if (d.chkLineWebhook) el('chkLineWebhook').checked = true;
        if (d.studentId) el('studentId').value = d.studentId;
        if (typeof d.repoPrivate === 'boolean') setRepoPrivacy(d.repoPrivate, true);

        validateLineInputs();
        validateGasUrl();
        validateStudentId(false);
        if (state.githubOwner) {
          el('ghProfile').classList.add('open');
          el('ghNameTitle').textContent = `已連結 GitHub 帳號：@${state.githubOwner}`;
          el('ghScopeSummary').textContent = state.githubScopes.length
            ? `權限已就緒（${state.githubScopes.join(', ')}）`
            : '若剛重新整理，可再點「驗證連線」確認權杖';
          markStepDone(2, true);
        }
        if (typeof d.currentStep === 'number' && d.currentStep >= 0 && d.currentStep <= 4) {
          goStep(d.currentStep);
        }
      } catch (_) {}
    }

    function clearSavedDraft() {
      sessionStorage.removeItem(STORAGE_KEY);
      ['lineUserId', 'lineToken', 'geminiKey', 'githubToken', 'gasUrl', 'studentId', 'studentPassword'].forEach(id => {
        if (el(id)) { el(id).value = ''; el(id).classList.remove('valid', 'invalid'); }
      });
      ['chkLineFriend', 'chkLineWebhook'].forEach(id => { if (el(id)) el(id).checked = false; });
      ['lineUserIdMsg', 'lineTokenMsg', 'githubTokenMsg', 'gasUrlMsg', 'studentIdMsg', 'passwordMsg', 'copyCodeMsg'].forEach(id => {
        if (el(id)) { el(id).textContent = ''; el(id).className = 'field-msg'; }
      });
      state.githubOwner = '';
      state.githubScopes = [];
      el('ghProfile').classList.remove('open');
      el('deployLog').classList.remove('open');
      el('deployLog').innerHTML = '';
      el('successPanel').style.display = 'none';
      el('failurePanel').style.display = 'none';
      el('btnRetryCreds').style.display = 'none';
      document.querySelectorAll('.step-tab').forEach(t => t.classList.remove('done'));
      setRepoPrivacy(true, true);
      goStep(0);
    }

    // ---------- 步驟 1：LINE 超精準防呆驗證 ----------
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
      } else if (uid.startsWith('@')) {
        uidInput.classList.add('invalid');
        uidInput.classList.remove('valid');
        uidMsg.textContent = '❌ 這是官方帳號 ID（@開頭），不是 Your user ID！請到 LINE Developers → Basic settings 拉到最底下找「U 開頭 33 碼」那串。';
        uidMsg.className = 'field-msg msg-err';
      } else if (/^\d{8,15}$/.test(uid)) {
        uidInput.classList.add('invalid');
        uidInput.classList.remove('valid');
        uidMsg.textContent = '❌ 這是 Channel ID（純數字），不是 Your user ID！請在 Basic settings 繼續往下滑到最底部找「U 開頭 33 碼」。';
        uidMsg.className = 'field-msg msg-err';
      } else {
        uidInput.classList.add('invalid');
        uidInput.classList.remove('valid');
        uidMsg.textContent = '⚠️ 格式不符：必須是大寫 U 開頭加上 32 位英數字（共 33 碼），請確認沒有多複製到空白或文字。';
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
        tokMsg.textContent = '⚠️ 你貼到的是「Channel secret（32 碼短的）」！請切到旁邊的「Messaging API」分頁，滑到最最底下按 Issue 複製超長的那串！';
        tokMsg.className = 'field-msg msg-warn';
      } else if (tok.length < 100) {
        tokInput.classList.add('invalid');
        tokInput.classList.remove('valid');
        tokMsg.textContent = '⚠️ 這串權杖太短了，請確認有完整複製整串 Channel access token（通常超過 150 碼）。';
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
        alert('請先確認「Your user ID」與「Channel access token」都出現綠色打勾喔！');
        return;
      }
      if (!el('chkLineFriend').checked) {
        const proceed = confirm('提醒：您還沒勾選「已掃 QR Code 加機器人好友＋關閉自動回應訊息」。\n如果沒加好友，機器人將無法傳送通知給您！確定都做好了並繼續嗎？');
        if (!proceed) return;
        el('chkLineFriend').checked = true;
        saveDraft();
      }
      goStep(2);
    }

    // ---------- 步驟 2：GitHub Token（貼上自動驗證） ----------
    function onGithubTokenInput() {
      const tok = val('githubToken').trim();
      const msg = el('githubTokenMsg');
      if (state.verifyTimer) clearTimeout(state.verifyTimer);

      if (!tok) {
        el('githubToken').classList.remove('valid', 'invalid');
        msg.textContent = '';
        msg.className = 'field-msg';
        el('ghProfile').classList.remove('open');
        state.githubOwner = '';
        markStepDone(2, false);
        return;
      }

      if (tok.startsWith('ghp_') || tok.startsWith('github_pat_')) {
        msg.textContent = '⏳ 偵測到 GitHub 授權碼，正在自動驗證權限...';
        msg.className = 'field-msg msg-muted';
        state.verifyTimer = setTimeout(() => verifyGithubToken(), 450);
      } else {
        msg.textContent = '💡 貼上後請按右側「🔍 驗證連線」（正常應以 ghp_ 開頭）。';
        msg.className = 'field-msg msg-warn';
      }
    }

    async function verifyGithubToken() {
      const tok = val('githubToken').trim();
      const msg = el('githubTokenMsg');
      const btn = el('btnVerifyGh');
      if (!tok) {
        msg.textContent = '❌ 請先貼上 GitHub 授權碼！';
        msg.className = 'field-msg msg-err';
        return false;
      }

      btn.disabled = true;
      btn.textContent = '⏳ 驗證中...';
      try {
        const resp = await fetch('https://api.github.com/user', {
          headers: { 'Authorization': `Bearer ${tok}`, 'Accept': 'application/vnd.github+json' }
        });
        if (!resp.ok) {
          throw new Error(`GitHub 拒絕這組授權碼（HTTP ${resp.status}），請確認有沒有漏複製字元，或點上方綠色按鈕重新產生一組。`);
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
            msg.textContent = `❌ 帳號 @${state.githubOwner} 登入成功，但漏勾了「${missing}」權限！請再點一次上方綠色按鈕重新產生（務必確認 repo 與 workflow 都有打勾）。`;
            msg.className = 'field-msg msg-err';
            markStepDone(2, false);
            return false;
          }
          el('ghScopeSummary').textContent = `權限檢查 100% 通過（具備 ${state.githubScopes.join(', ')}）`;
        } else {
          el('ghScopeSummary').textContent = '已連結（Fine-grained Token 請確認具備 Contents / Actions / Secrets 讀寫權限）';
        }

        el('ghNameTitle').textContent = `✅ 成功連結 GitHub 帳號：@${state.githubOwner}`;
        el('ghProfile').classList.add('open');
        el('githubToken').classList.add('valid');
        el('githubToken').classList.remove('invalid');
        msg.textContent = `✅ 完美！下一步的專屬程式碼將自動為你填入 ${state.githubOwner}/cool-line！`;
        msg.className = 'field-msg msg-ok';
        markStepDone(2, true);
        saveDraft();
        return true;
      } catch (err) {
        el('ghProfile').classList.remove('open');
        el('githubToken').classList.add('invalid');
        el('githubToken').classList.remove('valid');
        msg.textContent = `❌ ${err.message}`;
        msg.className = 'field-msg msg-err';
        markStepDone(2, false);
        return false;
      } finally {
        btn.disabled = false;
        btn.textContent = '🔍 驗證連線';
      }
    }

    async function nextFromStep2() {
      if (!state.githubOwner) {
        const ok = await verifyGithubToken();
        if (!ok) return;
      }
      goStep(3);
    }

    // ---------- 步驟 3：專屬 Code.gs 產生與驗證 ----------
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
        { label: state.githubOwner ? `GitHub (${state.githubOwner}/cool-line)` : 'GitHub 尚未連結', ok: !!state.githubOwner },
        { label: val('geminiKey').trim() ? 'Gemini AI（已填入）' : 'Gemini AI（略過，自動純文字摘要）', ok: true, warn: !val('geminiKey').trim() }
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

    async function copyTextSafe(text) {
      if (navigator.clipboard && window.isSecureContext !== false) {
        try {
          await navigator.clipboard.writeText(text);
          return true;
        } catch (_) {}
      }
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
      document.body.removeChild(ta);
      return ok;
    }

    async function copyPersonalizedCodeGs() {
      const copied = await copyTextSafe(buildPersonalizedCodeGs());
      const msg = el('copyCodeMsg');
      if (copied) {
        msg.textContent = '✅ 已複製完成！現在請點旁邊藍色按鈕開啟 Google Apps Script，全選清空後貼上（Ctrl+V / Cmd+V）並存檔！';
        msg.className = 'field-msg msg-ok';
      } else {
        msg.textContent = '⚠️ 瀏覽器限制自動複製，請改點「💾 下載備份」或「👁️ 檢視」手動全選複製！';
        msg.className = 'field-msg msg-warn';
      }
    }

    function downloadPersonalizedCodeGs() {
      const blob = new Blob([buildPersonalizedCodeGs()], { type: 'text/plain;charset=utf-8' });
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
      if (box.classList.contains('open')) box.textContent = buildPersonalizedCodeGs();
    }

    function validateGasUrl() {
      const raw = val('gasUrl').trim();
      const input = el('gasUrl');
      const msg = el('gasUrlMsg');
      if (!raw) {
        input.classList.remove('valid', 'invalid');
        msg.textContent = '';
        msg.className = 'field-msg';
        markStepDone(3, false);
        return false;
      }
      if (/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(raw)) {
        input.classList.add('valid');
        input.classList.remove('invalid');
        msg.textContent = '✅ 網址格式正確！建議點右側「🧪 測試網址」看到綠色成功頁，順便自動啟用 5 分鐘鬧鐘！';
        msg.className = 'field-msg msg-ok';
        markStepDone(3, true);
        return true;
      }
      input.classList.add('invalid');
      input.classList.remove('valid');
      if (raw.endsWith('/dev')) {
        msg.textContent = '❌ 你複製到 /dev 測試網址了！請複製正式部署產生的 .../exec 結尾網址。';
      } else if (raw.includes('/home/projects/') || raw.endsWith('/edit')) {
        msg.textContent = '❌ 這是編輯器網址，不是「網頁應用程式網址」！請點右上角「部署 → 新增部署作業」取得 https://script.google.com/macros/s/.../exec。';
      } else {
        msg.textContent = '⚠️ 網址必須以 https://script.google.com/macros/s/ 開頭，並以 /exec 結尾。';
      }
      msg.className = 'field-msg msg-err';
      markStepDone(3, false);
      return false;
    }

    function openGasHealthCheck() {
      if (!validateGasUrl()) {
        alert('請先貼入正確的 .../exec 網址再測試！');
        return;
      }
      window.open(val('gasUrl').trim(), '_blank', 'noopener');
    }

    async function copyGasUrlForLine() {
      if (!validateGasUrl()) {
        alert('請先貼入正確的 .../exec 網址！');
        return;
      }
      const ok = await copyTextSafe(val('gasUrl').trim());
      if (ok) {
        el('gasUrlMsg').textContent = '✅ 已複製！請貼回 LINE Developers → Messaging API → Webhook URL 並開啟 Use webhook！';
        el('gasUrlMsg').className = 'field-msg msg-ok';
      }
    }

    function nextFromStep3() {
      if (!validateGasUrl()) {
        alert('請先完成 Google Apps Script 部署，並貼入正確的 .../exec 網址！');
        return;
      }
      if (!el('chkLineWebhook').checked) {
        const proceed = confirm('提醒：請確認已經把這串 .../exec 網址貼回 LINE Developers 的 Webhook URL 並打開「Use webhook」，否則在 LINE 輸入「清單」會沒有反應！確定已貼好並繼續嗎？');
        if (!proceed) return;
        el('chkLineWebhook').checked = true;
        saveDraft();
      }
      goStep(4);
    }

    // ---------- 步驟 4：帳密驗證、GitHub 一鍵部署與即時監看 ----------
    function validateStudentId(normalizeNow) {
      let sid = val('studentId').trim();
      const input = el('studentId');
      const msg = el('studentIdMsg');

      if (normalizeNow && sid.includes('@')) {
        sid = sid.split('@')[0].trim();
        input.value = sid;
        msg.textContent = `💡 已幫你自動移除 @ 後綴，保留計中帳號「${sid}」`;
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
        msg.textContent = '💡 填學號就好不用打 @ntu.edu.tw（離開輸入框會自動幫你去掉）。';
        msg.className = 'field-msg msg-warn';
        return true;
      }
      input.classList.add('valid');
      input.classList.remove('invalid');
      msg.textContent = `✅ 將使用計中帳號「${sid}」登入 NTU COOL`;
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
      msg.textContent = '🔒 密碼已就緒（只在本機記憶體加密上傳，不留存於瀏覽器）';
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
        throw new Error('本機 SealedBox 加密套件未載入，請重新整理網頁。');
      }
      const msgBytes = new TextEncoder().encode(plainText);
      const pubKeyBytes = base64ToUint8(repoPublicKeyB64);
      return uint8ToBase64(window.sealedBox.seal(msgBytes, pubKeyBytes));
    }

    function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

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
      if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
      const resp = await fetch(url, Object.assign({}, options, { headers }));
      let data = null;
      const text = await resp.text();
      if (text) {
        try { data = JSON.parse(text); } catch (_) { data = { message: text }; }
      }
      return { ok: resp.ok, status: resp.status, data, headers: resp.headers };
    }

    async function uploadSecretsList(ghToken, owner, secretPairs) {
      const pkRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/actions/secrets/public-key`);
      if (!pkRes.ok) {
        throw new Error(`讀取倉庫 Secrets 公鑰失敗（HTTP ${pkRes.status}）：${pkRes.data?.message || ''}`);
      }
      const { key_id: keyId, key: pubKeyB64 } = pkRes.data;
      for (const [secName, secVal] of secretPairs) {
        const encryptedValue = sealSecretForGitHub(secVal, pubKeyB64);
        const putSec = await ghFetch(ghToken, `/repos/${owner}/cool-line/actions/secrets/${secName}`, {
          method: 'PUT',
          body: JSON.stringify({ encrypted_value: encryptedValue, key_id: keyId })
        });
        if (!putSec.ok) {
          throw new Error(`寫入 Secret [${secName}] 失敗（HTTP ${putSec.status}）：${putSec.data?.message || ''}`);
        }
        appendLog(`  🔐 已本機加密寫入 Secret：${secName}`, 'ok');
      }
    }

    async function triggerAndMonitorRun(ghToken, owner, branch) {
      const triggerTimeMs = Date.now() - 5000;
      let dispatched = false;
      let lastStatus = 0;
      let lastMsg = '';

      for (let attempt = 1; attempt <= 5; attempt++) {
        const dispRes = await ghFetch(
          ghToken,
          `/repos/${owner}/cool-line/actions/workflows/daily_cool.yml/dispatches`,
          { method: 'POST', body: JSON.stringify({ ref: branch }) }
        );
        if (dispRes.ok || dispRes.status === 204) {
          dispatched = true;
          break;
        }
        lastStatus = dispRes.status;
        lastMsg = dispRes.data?.message || '';
        appendLog(`  ⏳ 等待 GitHub 索引工作流，自動重試中（第 ${attempt}/5 次）...`, 'warn');
        await sleep(2500);
      }

      const actionsUrl = `https://github.com/${owner}/cool-line/actions`;
      el('linkActions').href = actionsUrl;
      el('linkFailActions').href = actionsUrl;
      el('linkRepo').href = `https://github.com/${owner}/cool-line`;

      if (!dispatched) {
        appendLog(`⚠️ 倉庫與金鑰都已裝好，但自動觸發測試回傳 HTTP ${lastStatus}（${lastMsg}）。請點下方連結手動按一次 Run workflow 即可。`, 'warn');
        el('successPanel').style.display = 'block';
        markStepDone(4, true);
        return;
      }

      appendLog('  🚀 已觸發雲端爬蟲！正在現場監看 GitHub 執行狀態（通常約 45～75 秒）...', 'info');

      // 現場監看最多 24 次 × 5 秒 = 120 秒
      let lastReportedStatus = '';
      for (let poll = 1; poll <= 24; poll++) {
        await sleep(5000);
        const runsRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/actions/runs?per_page=3`);
        if (!runsRes.ok || !runsRes.data?.workflow_runs?.length) continue;

        const latest = runsRes.data.workflow_runs.find(r => new Date(r.created_at).getTime() >= triggerTimeMs)
          || runsRes.data.workflow_runs[0];
        if (!latest) continue;

        const st = latest.status; // queued | in_progress | completed
        if (st !== lastReportedStatus && st !== 'completed') {
          lastReportedStatus = st;
          const label = st === 'queued'
            ? '⏳ GitHub 雲端機房排隊啟動中...'
            : '⚙️ 雲端瀏覽器正在自動登入您的 NTU COOL 並抓取未繳交作業...';
          appendLog(`  ${label}`, 'info');
        }

        if (st === 'completed') {
          if (latest.conclusion === 'success') {
            appendLog('🎉 雲端首次爬蟲測試「完全成功」！快打開手機 LINE 確認通知！', 'ok');
            el('failurePanel').style.display = 'none';
            el('btnRetryCreds').style.display = 'none';
            el('successPanel').style.display = 'block';
            markStepDone(4, true);
            return;
          } else {
            appendLog(`❌ 雲端爬蟲執行失敗（狀態：${latest.conclusion}）！請確認上方台大計中帳密是否輸入正確。`, 'err');
            el('successPanel').style.display = 'none';
            el('failurePanel').style.display = 'block';
            el('btnRetryCreds').style.display = 'inline-flex';
            return;
          }
        }
      }

      // 若超過 2 分鐘仍在跑，先顯示完成提示並附上即時查看連結
      appendLog('ℹ️ 雲端爬蟲仍在執行中，您可直接點下方按鈕查看進度或留意手機 LINE 通知！', 'warn');
      el('successPanel').style.display = 'block';
      markStepDone(4, true);
    }

    async function deployToGitHub() {
      if (state.isDeploying) return;

      validateStudentId(true);
      const lineUserId = val('lineUserId').trim();
      const lineToken = val('lineToken').trim();
      const ghToken = val('githubToken').trim();
      const gasUrl = val('gasUrl').trim();
      const studentId = val('studentId').trim();
      const studentPassword = val('studentPassword');

      if (!/^U[0-9a-f]{32}$/i.test(lineUserId) || lineToken.length < 100) {
        alert('步驟 1 的 LINE 通行證尚未填好，先帶你回步驟 1 檢查！');
        goStep(1);
        return;
      }
      if (!ghToken) {
        alert('步驟 2 的 GitHub 授權碼尚未填好，先帶你回步驟 2！');
        goStep(2);
        return;
      }
      if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(gasUrl)) {
        alert('步驟 3 的 GAS 網頁應用程式網址尚未填好，先帶你回步驟 3！');
        goStep(3);
        return;
      }
      if (!studentId || !studentPassword) {
        alert('請填寫你的台大計中帳號（學號）與密碼！');
        return;
      }
      if (!REPO_FILES['gas/Code.gs'].includes("'請填入您的_LINE_CHANNEL_ACCESS_TOKEN'")) {
        alert('安全檢查異常：已中止上傳。');
        return;
      }

      const btn = el('btnDeploy');
      el('deployLog').innerHTML = '';
      el('successPanel').style.display = 'none';
      el('failurePanel').style.display = 'none';
      state.isDeploying = true;
      btn.disabled = true;
      btn.textContent = '⏳ 正在全自動安裝並測試中，請勿關閉視窗...';

      try {
        appendLog('▶ [1/5] 確認 GitHub 帳號...', 'info');
        const userRes = await ghFetch(ghToken, '/user');
        if (!userRes.ok) {
          throw new Error(`GitHub 授權碼無效（HTTP ${userRes.status}），請回步驟 2 重新產生。`);
        }
        const owner = userRes.data.login;
        state.githubOwner = owner;
        appendLog(`  ✅ 部署目標：@${owner}/cool-line`, 'ok');

        appendLog(`▶ [2/5] 準備雲端倉庫 (${state.repoPrivate ? 'Private 私人' : 'Public 公開'})...`, 'info');
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
          appendLog(`  ✅ 已建立全新倉庫 ${owner}/cool-line！`, 'ok');
          await sleep(1600);
        } else if (createRes.status === 422) {
          appendLog(`  ℹ️ 偵測到 ${owner}/cool-line 已存在，直接更新既有倉庫...`, 'warn');
          const repoRes = await ghFetch(ghToken, `/repos/${owner}/cool-line`);
          if (!repoRes.ok) throw new Error(`無法存取既有倉庫（HTTP ${repoRes.status}）`);
          branch = repoRes.data.default_branch || 'main';
        } else {
          throw new Error(`建立倉庫失敗（HTTP ${createRes.status}）：${createRes.data?.message || ''}`);
        }
        state.lastBranch = branch;

        let refRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/ref/heads/${branch}`);
        if (!refRes.ok && (refRes.status === 404 || refRes.status === 409)) {
          const initPut = await ghFetch(ghToken, `/repos/${owner}/cool-line/contents/README.md`, {
            method: 'PUT',
            body: JSON.stringify({
              message: 'chore: initialize cool-line repository',
              content: utf8ToBase64(REPO_FILES['README.md']),
              branch
            })
          });
          if (!initPut.ok) throw new Error(`初始化空倉庫失敗（HTTP ${initPut.status}）`);
          await sleep(1200);
          refRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/ref/heads/${branch}`);
        }
        if (!refRes.ok) throw new Error(`讀取分支 ${branch} 失敗（HTTP ${refRes.status}）`);
        const headSha = refRes.data.object.sha;

        const workflowPath = '.github/workflows/daily_cool.yml';
        const nonWorkflowPaths = Object.keys(REPO_FILES).filter(p => p !== workflowPath);
        appendLog(`▶ [3/5] 上傳 ${nonWorkflowPaths.length} 份 COOL-LINE 主程式與每日排程...`, 'info');

        const headCommitRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/commits/${headSha}`);
        if (!headCommitRes.ok) throw new Error(`讀取 Commit 失敗（HTTP ${headCommitRes.status}）`);
        const treeRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/trees`, {
          method: 'POST',
          body: JSON.stringify({
            base_tree: headCommitRes.data.tree.sha,
            tree: nonWorkflowPaths.map(filePath => ({
              path: filePath,
              mode: '100644',
              type: 'blob',
              content: REPO_FILES[filePath]
            }))
          })
        });
        if (!treeRes.ok) throw new Error(`建立檔案樹失敗（HTTP ${treeRes.status}）`);

        const commitRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/commits`, {
          method: 'POST',
          body: JSON.stringify({
            message: 'feat: deploy COOL-LINE bot via setup wizard v2',
            tree: treeRes.data.sha,
            parents: [headSha]
          })
        });
        if (!commitRes.ok) throw new Error(`建立 Commit 失敗（HTTP ${commitRes.status}）`);

        const patchRefRes = await ghFetch(ghToken, `/repos/${owner}/cool-line/git/refs/heads/${branch}`, {
          method: 'PATCH',
          body: JSON.stringify({ sha: commitRes.data.sha, force: false })
        });
        if (!patchRefRes.ok) throw new Error(`更新分支失敗（HTTP ${patchRefRes.status}）`);

        let existingWfSha = null;
        const wfCheck = await ghFetch(ghToken, `/repos/${owner}/cool-line/contents/${workflowPath}?ref=${encodeURIComponent(branch)}`);
        if (wfCheck.ok && wfCheck.data?.sha) existingWfSha = wfCheck.data.sha;
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
            throw new Error('上傳自動排程失敗：您的 GitHub 授權碼漏勾了「workflow」權限！請回步驟 2 點綠色按鈕重新產生一組授權碼。');
          }
          throw new Error(`上傳工作流失敗（HTTP ${wfPutRes.status}）：${wfPutRes.data?.message || ''}`);
        }
        appendLog('  ✅ 主程式與每日自動排程上傳完成！', 'ok');

        appendLog('▶ [4/5] 本機加密並寫入 5 組 GitHub Secrets...', 'info');
        await uploadSecretsList(ghToken, owner, [
          ['NTU_STUDENT_ID', studentId],
          ['NTU_PASSWORD', studentPassword],
          ['LINE_CHANNEL_ACCESS_TOKEN', lineToken],
          ['LINE_USER_ID', lineUserId],
          ['GAS_WEBHOOK_URL', gasUrl]
        ]);

        appendLog('▶ [5/5] 啟動首次雲端爬蟲測試並即時監看結果...', 'info');
        await sleep(2000);
        await triggerAndMonitorRun(ghToken, owner, branch);
      } catch (err) {
        appendLog(`❌ 安裝中斷：${err.message}`, 'err');
        alert(`安裝過程遇到狀況：\n${err.message}`);
      } finally {
        state.isDeploying = false;
        btn.disabled = false;
        btn.textContent = '🚀 一鍵自動安裝至雲端並現場測試！';
      }
    }

    async function updateCredentialsAndRerun() {
      if (state.isDeploying) return;
      validateStudentId(true);
      const ghToken = val('githubToken').trim();
      const studentId = val('studentId').trim();
      const studentPassword = val('studentPassword');
      if (!ghToken || !state.githubOwner || !studentId || !studentPassword) {
        alert('請先重新輸入正確的台大計中帳號與密碼！');
        return;
      }

      const btn = el('btnRetryCreds');
      state.isDeploying = true;
      btn.disabled = true;
      el('failurePanel').style.display = 'none';
      el('successPanel').style.display = 'none';
      appendLog('──────────────────────────────', 'info');
      appendLog('🔄 正在更新台大計中帳密並重新觸發爬蟲測試...', 'info');
      try {
        await uploadSecretsList(ghToken, state.githubOwner, [
          ['NTU_STUDENT_ID', studentId],
          ['NTU_PASSWORD', studentPassword]
        ]);
        await triggerAndMonitorRun(ghToken, state.githubOwner, state.lastBranch || 'main');
      } catch (err) {
        appendLog(`❌ 重試失敗：${err.message}`, 'err');
        alert(err.message);
      } finally {
        state.isDeploying = false;
        btn.disabled = false;
      }
    }

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

    targets = [OUTPUT_REPO_HTML] + [p for p in OUTPUT_DESKTOP_TARGETS if p.parent.is_dir()]
    for target_path in targets:
        target_path.write_text(html_output, encoding="utf-8")
        print(f"Generated: {target_path} ({len(html_output.encode('utf-8')):,} bytes)")


if __name__ == "__main__":
    build()
