"""純 Python 一鍵自動推送並熱更新部署 Google Apps Script (Code.gs)。

使用 Google 官方 Apps Script REST API (v1)：
  1. 首次使用：執行 `python deploy_gas.py --auth` 完成一次本機 OAuth 2.0 授權並儲存 refresh_token。
  2. 日後更新：直接執行 `python deploy_gas.py`（約 1.5 秒內完成程式碼上傳、建立新版本、更新既有 Webhook 部署，網址不變）。

所有個人憑證檔（gas_oauth_client.json、gas_token.json、.gas_deploy_config.json）皆已列入 .gitignore，不會上傳至 GitHub。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import sys
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent
CLIENT_SECRET_PATH = BASE_DIR / "gas_oauth_client.json"
TOKEN_PATH = BASE_DIR / "gas_token.json"
DEPLOY_CONFIG_PATH = BASE_DIR / ".gas_deploy_config.json"
CODE_GS_PATH = BASE_DIR / "gas" / "Code.gs"

SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
]
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{REDIRECT_PORT}/"


def load_client_config() -> dict[str, str]:
    if not CLIENT_SECRET_PATH.is_file():
        raise FileNotFoundError(
            f"找不到 OAuth 用戶端設定檔：{CLIENT_SECRET_PATH}\n"
            "請先於 Google Cloud Console 建立「電腦版應用程式 (Desktop app)」OAuth 用戶端並儲存為 gas_oauth_client.json。"
        )
    raw = json.loads(CLIENT_SECRET_PATH.read_text(encoding="utf-8"))
    info = raw.get("installed") or raw.get("web") or raw
    client_id = info.get("client_id", "").strip()
    client_secret = info.get("client_secret", "").strip()
    if not client_id or not client_secret:
        raise ValueError("gas_oauth_client.json 缺少 client_id 或 client_secret。")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": info.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth"),
        "token_uri": info.get("token_uri", "https://oauth2.googleapis.com/token"),
    }


def load_deploy_config() -> dict[str, str]:
    if not DEPLOY_CONFIG_PATH.is_file():
        raise FileNotFoundError(f"找不到部署目標設定檔：{DEPLOY_CONFIG_PATH}")
    cfg = json.loads(DEPLOY_CONFIG_PATH.read_text(encoding="utf-8"))
    script_id = cfg.get("script_id", "").strip()
    deployment_id = cfg.get("deployment_id", "").strip()
    if not script_id or not deployment_id:
        raise ValueError(".gas_deploy_config.json 缺少 script_id 或 deployment_id。")
    return {"script_id": script_id, "deployment_id": deployment_id}


def run_local_oauth_flow(timeout_sec: int = 300) -> dict[str, Any]:
    client = load_client_config()
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    state_token = secrets.token_urlsafe(24)

    params = {
        "client_id": client["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state_token,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{client['auth_uri']}?{urllib.parse.urlencode(params)}"
    print(f"AUTH_URL={auth_url}", flush=True)

    result: dict[str, str | None] = {"code": None, "error": None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("state", [""])[0] != state_token:
                result["error"] = "OAuth state 驗證不符"
            elif "error" in qs:
                result["error"] = qs["error"][0]
            elif "code" in qs:
                result["code"] = qs["code"][0]
            else:
                result["error"] = "未收到授權碼 (code)"

            ok = result["code"] is not None
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = (
                "<html><body style='font-family:sans-serif;text-align:center;padding:48px;'>"
                + (
                    "<h2 style='color:#0f766e;'>✅ Google Apps Script 自動部署授權成功！</h2>"
                    "<p>已安全儲存本機專用權杖，以後 AI 可直接 1 秒幫您更新並部署 GAS，請直接切回對話視窗。</p>"
                    if ok
                    else f"<h2 style='color:#b91c1c;'>❌ 授權未完成：{result['error']}</h2>"
                )
                + "</body></html>"
            )
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    server = HTTPServer(("127.0.0.1", REDIRECT_PORT), CallbackHandler)
    server.timeout = 1.0
    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline and result["code"] is None and result["error"] is None:
            server.handle_request()
    finally:
        server.server_close()

    if result["error"]:
        raise RuntimeError(f"OAuth 授權失敗：{result['error']}")
    if not result["code"]:
        raise TimeoutError("等待瀏覽器點擊授權逾時。")

    resp = requests.post(
        client["token_uri"],
        data={
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": result["code"],
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"換取 Token 失敗（HTTP {resp.status_code}）：{resp.text}")

    token_data = resp.json()
    token_data["expires_at"] = time.time() + int(token_data.get("expires_in", 3500)) - 60
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("✅ 已成功取得並儲存 gas_token.json！", flush=True)
    return token_data


def get_valid_access_token() -> str:
    if not TOKEN_PATH.is_file():
        token_data = run_local_oauth_flow()
        return token_data["access_token"]

    token_data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    if time.time() < float(token_data.get("expires_at", 0)) and token_data.get("access_token"):
        return token_data["access_token"]

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        token_data = run_local_oauth_flow()
        return token_data["access_token"]

    client = load_client_config()
    resp = requests.post(
        client["token_uri"],
        data={
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    if not resp.ok:
        raise RuntimeError(f"自動刷新 Token 失敗（HTTP {resp.status_code}）：{resp.text}")

    refreshed = resp.json()
    token_data["access_token"] = refreshed["access_token"]
    token_data["expires_at"] = time.time() + int(refreshed.get("expires_in", 3500)) - 60
    if "refresh_token" in refreshed:
        token_data["refresh_token"] = refreshed["refresh_token"]
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return token_data["access_token"]


def deploy_code_gs(description: str | None = None) -> None:
    cfg = load_deploy_config()
    script_id = cfg["script_id"]
    deployment_id = cfg["deployment_id"]
    code_source = CODE_GS_PATH.read_text(encoding="utf-8")

    access_token = get_valid_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    api_base = f"https://script.googleapis.com/v1/projects/{script_id}"

    # 1. 讀取現有專案結構以保留 appsscript.json manifest 與既有 .gs 檔名
    get_res = requests.get(f"{api_base}/content", headers=headers, timeout=20)
    if not get_res.ok:
        raise RuntimeError(
            f"讀取 GAS 專案內容失敗（HTTP {get_res.status_code}）：{get_res.text}\n"
            "請確認已於 https://script.google.com/home/usersettings 開啟「Google Apps Script API」。"
        )
    existing_files = get_res.json().get("files", [])
    manifest_file = next(
        (f for f in existing_files if f.get("type") == "JSON" and f.get("name") == "appsscript"),
        {
            "name": "appsscript",
            "type": "JSON",
            "source": json.dumps(
                {
                    "timeZone": "Asia/Taipei",
                    "dependencies": {},
                    "exceptionLogging": "STACKDRIVER",
                    "runtimeVersion": "V8",
                    "webapp": {"executeAs": "USER_DEPLOYING", "access": "ANYONE_ANONYMOUS"},
                },
                indent=2,
            ),
        },
    )
    server_js_name = next(
        (f["name"] for f in existing_files if f.get("type") == "SERVER_JS"),
        "程式碼",
    )

    updated_files = [
        {"name": manifest_file["name"], "type": "JSON", "source": manifest_file["source"]},
        {"name": server_js_name, "type": "SERVER_JS", "source": code_source},
    ]
    # 保留其他非主檔（若有額外 HTML / 其他檔案）
    for f in existing_files:
        if f.get("name") not in {manifest_file["name"], server_js_name}:
            updated_files.append(
                {"name": f["name"], "type": f["type"], "source": f["source"]}
            )

    # 2. 推送最新程式碼
    put_res = requests.put(
        f"{api_base}/content",
        headers=headers,
        json={"files": updated_files},
        timeout=25,
    )
    if not put_res.ok:
        raise RuntimeError(f"上傳 Code.gs 失敗（HTTP {put_res.status_code}）：{put_res.text}")

    # 3. 建立新版本 (Version)
    desc = description or f"Auto-deploy via deploy_gas.py ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
    ver_res = requests.post(
        f"{api_base}/versions",
        headers=headers,
        json={"description": desc},
        timeout=20,
    )
    if not ver_res.ok:
        raise RuntimeError(f"建立新版本失敗（HTTP {ver_res.status_code}）：{ver_res.text}")
    version_num = ver_res.json()["versionNumber"]

    # 4. 無痛熱更新既有 Web App 部署（維持原 /exec 網址不變）
    dep_res = requests.put(
        f"{api_base}/deployments/{deployment_id}",
        headers=headers,
        json={
            "deploymentConfig": {
                "scriptId": script_id,
                "versionNumber": version_num,
                "manifestFileName": "appsscript",
                "description": desc,
            }
        },
        timeout=20,
    )
    if not dep_res.ok:
        raise RuntimeError(f"更新 Web App 部署失敗（HTTP {dep_res.status_code}）：{dep_res.text}")

    print(
        f"🎉 部署成功！已將 {server_js_name}.gs 推送並熱更新至【第 {version_num} 版】（Webhook 網址維持不變）！"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="一鍵推送並更新 Google Apps Script 部署")
    parser.add_argument("--auth", action="store_true", help="執行本機瀏覽器 OAuth 授權流程")
    parser.add_argument("--desc", type=str, default=None, help="版本更新說明")
    args = parser.parse_args()

    try:
        if args.auth:
            run_local_oauth_flow()
        else:
            deploy_code_gs(args.desc)
        return 0
    except Exception as exc:
        print(f"❌ 執行失敗：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
