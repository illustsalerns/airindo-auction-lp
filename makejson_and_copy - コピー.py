import re
import json
import shutil
import time
from pathlib import Path

# ========== 設定 ==========
INPUT_FILE = Path("list.txt")
ROOT_DIR = Path(r"D:\事業用\オリジナル\アダルトコンテンツ\オリジナル")
SUB_THUMB_DIR_NAME = "サムネ"
IMG_EXTS = (".jpg", ".jpeg", ".png")

SITE_DIR = Path("site")
SITE_TMP = Path("_site_build_tmp")       # 一時ビルド先
SITE_OLD_PREFIX = "_site_old_"           # 退避フォルダの接頭辞
OUTPUT_JSON_NAME = "auctions.json"
# ==========================

def read_text_safely(p: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            return p.read_text(encoding=enc)
        except UnicodeDecodeError:
            pass
    return p.read_bytes().decode("utf-8", errors="ignore")

# 1) 入力読み込み・正規化
text = read_text_safely(INPUT_FILE)
text = (text.replace("\r\n", "\n")
             .replace("\r", "\n")
             .replace("\u3000", " ")
             .replace("\t", " "))
lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

items = []
cur = None

# パターン
pat_id    = re.compile(r"^[a-zA-Z]\d{10}$")
pat_title = re.compile(r"^(?:A|S|D|L|N)\d+\b", re.IGNORECASE)
pat_date  = re.compile(r"\b\d{2}/\d{2}\s*\([^)]*\)")
pat_time  = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

def flush_current():
    if not cur:
        return
    title = cur.get("title", "")
    img = ""
    m = re.match(r"^([ASDLN]\d+)", title, flags=re.IGNORECASE)
    if m:
        img = m.group(1) + ".jpg"
    date = cur.get("date", "")
    time_str = cur.get("time", "")
    end = (date + " " + time_str).strip()
    items.append({
        "id": cur.get("id", ""),
        "title": title,
        "img": img,
        "end": end
    })

for ln in lines:
    if pat_id.match(ln):
        if cur: flush_current()
        cur = {"id": ln, "title": "", "date": "", "time": ""}
        continue
    if not cur: continue

    if not cur["title"] and pat_title.search(ln):
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

# 2) 一時ビルドフォルダを作成（毎回作り直し）
if SITE_TMP.exists():
    shutil.rmtree(SITE_TMP, ignore_errors=True)
SITE_TMP.mkdir(parents=True, exist_ok=True)
thumbs_tmp = SITE_TMP / "thumbs"
thumbs_tmp.mkdir(parents=True, exist_ok=True)

# 3) 画像コピー（親\{A|S|D|L|N}\サムネ\下から探索）
def find_source_image(root: Path, filename: str) -> Path | None:
    if not filename:
        return None
    first = filename[0].upper()
    if first not in ("A", "S", "D", "L", "N"):
        return None
    base = Path(filename).stem
    cand = root / first / SUB_THUMB_DIR_NAME / filename
    if cand.exists():
        return cand
    for ext in IMG_EXTS:
        c2 = root / first / SUB_THUMB_DIR_NAME / (base + ext)
        if c2.exists():
            return c2
    return None

missing = []
copied = 0
for it in items:
    img = it.get("img") or ""
    if not img: continue
    src = find_source_image(ROOT_DIR, img)
    if not src:
        missing.append(img)
        continue
    shutil.copy2(src, thumbs_tmp / Path(img).name)
    copied += 1

# 4) auctions.json を一時ビルド先に書き込み
with (SITE_TMP / OUTPUT_JSON_NAME).open("w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

# 5) index.html を既存 site からコピー（まだ無い場合はスキップ）
src_index = SITE_DIR / "index.html"
if src_index.exists():
    shutil.copy2(src_index, SITE_TMP / "index.html")
else:
    print("注意: site/index.html が見つかりません。必要なら後で手動で配置してください。")

# 6) 既存 site を「削除」ではなく **リネーム退避** → 新ビルドを本番名にリネーム
def timestamp():
    return time.strftime("%Y%m%d_%H%M%S")

if SITE_DIR.exists():
    old_name = f"{SITE_OLD_PREFIX}{timestamp()}"
    SITE_DIR.rename(old_name)  # 退避（ロックが掛かっていても、削除より通りやすい）
    print(f"旧サイトを {old_name} に退避しました。")

SITE_TMP.rename(SITE_DIR)
print(f"新サイトを {SITE_DIR} として配置しました。items={len(items)} / 画像コピー={copied}")

# 7) 退避フォルダのクリーンアップを試行（ロック中なら残してOK）
#    ※ ここで直ちに消さず、次回実行時や手動で削除でもOK
for p in Path(".").glob(f"{SITE_OLD_PREFIX}*"):
    try:
        shutil.rmtree(p)
    except Exception:
        # まだロック中などで失敗することがある → 次回以降に削除される想定
        pass

if missing:
    print("見つからなかった画像:")
    for m in missing:
        print("  -", m)
