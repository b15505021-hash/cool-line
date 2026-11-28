"""COOL-LINE Antigravity 智慧安裝包 CLI 工具。

僅相依 requests 與 pynacl，供朋友的 Antigravity 檢查進度、設定參數、
產生專屬 Code.gs、設定 LINE Webhook、建立加密 GitHub 倉庫並監看首次爬蟲。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from nacl.public import PublicKey, SealedBox

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PACK_DIR = Path(__file__).resolve().parent
REPO_DIR = PACK_DIR / "repo"

ALLOWED_KEYS = {
    "line_token",
    "line_user_id",
    "github_token",
    "github_owner",
    "gas_url",
    "gemini_key",
    "ntu_student_id",
    "repo_private",
    "repo_name",
}
SECRET_KEYS = {"line_token", "github_token", "gemini_key"}
LINE_USER_ID_RE = re.compile(r"^U[0-9a-fA-F]{32}$")
GAS_URL_RE = re.compile(r"^https://script\.google\.com/macros/s/[^/]+/exec$")
REQUIRED_SECRETS = {
    "NTU_STUDENT_ID",
    "NTU_PASSWORD",
    "LINE_CHANNEL_ACCESS_TOKEN",
    "LINE_USER_ID",
    "GAS_WEBHOOK_URL",
}
REPO_SHA_CHECK_FILES = (
    "cloud_sync.py",
    "rich_menu.py",
    ".github/workflows/daily_cool.yml",
)


def get_state_path() -> Path:
    custom = os.environ.get("COOL_LINE_STATE_PATH", "").strip()
    return Path(custom) if custom else (PACK_DIR / ".install_state.json")


def load_state() -> dict[str, Any]:
    path = get_state_path()
    data: dict[str, Any] = {"repo_private": True, "repo_name": "cool-line"}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except Exception:
            pass
    return data


def save_state(state: dict[str, Any]) -> None:
    path = get_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 雙重防護：絕不把台大密碼寫進任何狀態檔
    clean = {k: v for k, v in state.items() if k in ALLOWED_KEYS}
    path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")


def mask_value(key: str, val: Any) -> str:
    s = str(val)
    if key in SECRET_KEYS:
        return (s[:6] + "…") if len(s) > 6 else "***"
    return s


def gh(method: str, path: str, token: str, **kw: Any) -> requests.Response:
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if "headers" in kw and isinstance(kw["headers"], dict):
        headers.update(kw.pop("headers"))
    kw.setdefault("timeout", 30)
    return requests.request(method, url, headers=headers, **kw)


def line(method: str, path: str, token: str, **kw: Any) -> requests.Response:
    url = path if path.startswith("http") else f"https://api.line.me{path}"
    headers = {"Authorization": f"Bearer {token}"}
    if "headers" in kw and isinstance(kw["headers"], dict):
        headers.update(kw.pop("headers"))
    kw.setdefault("timeout", 30)
    return requests.request(method, url, headers=headers, **kw)


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def cmd_set(key: str, value: str) -> int:
    if key not in ALLOWED_KEYS:
        print(f"❌ 不支援的欄位 `{key}`。可用欄位：{', '.join(sorted(ALLOWED_KEYS))}", file=sys.stderr)
        return 1

    val: Any = value.strip()
    if key == "ntu_student_id":
        if "@" in val:
            val = val.split("@", 1)[0].strip()
        val = val.lower()
    elif key == "repo_private":
        low = val.lower()
        if low in ("true", "1", "yes", "y"):
            val = True
        elif low in ("false", "0", "no", "n"):
            val = False
        else:
            print("❌ repo_private 請輸入 true 或 false。", file=sys.stderr)
            return 1

    state = load_state()
    state[key] = val
    save_state(state)
    print(f"✅ 已儲存 {key} = {mask_value(key, val)}")
    return 0


def _add_result(
    items: list[dict[str, Any]],
    step_id: str,
    icon: str,
    passed: bool,
    detail: str,
) -> None:
    items.append({"id": step_id, "icon": icon, "passed": passed, "detail": detail})


def cmd_status(as_json: bool = False) -> int:
    state = load_state()
    items: list[dict[str, Any]] = []
    state_changed = False

    # 1. deps
    py_ok = sys.version_info >= (3, 9)
    deps_ok = py_ok
    if deps_ok:
        _add_result(items, "deps", "✅", True, f"Python {sys.version.split()[0]} + requests + PyNaCl 就緒")
    else:
        _add_result(items, "deps", "❌", False, f"Python 版本過舊（{sys.version.split()[0]}），需 >= 3.9")

    # 2. line_token
    line_token = str(state.get("line_token") or "").strip()
    line_token_ok = False
    if not line_token:
        _add_result(items, "line_token", "❌", False, "尚未設定 LINE Channel access token")
    else:
        try:
            res = line("GET", "/v2/bot/info", line_token)
            if res.status_code == 200:
                info = res.json()
                bot_name = info.get("displayName", "未命名機器人")
                basic_id = info.get("basicId", "")
                line_token_ok = True
                _add_result(items, "line_token", "✅", True, f"機器人「{bot_name}」（{basic_id}，{mask_value('line_token', line_token)}）")
            else:
                _add_result(items, "line_token", "❌", False, f"LINE Token 驗證失敗（HTTP {res.status_code}）")
        except Exception as exc:
            _add_result(items, "line_token", "❌", False, f"無法連線 LINE API：{exc}")

    # 3. line_user
    line_uid = str(state.get("line_user_id") or "").strip()
    line_user_ok = False
    if not line_token_ok:
        _add_result(items, "line_user", "⏭️", True, "等待 LINE Token 就緒後檢查")
    elif not LINE_USER_ID_RE.match(line_uid):
        _add_result(items, "line_user", "❌", False, "尚未設定或格式錯誤（需為 U 開頭 33 碼 Your user ID）")
    else:
        try:
            res = line("GET", f"/v2/bot/profile/{line_uid}", line_token)
            if res.status_code == 200:
                prof = res.json()
                line_user_ok = True
                _add_result(items, "line_user", "✅", True, f"已加機器人為好友（{prof.get('displayName', line_uid)}）")
            elif res.status_code == 404:
                _add_result(items, "line_user", "❌", False, "User ID 錯了，或你還沒用手機掃 QR Code 加機器人好友（HTTP 404）")
            else:
                _add_result(items, "line_user", "❌", False, f"LINE User 驗證失敗（HTTP {res.status_code}）")
        except Exception as exc:
            _add_result(items, "line_user", "❌", False, f"查詢好友狀態失敗：{exc}")

    # 4. github_token
    gh_token = str(state.get("github_token") or "").strip()
    gh_token_ok = False
    gh_owner = str(state.get("github_owner") or "").strip()
    if not gh_token:
        _add_result(items, "github_token", "❌", False, "尚未設定 GitHub Token")
    else:
        try:
            res = gh("GET", "/user", gh_token)
            if res.status_code == 200:
                login = res.json().get("login", "").strip()
                if login and login != gh_owner:
                    gh_owner = login
                    state["github_owner"] = login
                    state_changed = True
                scope_hdr = res.headers.get("X-OAuth-Scopes")
                if scope_hdr is not None:
                    scopes = {s.strip() for s in scope_hdr.split(",") if s.strip()}
                    missing = [s for s in ("repo", "workflow") if s not in scopes]
                    if missing:
                        _add_result(items, "github_token", "❌", False, f"@{login} 權杖缺少 {'、'.join(missing)} 權限")
                    else:
                        gh_token_ok = True
                        _add_result(items, "github_token", "✅", True, f"已連結 @{login}（權限：repo, workflow）")
                else:
                    gh_token_ok = True
                    _add_result(items, "github_token", "⚠️", True, f"已連結 @{login}（Fine-grained Token，請確定具備寫入權限）")
            else:
                _add_result(items, "github_token", "❌", False, f"GitHub Token 無效（HTTP {res.status_code}）")
        except Exception as exc:
            _add_result(items, "github_token", "❌", False, f"無法連線 GitHub API：{exc}")

    # 5. gas_url（若狀態未填但 LINE Webhook 已有，自動撈回接續）
    webhook_cache: dict[str, Any] | None = None
    if line_token_ok:
        try:
            wh_res = line("GET", "/v2/bot/channel/webhook/endpoint", line_token)
            if wh_res.status_code == 200:
                webhook_cache = wh_res.json()
        except Exception:
            webhook_cache = None

    gas_url = str(state.get("gas_url") or "").strip()
    if not gas_url and webhook_cache:
        candidate = str(webhook_cache.get("endpoint") or "").strip()
        if GAS_URL_RE.match(candidate):
            gas_url = candidate
            state["gas_url"] = gas_url
            state_changed = True

    gas_ok = False
    if not gas_url:
        _add_result(items, "gas_url", "❌", False, "尚未設定 GAS Web App 網址")
    elif not GAS_URL_RE.match(gas_url):
        _add_result(items, "gas_url", "❌", False, "GAS 網址格式錯誤（需為 https://script.google.com/macros/s/.../exec）")
    else:
        try:
            ping_res = requests.post(
                gas_url,
                json={"ping": "cool-line"},
                allow_redirects=True,
                timeout=30,
            )
            body_text = ping_res.text.strip()
            final_url_lower = str(getattr(ping_res, "url", "")).lower()
            if "<html" in body_text.lower() or "accounts.google.com" in body_text.lower() or "accounts.google.com" in final_url_lower:
                _add_result(items, "gas_url", "❌", False, "部署時「誰可以存取」不是「所有人」，請到 GAS 管理部署作業改為所有人")
            else:
                pong_ver = None
                try:
                    j = json.loads(body_text)
                    if isinstance(j, dict) and j.get("status") == "PONG":
                        pong_ver = j.get("version", "unknown")
                except ValueError:
                    pass
                if pong_ver is not None:
                    gas_ok = True
                    _add_result(items, "gas_url", "✅", True, f"GAS 連線正常（PONG 版本 {pong_ver}）")
                elif body_text == "OK":
                    _add_result(items, "gas_url", "⚠️", False, "偵測到舊版 Code.gs（無 PONG 回應），建議重新貼新版並部署")
                else:
                    _add_result(items, "gas_url", "❌", False, f"GAS 回應異常（HTTP {ping_res.status_code}）")
        except Exception as exc:
            _add_result(items, "gas_url", "❌", False, f"無法連線 GAS：{exc}")

    # 6. line_webhook
    line_webhook_ok = False
    if not (line_token_ok and gas_url and GAS_URL_RE.match(gas_url)):
        _add_result(items, "line_webhook", "⏭️", True, "等待 LINE Token 與 GAS 網址就緒")
    else:
        try:
            if webhook_cache is None:
                wh_res = line("GET", "/v2/bot/channel/webhook/endpoint", line_token)
                webhook_cache = wh_res.json() if wh_res.status_code == 200 else {}
            ep = str(webhook_cache.get("endpoint") or "").strip()
            active = bool(webhook_cache.get("active"))
            if ep == gas_url and active:
                line_webhook_ok = True
                _add_result(items, "line_webhook", "✅", True, "LINE Webhook 已指向 GAS 且已啟用 (active=true)")
            elif ep != gas_url:
                _add_result(items, "line_webhook", "❌", False, "LINE Webhook URL 尚未指向目前的 GAS 網址")
            else:
                _add_result(items, "line_webhook", "❌", False, "LINE Webhook URL 正確，但 Use webhook 開關未啟用 (active=false)")
        except Exception as exc:
            _add_result(items, "line_webhook", "❌", False, f"檢查 Webhook 失敗：{exc}")

    # 7. github_repo
    repo_name = str(state.get("repo_name") or "cool-line").strip() or "cool-line"
    repo_ok = False
    if not (gh_token_ok and gh_owner):
        _add_result(items, "github_repo", "⏭️", True, "等待 GitHub Token 就緒")
    else:
        try:
            r_res = gh("GET", f"/repos/{gh_owner}/{repo_name}", gh_token)
            if r_res.status_code != 200:
                _add_result(items, "github_repo", "❌", False, f"尚未建立倉庫 {gh_owner}/{repo_name}")
            else:
                outdated: list[str] = []
                for rel in REPO_SHA_CHECK_FILES:
                    local_file = REPO_DIR / rel
                    if not local_file.is_file():
                        continue
                    local_sha = git_blob_sha(local_file.read_bytes())
                    c_res = gh("GET", f"/repos/{gh_owner}/{repo_name}/contents/{rel}", gh_token)
                    if c_res.status_code != 200 or c_res.json().get("sha") != local_sha:
                        outdated.append(rel)
                if outdated:
                    _add_result(items, "github_repo", "❌", False, f"倉庫存在但程式碼需更新（{', '.join(outdated)}）")
                else:
                    repo_ok = True
                    _add_result(items, "github_repo", "✅", True, f"倉庫 {gh_owner}/{repo_name} 與主程式已就緒")
        except Exception as exc:
            _add_result(items, "github_repo", "❌", False, f"檢查倉庫失敗：{exc}")

    # 8. github_secrets
    secrets_ok = False
    if not repo_ok:
        _add_result(items, "github_secrets", "⏭️", True, "等待 GitHub 倉庫就緒")
    else:
        try:
            s_res = gh("GET", f"/repos/{gh_owner}/{repo_name}/actions/secrets", gh_token)
            if s_res.status_code == 200:
                names = {s.get("name") for s in s_res.json().get("secrets", [])}
                missing_sec = sorted(REQUIRED_SECRETS - names)
                if not missing_sec:
                    secrets_ok = True
                    _add_result(items, "github_secrets", "✅", True, "5 組 GitHub Secrets 已全數設定")
                else:
                    _add_result(items, "github_secrets", "❌", False, f"缺少 Secrets：{', '.join(missing_sec)}")
            else:
                _add_result(items, "github_secrets", "❌", False, f"讀取 Secrets 失敗（HTTP {s_res.status_code}）")
        except Exception as exc:
            _add_result(items, "github_secrets", "❌", False, f"檢查 Secrets 失敗：{exc}")

    # 9. first_run
    if not secrets_ok:
        _add_result(items, "first_run", "⏭️", True, "等待 Secrets 設定完成")
    else:
        try:
            run_res = gh("GET", f"/repos/{gh_owner}/{repo_name}/actions/runs?per_page=1", gh_token)
            if run_res.status_code == 200:
                runs = run_res.json().get("workflow_runs", [])
                if runs and runs[0].get("conclusion") == "success":
                    _add_result(items, "first_run", "✅", True, "最近一次雲端爬蟲測試已成功！")
                elif runs:
                    st = runs[0].get("conclusion") or runs[0].get("status")
                    _add_result(items, "first_run", "❌", False, f"最近一次雲端爬蟲狀態為 {st}，請執行 run-test")
                else:
                    _add_result(items, "first_run", "❌", False, "尚未執行過首次雲端爬蟲測試")
            else:
                _add_result(items, "first_run", "❌", False, f"查詢 Actions 紀錄失敗（HTTP {run_res.status_code}）")
        except Exception as exc:
            _add_result(items, "first_run", "❌", False, f"查詢執行紀錄失敗：{exc}")

    if state_changed:
        save_state(state)

    next_step = next((it["id"] for it in items if not it["passed"]), "done")
    if as_json:
        print(json.dumps({"steps": items, "next_step": next_step}, ensure_ascii=False, indent=2))
    else:
        print("📋 COOL-LINE 安裝狀態檢查")
        print("-" * 56)
        for it in items:
            print(f"{it['icon']} {it['id']:<15} | {it['detail']}")
        print("-" * 56)
        print(f"NEXT_STEP={next_step}")
    return 0


def cmd_gen_gas() -> int:
    state = load_state()
    line_token = str(state.get("line_token") or "").strip()
    line_uid = str(state.get("line_user_id") or "").strip()
    gh_owner = str(state.get("github_owner") or "").strip()
    gh_token = str(state.get("github_token") or "").strip()
    gemini_key = str(state.get("gemini_key") or "").strip()
    repo_name = str(state.get("repo_name") or "cool-line").strip() or "cool-line"

    missing = [
        name
        for name, val in (
            ("line_token", line_token),
            ("line_user_id", line_uid),
            ("github_owner", gh_owner),
            ("github_token", gh_token),
        )
        if not val
    ]
    if missing:
        print(f"❌ 缺少必要設定無法產生 Code.gs：{', '.join(missing)}", file=sys.stderr)
        return 1

    tpl_path = REPO_DIR / "gas" / "Code.gs"
    if not tpl_path.is_file():
        print(f"❌ 找不到範本檔：{tpl_path}", file=sys.stderr)
        return 1

    code = tpl_path.read_text(encoding="utf-8")
    code = code.replace("'請填入您的_LINE_CHANNEL_ACCESS_TOKEN'", json.dumps(line_token, ensure_ascii=False), 1)
    code = code.replace("'請填入您的_LINE_USER_ID'", json.dumps(line_uid, ensure_ascii=False), 1)
    if gemini_key:
        code = code.replace("'請填入您的_GEMINI_API_KEY'", json.dumps(gemini_key, ensure_ascii=False), 1)
    code = code.replace("'請填入您的_GITHUB_REPO'", json.dumps(f"{gh_owner}/{repo_name}", ensure_ascii=False), 1)
    code = code.replace("'請填入您的_GITHUB_PAT'", json.dumps(gh_token, ensure_ascii=False), 1)

    out_path = PACK_DIR / "Code.personal.gs"
    out_path.write_text(code, encoding="utf-8")
    line_count = len(code.splitlines())
    print(f"✅ 已產生專屬 GAS 程式碼：{out_path.resolve()}（共 {line_count} 行）")
    return 0


def cmd_set_webhook() -> int:
    state = load_state()
    line_token = str(state.get("line_token") or "").strip()
    gas_url = str(state.get("gas_url") or "").strip()
    if not line_token or not gas_url:
        print("❌ 請先設定 line_token 與 gas_url。", file=sys.stderr)
        return 1

    put_res = line(
        "PUT",
        "/v2/bot/channel/webhook/endpoint",
        line_token,
        json={"endpoint": gas_url},
    )
    if not put_res.ok:
        print(f"❌ 設定 Webhook URL 失敗（HTTP {put_res.status_code}）：{put_res.text}", file=sys.stderr)
        return 1

    test_res = line(
        "POST",
        "/v2/bot/channel/webhook/test",
        line_token,
        json={"endpoint": gas_url},
    )
    if test_res.ok:
        data = test_res.json()
        print(
            f"📡 Webhook 測試結果：success={data.get('success')}, "
            f"statusCode={data.get('statusCode')}, reason={data.get('reason')}"
        )
    else:
        print(f"⚠️ Webhook 測試請求回應 HTTP {test_res.status_code}：{test_res.text}")

    print("💡 提醒：請於 LINE Developers 確認「Use webhook」為開啟、於官方帳號回應設定確認「自動回應訊息」為關閉（status 會自動檢查 active 狀態）。")
    return 0


def _raise_if_workflow_perm_error(res: requests.Response, action: str) -> None:
    msg = res.text
    hint = ""
    if res.status_code in (403, 404) and ("workflow" in msg.lower() or "refused" in msg.lower() or res.status_code == 404):
        hint = "（GitHub Token 缺少 workflow 權限或倉庫存取權限不足，請重新產生同時勾選 repo 與 workflow 的 Token）"
    raise RuntimeError(f"{action}失敗（HTTP {res.status_code}）{hint}：{msg}")


def _upload_repo_tree(gh_token: str, owner: str, repo_name: str, branch: str) -> None:
    if not REPO_DIR.is_dir():
        raise FileNotFoundError(f"找不到 repo 程式目錄：{REPO_DIR}")

    ref_res = gh("GET", f"/repos/{owner}/{repo_name}/git/ref/heads/{branch}", gh_token)
    if ref_res.status_code in (404, 409):
        print("  ℹ️ 偵測到空倉庫，先初始化 README.md...")
        readme_bytes = (REPO_DIR / "README.md").read_bytes()
        init_res = gh(
            "PUT",
            f"/repos/{owner}/{repo_name}/contents/README.md",
            gh_token,
            json={
                "message": "chore: initialize cool-line repository",
                "content": base64.b64encode(readme_bytes).decode("ascii"),
                "branch": branch,
            },
        )
        if not init_res.ok:
            _raise_if_workflow_perm_error(init_res, "初始化空倉庫")
        ref_res = gh("GET", f"/repos/{owner}/{repo_name}/git/ref/heads/{branch}", gh_token)

    if not ref_res.ok:
        _raise_if_workflow_perm_error(ref_res, f"讀取分支 {branch}")
    head_sha = ref_res.json()["object"]["sha"]

    commit_res = gh("GET", f"/repos/{owner}/{repo_name}/git/commits/{head_sha}", gh_token)
    if not commit_res.ok:
        _raise_if_workflow_perm_error(commit_res, "讀取最新 Commit")
    base_tree_sha = commit_res.json()["tree"]["sha"]

    tree_entries: list[dict[str, str]] = []
    for file_path in sorted(REPO_DIR.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(REPO_DIR).as_posix()
        if "__pycache__/" in rel:
            continue
        tree_entries.append(
            {
                "path": rel,
                "mode": "100644",
                "type": "blob",
                "content": file_path.read_text(encoding="utf-8"),
            }
        )

    print(f"  📦 正在打包上傳 {len(tree_entries)} 份檔案至 {owner}/{repo_name}...")
    tree_res = gh(
        "POST",
        f"/repos/{owner}/{repo_name}/git/trees",
        gh_token,
        json={"base_tree": base_tree_sha, "tree": tree_entries},
    )
    if not tree_res.ok:
        _raise_if_workflow_perm_error(tree_res, "建立 Git Tree（含 .github/workflows/daily_cool.yml）")

    new_commit = gh(
        "POST",
        f"/repos/{owner}/{repo_name}/git/commits",
        gh_token,
        json={
            "message": "feat: deploy COOL-LINE via Antigravity installer",
            "tree": tree_res.json()["sha"],
            "parents": [head_sha],
        },
    )
    if not new_commit.ok:
        _raise_if_workflow_perm_error(new_commit, "建立 Commit")

    patch_res = gh(
        "PATCH",
        f"/repos/{owner}/{repo_name}/git/refs/heads/{branch}",
        gh_token,
        json={"sha": new_commit.json()["sha"], "force": False},
    )
    if not patch_res.ok:
        _raise_if_workflow_perm_error(patch_res, "更新分支指標（可能缺少 workflow 權限）")
    print("  ✅ 主程式與每日排程已全數上傳完成！")


def _encrypt_secret(pub_key_b64: str, value: str) -> str:
    pub_key = PublicKey(base64.b64decode(pub_key_b64))
    encrypted = SealedBox(pub_key).encrypt(value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def cmd_deploy_github(skip_secrets: bool = False, only_secrets: bool = False) -> int:
    state = load_state()
    gh_token = str(state.get("github_token") or "").strip()
    gh_owner = str(state.get("github_owner") or "").strip()
    repo_name = str(state.get("repo_name") or "cool-line").strip() or "cool-line"
    repo_private = bool(state.get("repo_private", True))

    if not gh_token:
        print("❌ 尚未設定 github_token。", file=sys.stderr)
        return 1

    if not gh_owner:
        u_res = gh("GET", "/user", gh_token)
        if not u_res.ok:
            print(f"❌ 無法驗證 GitHub 帳號（HTTP {u_res.status_code}）。", file=sys.stderr)
            return 1
        gh_owner = u_res.json()["login"]
        state["github_owner"] = gh_owner
        save_state(state)

    ntu_pw = os.environ.get("NTU_PASSWORD", "")
    ntu_id = str(state.get("ntu_student_id") or "").strip()
    line_token = str(state.get("line_token") or "").strip()
    line_uid = str(state.get("line_user_id") or "").strip()
    gas_url = str(state.get("gas_url") or "").strip()

    if not skip_secrets:
        if not ntu_pw:
            print(
                "❌ 缺少環境變數 NTU_PASSWORD，無法加密寫入密碼。\n"
                "請用單次環境變數執行，例如：\n"
                "  PowerShell: $env:NTU_PASSWORD='<密碼>'; python installer.py deploy-github\n"
                "  Mac/Linux:  NTU_PASSWORD='<密碼>' python3 installer.py deploy-github",
                file=sys.stderr,
            )
            return 1
        req_fields = [("ntu_student_id", ntu_id)]
        if not only_secrets:
            req_fields.extend(
                [("line_token", line_token), ("line_user_id", line_uid), ("gas_url", gas_url)]
            )
        missing = [k for k, v in req_fields if not v]
        if missing:
            print(f"❌ 缺少必要設定欄位：{', '.join(missing)}", file=sys.stderr)
            return 1

    print(f"▶ 確認目標倉庫：{gh_owner}/{repo_name}...")
    create_res = gh(
        "POST",
        "/user/repos",
        gh_token,
        json={
            "name": repo_name,
            "description": "COOL-LINE 台大 NTU COOL 智慧死線警報與 LINE 互動行事曆機器人",
            "private": repo_private,
            "auto_init": True,
        },
    )
    if create_res.status_code in (200, 201):
        branch = create_res.json().get("default_branch") or "main"
        print(f"  ✅ 已建立新倉庫 {gh_owner}/{repo_name}（{branch}）")
        time.sleep(2)
    elif create_res.status_code == 422:
        repo_res = gh("GET", f"/repos/{gh_owner}/{repo_name}", gh_token)
        if not repo_res.ok:
            print(f"❌ 無法讀取既有倉庫（HTTP {repo_res.status_code}）：{repo_res.text}", file=sys.stderr)
            return 1
        branch = repo_res.json().get("default_branch") or "main"
        print(f"  ℹ️ 倉庫已存在，使用既有分支 {branch}")
    else:
        print(f"❌ 建立倉庫失敗（HTTP {create_res.status_code}）：{create_res.text}", file=sys.stderr)
        return 1

    if not only_secrets:
        _upload_repo_tree(gh_token, gh_owner, repo_name, branch)

    if not skip_secrets:
        print("▶ 取得倉庫公鑰並進行 Curve25519 SealedBox 本機加密...")
        pk_res = gh("GET", f"/repos/{gh_owner}/{repo_name}/actions/secrets/public-key", gh_token)
        if not pk_res.ok:
            print(f"❌ 讀取公鑰失敗（HTTP {pk_res.status_code}）：{pk_res.text}", file=sys.stderr)
            return 1
        pk_data = pk_res.json()
        key_id = pk_data["key_id"]
        pub_key_b64 = pk_data["key"]

        secret_pairs = [
            ("NTU_STUDENT_ID", ntu_id),
            ("NTU_PASSWORD", ntu_pw),
        ]
        if not only_secrets:
            secret_pairs.extend(
                [
                    ("LINE_CHANNEL_ACCESS_TOKEN", line_token),
                    ("LINE_USER_ID", line_uid),
                    ("GAS_WEBHOOK_URL", gas_url),
                ]
            )

        for sec_name, sec_val in secret_pairs:
            enc_val = _encrypt_secret(pub_key_b64, sec_val)
            put_sec = gh(
                "PUT",
                f"/repos/{gh_owner}/{repo_name}/actions/secrets/{sec_name}",
                gh_token,
                json={"encrypted_value": enc_val, "key_id": key_id},
            )
            if not put_sec.ok:
                print(f"❌ 寫入 Secret {sec_name} 失敗（HTTP {put_sec.status_code}）：{put_sec.text}", file=sys.stderr)
                return 1
            print(f"  🔐 已本機加密寫入 Secret：{sec_name}")

    print("🎉 GitHub 雲端部署完成！")
    return 0


def _parse_gh_time(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def cmd_run_test(timeout_sec: int = 180) -> int:
    state = load_state()
    gh_token = str(state.get("github_token") or "").strip()
    gh_owner = str(state.get("github_owner") or "").strip()
    repo_name = str(state.get("repo_name") or "cool-line").strip() or "cool-line"
    if not gh_token or not gh_owner:
        print("❌ 請先完成 github_token 與 github_owner 設定。", file=sys.stderr)
        return 1

    repo_res = gh("GET", f"/repos/{gh_owner}/{repo_name}", gh_token)
    if not repo_res.ok:
        print(f"❌ 找不到倉庫 {gh_owner}/{repo_name}（HTTP {repo_res.status_code}）", file=sys.stderr)
        return 1
    branch = repo_res.json().get("default_branch") or "main"
    actions_url = f"https://github.com/{gh_owner}/{repo_name}/actions"

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=10)
    dispatched = False
    for attempt in range(1, 6):
        d_res = gh(
            "POST",
            f"/repos/{gh_owner}/{repo_name}/actions/workflows/daily_cool.yml/dispatches",
            gh_token,
            json={"ref": branch},
        )
        if d_res.status_code == 204 or d_res.ok:
            dispatched = True
            break
        print(f"⏳ 等待 GitHub 索引工作流，重試中（{attempt}/5）...", flush=True)
        time.sleep(3)

    if not dispatched:
        print(f"❌ 無法觸發 workflow_dispatch，請前往 {actions_url} 手動確認。")
        print("RESULT=failure")
        return 1

    print("🚀 已觸發首次雲端爬蟲測試，正在監看進度...", flush=True)
    deadline = time.time() + timeout_sec
    last_status = ""
    while time.time() < deadline:
        time.sleep(6)
        runs_res = gh(
            "GET",
            f"/repos/{gh_owner}/{repo_name}/actions/runs?per_page=5&event=workflow_dispatch",
            gh_token,
        )
        if not runs_res.ok:
            continue
        runs = runs_res.json().get("workflow_runs", [])
        target = next((r for r in runs if _parse_gh_time(r["created_at"]) >= cutoff), None)
        if not target:
            continue

        status = target.get("status", "")
        if status != last_status and status != "completed":
            last_status = status
            print(f"  ⚙️ 目前狀態：{status}...", flush=True)

        if status == "completed":
            conclusion = target.get("conclusion")
            run_url = target.get("html_url", actions_url)
            if conclusion == "success":
                print(f"🎉 雲端首次爬蟲測試完全成功！紀錄：{run_url}")
                print("RESULT=success")
                return 0

            failed_steps: list[str] = []
            jobs_res = gh("GET", f"/repos/{gh_owner}/{repo_name}/actions/runs/{target['id']}/jobs", gh_token)
            if jobs_res.ok:
                for job in jobs_res.json().get("jobs", []):
                    for step in job.get("steps", []):
                        if step.get("conclusion") == "failure":
                            failed_steps.append(step.get("name", "unknown"))
            step_info = ", ".join(failed_steps) if failed_steps else str(conclusion)
            print(f"❌ 測試失敗（{conclusion}）｜失敗步驟：{step_info}")
            print(f"   詳細紀錄：{run_url}")
            print("💡 最常見原因是台大帳密錯誤 → 重新詢問密碼後執行 `deploy-github --only-secrets` 再 `run-test`")
            print("RESULT=failure")
            return 1

    print(f"⏳ 等待逾時（超過 {timeout_sec} 秒仍在執行），請前往查看：{actions_url}")
    print("RESULT=timeout")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="COOL-LINE Antigravity 智慧安裝包 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="唯讀檢查目前所有安裝步驟與下一步")
    p_status.add_argument("--json", action="store_true", help="以 JSON 格式輸出")

    p_set = sub.add_parser("set", help="儲存單一安裝設定欄位")
    p_set.add_argument("key", help="欄位名稱")
    p_set.add_argument("value", help="欄位值")

    sub.add_parser("gen-gas", help="產生已填入個人金鑰的 Code.personal.gs")
    sub.add_parser("set-webhook", help="將 LINE Webhook 設為 gas_url 並執行連線測試")

    p_deploy = sub.add_parser("deploy-github", help="建立／更新 GitHub 倉庫並本機加密寫入 Secrets")
    p_deploy.add_argument("--skip-secrets", action="store_true", help="只更新程式碼，不覆蓋 Secrets")
    p_deploy.add_argument("--only-secrets", action="store_true", help="只更新台大帳密 Secrets，不重傳程式碼")

    p_run = sub.add_parser("run-test", help="觸發並輪詢首次 GitHub Actions 爬蟲結果")
    p_run.add_argument("--timeout", type=int, default=180, help="最長等待秒數（預設 180）")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "status":
        return cmd_status(as_json=args.json)
    if args.cmd == "set":
        return cmd_set(args.key, args.value)
    if args.cmd == "gen-gas":
        return cmd_gen_gas()
    if args.cmd == "set-webhook":
        return cmd_set_webhook()
    if args.cmd == "deploy-github":
        return cmd_deploy_github(skip_secrets=args.skip_secrets, only_secrets=args.only_secrets)
    if args.cmd == "run-test":
        return cmd_run_test(timeout_sec=args.timeout)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
