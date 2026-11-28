# COOL-LINE Antigravity 安裝包工作區指引

此資料夾是 **COOL-LINE（台大 NTU COOL 死線警報與 LINE 互動行事曆助理）** 的自動安裝包。

- 當使用者表示要「安裝」、「繼續安裝」、「修復」或「更新」COOL-LINE（或任何類似意圖）時，**必須先完整讀取 `.agents/skills/cool-line-installer/SKILL.md`** 並嚴格依照其步驟執行。
- 全程請一律使用**繁體中文（台灣用語）**與使用者對話。
- **機密保護原則**：
  - 絕對不可將任何 Token、Secret 或金鑰寫入 `.install_state.json` 以外的檔案（`.install_state.json` 僅由 `installer.py` 管理）。
  - 台大計中密碼（`NTU_PASSWORD`）**永遠不可寫入任何檔案**（包含 `.install_state.json`、暫存檔或筆記），只能在使用時透過環境變數傳給單次指令。
