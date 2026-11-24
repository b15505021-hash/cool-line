# COOL-LINE：台大 NTU COOL 雙雲端智慧死線、行事曆與 LINE 推播助理

**COOL-LINE** 是一套開源自架（Self-Hosted）的台大 NTU COOL 個人課程助理。採用 **「GitHub Actions 自動登入同步 ＋ Google Apps Script 即時互動與收信」雙雲端零成本架構**，電腦完全不用開機，即可自動過濾已繳交作業、接收考試緊急警報，並在 LINE 內滑動查看分類待辦與本月日曆。

---

## ✨ 核心特色

- **免開電腦、自動過濾已繳交作業（GitHub Actions）**：
  - 每天早上 **07:55** 與晚上 **23:00**（死線前最後一小時）自動透過無頭瀏覽器登入台大 SSO，從 Canvas API 精準篩選出 **「尚未截止且尚未繳交（`unsubmitted`）」** 的作業與測驗，交完的作業自動從清單消失。
- **即時公告濃縮與分級警報（Google Apps Script + Gemini 2.5 Flash）**：
  - 每 5 分鐘掃描 Gmail 中的 NTU COOL 通知信，自動濃縮為 60 字內重點；偵測到考試關鍵字立即發送滿版 **`❗❗❗` 紅色驚嘆號緊急警報**。
- **4 頁橫向輪播 LINE 儀表板（完全免費 Reply API）**：
  - 輸入「清單」一次回傳 **【📋 全部 ｜ 📝 作業 ｜ ⚡ 考試 ｜ 📅 本月日曆】** 4 張並排卡片，左右滑動切換不洗版、不扣每月 200 則推播額度。
  - **點擊標題直達繳交頁**：自動附加 `?openExternalBrowser=1`，點擊任務標題直接以 Safari／Chrome 開啟該作業頁，避開 LINE 內建瀏覽器限制。
  - **互動式 Check List ＋ 原生選日期新增**：支援一鍵打勾「完成／復原」及呼叫手機原生滾輪日曆新增個人待辦。

---

## 🗂️ 專案架構

```text
COOL-LINE/
├── COOL-LINE_一鍵安裝精靈.html  # ✨ 分享專用單一檔案互動精靈（雙擊開啟，免程式背景一鍵自架）
├── build_wizard.py            # 建置安裝精靈並執行零洩密自動檢查
├── vendor/                    # 本機離線純 JS Curve25519 SealedBox 加密套件
├── .github/workflows/
│   └── daily_cool.yml   # GitHub Actions 排程（每日 07:55 與 23:00 自動登入同步）
├── gas/
│   └── Code.gs          # Google Apps Script 程式碼（LINE Webhook 輪播日曆 + 5 分鐘 Gmail 巡檢）
├── cloud_sync.py        # 雲端同步主程式（過濾已繳交作業、同步至 GAS、發送早晚死線提醒）
├── auth_helper.py       # Playwright 自動走完台大 ADFS SSO 登入取得 _normandy_session
├── scraper.py           # Canvas REST API 與 Gmail IMAP 擷取模組
├── ai_summarizer.py     # Gemini 2.5 Flash 公告濃縮（含純文字降級機制）
├── line_service.py      # LINE Messaging API v3 推播（含 Quick Reply 快捷鍵與外部瀏覽器連結）
├── app.py               # （選用備案）Flask 本機課堂 30 秒高頻輪詢伺服器
├── database.py          # （選用備案）SQLite 本地狀態追蹤
├── demo_simulate.py     # Demo Day 一鍵模擬突襲小考與 AI 公告濃縮推播腳本
├── requirements.txt     # Python 相依套件清單
└── .env.example         # 環境變數範本（機密 .env 已由 .gitignore 排除）
```

---

## ✨ 新手零門檻推薦：一鍵分享安裝精靈（免寫程式・不燒原作者額度）

想把 COOL-LINE 分享給其他台大同學？直接將專案內的 **[`COOL-LINE_一鍵安裝精靈.html`](./COOL-LINE_一鍵安裝精靈.html)** 傳給對方雙擊開啟（支援 Windows / Mac 瀏覽器，完全無須安裝 Python）：
- 逐步引導申請 **對方自己的** LINE 機器人與選填 Gemini 金鑰。
- **一鍵自動填入全部金鑰** 產生專屬 `Code.gs`，引導貼至 Google Apps Script 並設定 LINE Webhook。
- 在瀏覽器本機端以 **Libsodium SealedBox 端對端加密**，一鍵全自動在對方 GitHub 帳號建立私人倉庫、寫入 5 組 Secrets 並觸發首次 NTU COOL 自動爬蟲測試！

---

## 🚀 5 分鐘開源自架教學（手動步驟版）

### 步驟 1：建立 LINE 官方帳號
1. 前往 [LINE Official Account Manager](https://manager.line.biz/) 建立帳號，於「設定 → Messaging API」啟用 Messaging API，並於「回應設定」**關閉自動回應訊息、開啟 Webhook**。
2. 前往 [LINE Developers Console](https://developers.line.biz/console/) 取得 **Channel access token** 與 **Your user ID**，並掃描 QR Code 加機器人為好友。

### 步驟 2：部署 Google Apps Script（GAS 雲端互動端）
1. 用綁定 NTU COOL 通知的 Google 帳號開啟 [script.google.com](https://script.google.com/) 建立新專案，貼上 `gas/Code.gs` 全部內容（無須手動在程式碼內填 Token，下一步雲端同步會自動安全寫入雲端屬性；若有申請 [Gemini API Key](https://aistudio.google.com/apikey) 可填入）。
2. 點右上角 **「部署 → 新增部署作業」**，類型選 **「網頁應用程式」**，「誰可以存取」選 **「所有人」**，複製產生的 `https://script.google.com/macros/s/.../exec` 網址。
3. 將該網址貼回 LINE Developers Console 的 **Webhook URL** 並開啟 **Use webhook**。
4. 在 GAS 左側 **「觸發條件（鬧鐘）」** 新增兩條時間驅動排程：
   - `checkCoolUpdates`：分鐘計時器 → 每 5 分鐘
   - `sendDailyMorningBriefing`：日計時器 → 上午 8 點到 9 點

### 步驟 3：Fork 本專案並啟用 GitHub Actions 自動登入
1. Fork 本專案至你個人的 GitHub 帳號。
2. 進入你專案的 **Settings → Secrets and variables → Actions → New repository secret**，新增以下 5 個加密環境變數：
   - `NTU_STUDENT_ID`：台大計中帳號（如 `b12345678`）
   - `NTU_PASSWORD`：台大計中密碼
   - `LINE_CHANNEL_ACCESS_TOKEN`：步驟 1 取得的 Token
   - `LINE_USER_ID`：步驟 1 取得的 User ID
   - `GAS_WEBHOOK_URL`：步驟 2 取得的 GAS 網頁應用程式網址
3. 點擊上方 **Actions → `COOL-LINE 每日雲端登入同步` → Run workflow** 執行一次測試，看到綠色勾勾 ✅ 即完成！

---

## 💻 本機開發與 Demo 測試

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # 填入對應金鑰後即可測試

# 單獨測試自動登入與同步未繳交清單
python cloud_sync.py

# Demo Day 一鍵模擬突襲小考與 AI 濃縮推播
python demo_simulate.py
```
