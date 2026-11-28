"""建置《COOL-LINE Antigravity 智慧安裝包》壓縮檔（同步輸出至 repo 與 D:\\桌面）。

執行後會：
  1. 清空並重建 dist/COOL-LINE_Antigravity安裝包/
  2. 複製 agent_pack/ 全部引導與 CLI（排除暫存與個人狀態檔）
  3. 複製 REPO_FILE_WHITELIST 全部乾淨原始碼至 <out>/repo/
  4. 掃描確定 0 夾帶任何本機 .env 機密與私人憑證檔
  5. 打包成 COOL-LINE_Antigravity安裝包.zip 至專案根目錄與 D:\\桌面
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from build_wizard import REPO_FILE_WHITELIST, assert_no_leaked_secrets

BASE_DIR = Path(__file__).resolve().parent
AGENT_PACK_SRC = BASE_DIR / "agent_pack"
DIST_PACK_DIR = BASE_DIR / "dist" / "COOL-LINE_Antigravity安裝包"
ZIP_NAME = "COOL-LINE_Antigravity安裝包.zip"
OUTPUT_REPO_ZIP = BASE_DIR / ZIP_NAME
OUTPUT_DESKTOP_ZIPS: list[Path] = [
    Path(r"D:\桌面") / ZIP_NAME,
    Path(r"C:\Users\User\Desktop") / ZIP_NAME,
]

FORBIDDEN_FILENAMES = {
    ".env",
    "gas_token.json",
    "gas_oauth_client.json",
    ".gas_deploy_config.json",
    ".install_state.json",
    "Code.personal.gs",
}


def build() -> None:
    if not AGENT_PACK_SRC.is_dir():
        raise FileNotFoundError(f"找不到 agent_pack 目錄：{AGENT_PACK_SRC}")

    if DIST_PACK_DIR.exists():
        shutil.rmtree(DIST_PACK_DIR)
    DIST_PACK_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 複製 agent_pack/（保留 .agents 隱藏資料夾，排除暫存／狀態檔）
    for src_path in AGENT_PACK_SRC.rglob("*"):
        rel = src_path.relative_to(AGENT_PACK_SRC)
        if "__pycache__" in rel.parts or src_path.name in FORBIDDEN_FILENAMES:
            continue
        dst_path = DIST_PACK_DIR / rel
        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

    # 2. 複製乾淨的開源原始碼至 repo/
    repo_dst = DIST_PACK_DIR / "repo"
    for rel_path in REPO_FILE_WHITELIST:
        src_file = BASE_DIR / rel_path
        if not src_file.is_file():
            raise FileNotFoundError(f"找不到白名單檔案：{src_file}")
        target_file = repo_dst / rel_path
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, target_file)

    # 3. 確認 repo/gas/Code.gs 保留乾淨佔位字元
    code_gs_txt = (repo_dst / "gas" / "Code.gs").read_text(encoding="utf-8")
    if "'請填入您的_LINE_CHANNEL_ACCESS_TOKEN'" not in code_gs_txt:
        raise ValueError("repo/gas/Code.gs 缺少佔位字元，請檢查範本！")

    # 4. 全面檢查絕無禁止檔案或 .env 機密外洩
    all_texts: list[str] = []
    for p in DIST_PACK_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.name in FORBIDDEN_FILENAMES:
            raise RuntimeError(f"❌ 禁止的敏感檔案出現在安裝包：{p}")
        try:
            all_texts.append(p.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            pass
    assert_no_leaked_secrets("\n".join(all_texts))

    # 5. 打包成 ZIP（頂層資料夾名稱固定為 COOL-LINE_Antigravity安裝包/）
    OUTPUT_REPO_ZIP.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT_REPO_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(DIST_PACK_DIR.rglob("*")):
            if file_path.is_file():
                arcname = Path("COOL-LINE_Antigravity安裝包") / file_path.relative_to(DIST_PACK_DIR)
                zf.write(file_path, arcname.as_posix())

    print(f"Generated: {OUTPUT_REPO_ZIP} ({OUTPUT_REPO_ZIP.stat().st_size:,} bytes)")
    for desktop_zip in OUTPUT_DESKTOP_ZIPS:
        if desktop_zip.parent.is_dir():
            shutil.copy2(OUTPUT_REPO_ZIP, desktop_zip)
            print(f"Generated: {desktop_zip} ({desktop_zip.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
