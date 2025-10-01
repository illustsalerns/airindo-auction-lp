import re
import json
import shutil
import time
import os
from pathlib import Path

# ========== 設定 ==========
INPUT_FILE = Path("list.txt")
ROOT_DIR = Path(r"D:\事業用\オリジナル\アダルトコンテンツ\オリジナル")
SUB_THUMB_DIR_NAME = "サムネ"
IMG_EXTS = (".jpg", ".jpeg", ".png")

SITE_DIR = Path("docs")
SITE_TMP = Path("_site_build_tmp")
SITE_OLD_PREFIX = "_site_old_"
OUTPUT_JSON_NAME = "auctions.json"

RETRY = 10           # リトライ回数
SLEEP_SEC = 0.8      # リトライ間隔
# ==========================

def read_text_safely(p: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            return p.read_text(encoding=enc)
        except UnicodeDecodeError:
            pass
    return p.read_bytes().decode("utf-8", errors="ignore")

# 1) 入力読み込み・整形
text = read_text_safely(INPUT_FILE)
text = (text.replace("\r\n", "\n")
             .replace("\r", "\n")
             .replace("\u3000", " ")
             .replace("\t", " "))
lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

items = []
cur = None

# パターン（要件）
pat_id    = re.compile(r"^[a-zA-Z]\d{10}$")
pat_title = re.compile(r"^([ASDLN]\d{3})\b", re.IGNORECASE)   # 先頭4文字がサムネ名ベース
pat_date  = re.compile(r"\b\d{2}/\d{2}\s*\([^)]*\)")
pat_time  = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

def flush_current():
    if not cur: return
    title = cur.get("title", "")
    img_base = ""
    m_head = pat_title.match(title)
    if m_head:
        img_base = m_head.group(1).upper()
    end = (cur.get("date", "") + " " + cur.get("time", "")).strip()
    items.append({
        "id": cur.get("id", ""),
        "title": title,
        "img": (img_base + ".jpg") if img_base else "",
        "img_base": img_base,
        "end": end
    })

for ln in lines:
    if pat_id.match(ln):
        if cur: flush_current()
        cur = {"id": ln, "title": "", "date": "", "time": ""}
        continue
    if not cur: continue

    if not cur["title"]:
        m = pat_title.match(ln)
        if m:
            cur["title"] = ln
            continue

    if not cur["date"]:
        m = pat_date.search(ln)
        if m:
            cur["date"] = m.group(0)
            mt = pat_time.search(ln)
            if mt and not cur["time"]:
                cur["time"] = mt.group(0)
            continue

    if not cur["time"]:
        mt = pat_time.search(ln)
        if mt:
            cur["time"] = mt.group(0)
            continue

if cur: flush_current()

# 2) 一時ビルド作成（毎回クリーン）
if SITE_TMP.exists():
    shutil.rmtree(SITE_TMP, ignore_errors=True)
SITE_TMP.mkdir(parents=True, exist_ok=True)
thumbs_tmp = SITE_TMP / "thumbs"
thumbs_tmp.mkdir(parents=True, exist_ok=True)

def find_source_image(root: Path, img_base: str) -> Path | None:
    if not img_base:
        return None
    first = img_base[0].upper()
    if first not in ("A","S","D","L","N"):
        return None
    for ext in IMG_EXTS:
        cand = root / first / SUB_THUMB_DIR_NAME / (img_base + ext)
        if cand.exists():
            return cand
    return None

# 3) 画像コピー（実拡張子を反映）
missing = []
copied = 0
for it in items:
    base = it.get("img_base") or ""
    if not base: continue
    src = find_source_image(ROOT_DIR, base)
    if not src:
        missing.append(base + ".*")
        continue
    dst_name = base + src.suffix.lower()
    shutil.copy2(src, thumbs_tmp / dst_name)
    it["img"] = dst_name
    it.pop("img_base", None)
    copied += 1

for it in items:
    it.pop("img_base", None)

# 4) auctions.json
with (SITE_TMP / OUTPUT_JSON_NAME).open("w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

# 5) index.html を既存 site からコピー（無ければスキップ）
src_index = SITE_DIR / "index.html"
if src_index.exists():
    shutil.copy2(src_index, SITE_TMP / "index.html")
else:
    print("注意: site/index.html が見つかりません。必要なら後で配置してください。")

# 6) 昇格ロジック（ロックに強い）
def ts():
    return time.strftime("%Y%m%d_%H%M%S")

def try_rename(src: Path, dst: Path) -> bool:
    for _ in range(RETRY):
        try:
            src.rename(dst)
            return True
        except Exception:
            time.sleep(SLEEP_SEC)
    return False

def copy_tree_overwrite(src: Path, dst: Path):
    """src の中身を dst に上書きコピー（削除しない）。
       thumbs は古いファイルを残さないため、まず dst/thumbs を削除→再作成を試す。
    """
    thumbs_dst = dst / "thumbs"
    # thumbs はできる限り消す（ロック時は残るが、上書きで実害は小さい）
    if thumbs_dst.exists():
        try:
            shutil.rmtree(thumbs_dst)
        except Exception:
            pass
    thumbs_dst.mkdir(parents=True, exist_ok=True)

    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in files:
            s = Path(root) / name
            d = (dst / rel) / name
            try:
                shutil.copy2(s, d)
            except Exception:
                # ロック中などで一部失敗する可能性。次回で上書きされる想定。
                pass

# 6-1) 旧 site を退避（rename リトライ）
old_name = f"{SITE_OLD_PREFIX}{ts()}"
if SITE_DIR.exists():
    if not try_rename(SITE_DIR, Path(old_name)):
        print(f"警告: 旧サイト退避に失敗（ロックの可能性）: {SITE_DIR} -> {old_name}")

# 6-2) 新ビルドを本番へ（rename リトライ or フォールバック）
if not SITE_DIR.exists():
    # 空いていれば丸ごとリネーム
    if not try_rename(SITE_TMP, SITE_DIR):
        print("警告: 新サイトのリネームに失敗。フォールバックで上書きコピーします。")
        SITE_DIR.mkdir(parents=True, exist_ok=True)
        copy_tree_overwrite(SITE_TMP, SITE_DIR)
else:
    # site が残っている（退避に失敗）→ フォールバックで上書きコピー
    print("警告: site が残っているため、フォールバックで上書きコピーします。")
    copy_tree_overwrite(SITE_TMP, SITE_DIR)

# 7) 退避フォルダを可能なら削除
for p in Path(".").glob(f"{SITE_OLD_PREFIX}*"):
    try:
        shutil.rmtree(p)
    except Exception:
        pass

print(f"配置完了: {SITE_DIR}  items={len(items)}  画像コピー={copied}")
if missing:
    print("見つからなかった画像（要確認）:")
    for m in missing:
        print(f"  - {m}")
