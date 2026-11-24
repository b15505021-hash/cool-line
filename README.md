# COOL-LINE：台大 NTU COOL 課程動態監控與 LINE 智慧提醒機器人

**COOL-LINE** 是一個專為台大學生設計的自動化課程監控系統。透過「Canvas REST API 主軌 + Gmail IMAP 副軌」雙軌偵測課堂突襲小考、新作業死線、隱藏上傳檔案與助教公告，結合 **Google Gemini 2.5 Flash** 濃縮重點，並透過 **LINE Messaging API** 合併推播（省額度）與免費互動回覆 Flex 卡片。

---

## 目錄
1. [專案結構](#專案結構)
2. [系統核心功能](#系統核心功能)
3. [申請各項 API 金鑰與憑證](#申請各項-api-金鑰與憑證)
4. [安裝與環境設定](#安裝與環境設定)
5. [測試與 Demo 展示](#測試與-demo-展示)
6. [啟動與免費雲端部署建議](#啟動與免費雲端部署建議)

---

## 專案結構

```text
COOL-LINE/
├── app.py               # Flask Webhook 伺服器與 APScheduler 智慧動態排程器
├── config.py            # 環境變數載入、課表高頻警戒時段（CLASS_SCHEDULE）設定
├── database.py          # SQLite 本地資料庫（記錄已通知項目與查詢未到期任務）
├── scraper.py           # 雙軌資料擷取（Canvas REST API + Gmail IMAP 副軌）
├── ai_summarizer.py     # Gemini 2.5 Flash 公告濃縮（含 100 字純文字降級機制）
├── line_service.py      # LINE SDK v3 合併 Push 推播與 Flex Message 待辦卡片
├── auth_helper.py       # Playwright 無頭瀏覽器自動登入台大 SSO 更新 Cookie
├── test_scraper.py      # 單獨測試 COOL Cookie 連線與列出本學期課程
├── demo_simulate.py     # 一鍵模擬「突襲小考 + Gemini 公告濃縮」並發送真實 LINE 推播
├── requirements.txt     # Python 相依套件清單
├── .env.example         # 環境變數範本
├── .env                 # 實際機密設定（已被 .gitignore 排除）
└── .gitignore
```

---

## 系統核心功能

- **課表感知動態輪詢（`APScheduler`）**：
  - **上課高頻警戒時段**（依 `config.py` 中的 `CLASS_SCHEDULE`）：每 **30 秒** 掃描一次，抓出未寄信通知的課堂突襲小考。
  - **非上課一般時段**：每 **20 分鐘** 掃描一次，維持連線狀態並節省資源。
- **雙軌偵測無死角**：
  - **主軌（Canvas API）**：監控線上測驗（`quizzes`）、作業死線（`assignments`）以及老師只傳檔案不開作業的隱藏任務（`files`）。
  - **副軌（Gmail IMAP，選用）**：自動讀取來自 `ntu-cool@cool.ntu.edu.tw` 的未讀通知信並去除 HTML 標籤。
- **節省 LINE 免費推播額度**：
  - 主動推播（Push API）將同一輪偵測到的多筆新動態**合併成一則訊息**發送。
  - 傳送「作業」、「考試」、「檢查」或 `check` 至機器人時，改走免費的 **Reply API** 即時回傳 **Flex Message** 視覺化待辦卡片。
- **Session 自動續命**：遇到 HTTP `401/403`（`SessionExpiredError`）時，自動呼叫 Playwright 登入台大 SSO 更新 `_normandy_session`；若失敗（如遇驗證碼或未設定帳密），會主動發送 LINE 警告通知。

---

## 申請各項 API 金鑰與憑證

### 1. 取得 LINE Messaging API 金鑰與 User ID
1. 前往 [LINE Developers Console](https://developers.line.biz/console/)，登入後建立一個 Provider，並新增 **Messaging API Channel**。
2. 在 Channel 的 **Messaging API** 分頁中：
   - 發行並複製 **Channel access token (long-lived)** -> 填入 `LINE_CHANNEL_ACCESS_TOKEN`。
   - 捲動到下方找到 **Your user ID**（`U` 開頭的字串）-> 填入 `LINE_USER_ID`。
   - 建議關閉「自動回應訊息（Auto-reply messages）」以避免干擾機器人回覆。
3. 在 **Basic settings** 分頁中：
   - 複製 **Channel secret** -> 填入 `LINE_CHANNEL_SECRET`。
4. 掃描 QR Code 將你的 LINE 官方帳號加為好友。

### 2. 取得 Google Gemini API Key
1. 前往 [Google AI Studio](https://aistudio.google.com/apikey)。
2. 點擊 **Create API key** 建立免費金鑰 -> 填入 `GEMINI_API_KEY`。

### 3. 取得 NTU COOL `_normandy_session` Cookie
1. 使用 Chrome / Edge 瀏覽器登入 [NTU COOL](https://cool.ntu.edu.tw)。
2. 按 `F12` 開啟開發者工具 -> 切換至 **Application（應用程式）** 分頁 -> 左側展開 **Cookies** -> 點選 `https://cool.ntu.edu.tw`。
3. 找到名稱為 `_normandy_session` 的項目，複製其 **Value** -> 填入 `.env` 的 `COOL_SESSION_COOKIE`。

### 4. （選用）設定台大計中帳密自動重登
- 若希望 Cookie 過期時自動更新，可在 `.env` 填入 `NTU_STUDENT_ID` 與 `NTU_PASSWORD`（僅存於本機 `.env`，請勿上傳至 GitHub）。

### 5. （選用）設定 Gmail IMAP 應用程式密碼
1. 若 NTU COOL 通知信寄到 Gmail，先到 Google 帳戶開啟「兩步驟驗證」。
2. 前往 Google 帳戶安全性設定建立 **應用程式密碼（App Password）**（16 碼英文字母）。
3. 將 Gmail 信箱與 16 碼密碼填入 `.env` 的 `GMAIL_ADDRESS` 與 `GMAIL_APP_PASSWORD`（兩者皆填寫才會啟用副軌讀信）。

---

## 安裝與環境設定

### 1. 安裝 Python 相依套件
```bash
pip install -r requirements.txt
```

### 2. 安裝 Playwright 無頭瀏覽器（供自動重登使用）
```bash
playwright install chromium
```

### 3. 設定 `.env` 與課表
1. 打開專案內的 `.env` 檔案，填入上述取得之金鑰與 Cookie。
2. 打開 `config.py`，依你的實際課表修改 `CLASS_SCHEDULE`：
   ```python
   CLASS_SCHEDULE = {
       "Mon": [("13:20", "15:10")],
       "Thu": [("13:20", "14:10")],
   }
   ```

---

## 測試與 Demo 展示

### 1. 測試 NTU COOL 連線與課程列表
```bash
python test_scraper.py
```
（也可直接帶入參數測試：`python test_scraper.py --cookie "你的_normandy_session"`）

### 2. 期末 Demo Day 一鍵模擬推播
```bash
python demo_simulate.py
```
執行後會立刻模擬「工程數學突襲小考」與「Gemini 濃縮助教公告」，並合併推播一則真實訊息到你的手機 LINE。接著在 LINE 聊天室傳送「考試」或「作業」，即可展示 Flex Message 卡片回覆！

---

## 啟動與免費雲端部署建議

### 本機啟動
```bash
python app.py
```
預設監聽 `http://0.0.0.0:5000`。若需在本機測試 LINE Webhook，可搭配 `ngrok http 5000` 取得 HTTPS 網址後，填入 LINE Developers Console 的 **Webhook URL**（`https://你的網址/callback`）並開啟 **Use webhook**。

### 雲端防休眠設定
- 部署至 Render / Railway 等免費方案後，可至 [cron-job.org](https://cron-job.org/) 建立每 10～14 分鐘一次的免費排程任務，定時向 `https://你的網域/ping` 或 `https://你的網域/trigger` 發送 `GET` 請求，防止免費伺服器休眠。
