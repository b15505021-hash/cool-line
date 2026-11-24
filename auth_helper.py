"""Session 自動重登模組：使用 Playwright 無頭瀏覽器走完台大計中 SSO 登入並更新 Cookie。"""

from __future__ import annotations

import logging
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

import config

logger = logging.getLogger(__name__)


def refresh_cool_cookie(timeout_ms: int = 60000) -> str:
    """啟動無頭 Chromium 登入 NTU COOL，取得最新 _normandy_session 並同步更新 .env 與記憶體。

    Returns:
        最新取得的 _normandy_session 字串。

    Raises:
        RuntimeError: 若未設定帳號密碼、登入逾時、帳密錯誤或無法取得 Cookie 時拋出。
    """
    student_id = config.NTU_STUDENT_ID
    password = config.NTU_PASSWORD
    if not student_id or not password:
        raise RuntimeError("未設定 NTU_STUDENT_ID 或 NTU_PASSWORD，無法執行自動重登。")

    logger.info("開始使用 Playwright 執行台大計中 SSO 自動登入...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            try:
                browser = p.chromium.launch(headless=True, channel="chrome")
            except Exception:
                browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            # 改用 domcontentloaded（避免等待背景分析腳本 networkidle 造成逾時），並於連線延遲時自動重試一次
            for attempt in range(2):
                try:
                    page.goto(
                        f"{config.COOL_BASE_URL}/login",
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    break
                except PlaywrightTimeoutError:
                    if attempt == 1:
                        raise
                    logger.warning("前往 NTU COOL 登入頁逾時，正在進行第 2 次重試...")

            # 若停在 COOL 登入入口頁，點擊「以計中帳號登入」前往台大 ADFS SSO
            sso_trigger = page.locator(
                "button:has-text('以計中帳號登入'), a[href*='saml'], a[href*='login/saml'], button:has-text('NTU'), a:has-text('臺大')"
            )
            try:
                sso_trigger.first.wait_for(state="visible", timeout=8000)
            except PlaywrightTimeoutError:
                pass
            if sso_trigger.count() > 0 and page.locator("input[type='password']").count() == 0:
                sso_trigger.first.click()
                page.wait_for_load_state("domcontentloaded")

            # 等待台大計中 ADFS SSO 帳號密碼欄位出現
            username_input = page.locator(
                "#ContentPlaceHolder1_UsernameTextBox, input[name='ctl00$ContentPlaceHolder1$UsernameTextBox'], input[name='user'], input#user, input[name='username']"
            ).first
            password_input = page.locator(
                "#ContentPlaceHolder1_PasswordTextBox, input[type='password']"
            ).first

            username_input.wait_for(state="visible", timeout=timeout_ms)
            username_input.fill(student_id)
            password_input.fill(password)

            # 點擊登入按鈕
            submit_btn = page.locator(
                "#ContentPlaceHolder1_SubmitButton, input[type='submit'], button[type='submit'], button:has-text('登入')"
            ).first
            submit_btn.click()

            # 等待導回 NTU COOL 主網域（代表登入完成）
            page.wait_for_url(
                lambda url: url.startswith(config.COOL_BASE_URL)
                and "/login" not in url
                and "adfs" not in url.lower(),
                timeout=timeout_ms,
            )

            # 等待 DOM 就緒即可讀取 Canvas Session Cookie（無須等 networkidle）
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            cookies = context.cookies(config.COOL_BASE_URL)
            session_cookie = next(
                (c["value"] for c in cookies if c.get("name") == "_normandy_session"),
                None,
            )

            if not session_cookie:
                raise RuntimeError("登入流程結束但未在瀏覽器中取得 _normandy_session Cookie。")

            config.update_cool_session_cookie(session_cookie)
            logger.info("已成功取得並更新 _normandy_session Cookie。")
            return session_cookie

        except PlaywrightTimeoutError as exc:
            raise RuntimeError(
                f"連線或登入台大 SSO 逾時（可能為 GitHub 雲端機房連回台大主機暫時較慢，或帳密有誤）：{exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"自動登入流程發生錯誤：{exc}") from exc
        finally:
            browser.close()
