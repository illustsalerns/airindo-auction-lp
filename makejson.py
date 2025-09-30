import sys
import re
import json
from pathlib import Path

# 使い方: python makejson.py [input.txt] [output.json]
INPUT_FILE = Path(sys.argv[1]) if len(sys.argv) >= 2 else Path("list.txt")
OUTPUT_FILE = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("auctions.json")

def read_text_safely(p: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            return p.read_text(encoding=enc)
        except UnicodeDecodeError:
            pass
    return p.read_bytes().decode("utf-8", errors="ignore")

text = read_text_safely(INPUT_FILE)

# 正規化
text = (text.replace("\r\n", "\n")
             .replace("\r", "\n")
             .replace("\u3000", " ")
             .replace("\t", " "))
lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

items = []
cur = None

# パターン
pat_id   = re.compile(r"^[a-z]\d{10}$", re.IGNORECASE)      # 例: w1201341836
pat_title= re.compile(r"^A\d+\b")                           # 例: A526 ...
pat_date = re.compile(r"\b\d{2}/\d{2}\s*\([^)]*\)")         # 例: 09/26 (金)
pat_time = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")      # 例: 23:24:00 / 9:05

def flush_current():
    if not cur:
        return
    title = cur.get("title", "")
    m = re.match(r"^(A\d+)", title)
    img = (m.group(1) + ".jpg") if m else ""
    date = cur.get("date", "")
    time = cur.get("time", "")
    end = (date + " " + time).strip()
    items.append({
        "id": cur.get("id", ""),
        "title": title,
        "img": img,
        "end": end
    })

for ln in lines:
    # 1) ID行で開始
    if pat_id.match(ln):
        if cur:  # 直前を確定
            flush_current()
        cur = {"id": ln, "title": "", "date": "", "time": ""}
        continue
    if not cur:
        continue

    # 2) タイトル
    if not cur["title"] and pat_title.search(ln):
        cur["title"] = ln
        continue

    # 3) 日付
    if not cur["date"]:
        m = pat_date.search(ln)
        if m:
            cur["date"] = m.group(0)
            # 続く同一行に時刻がある可能性もあるので、ついでに拾う
            mt = pat_time.search(ln)
            if mt and not cur["time"]:
                cur["time"] = mt.group(0)
            continue

    # 4) 時刻（行の途中でもOK）
    if not cur["time"]:
        mt = pat_time.search(ln)
        if mt:
            cur["time"] = mt.group(0)
            continue

# 最後の出品を確定
if cur:
    flush_current()

with OUTPUT_FILE.open("w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=2)

print(f"完了: {OUTPUT_FILE} を作成しました。件数={len(items)}")
