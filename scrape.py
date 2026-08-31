#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
寵物公園 價格監控爬蟲（自動抓取版 / auto-discovery）
----------------------------------------------------
每次執行：
  1. 逐一爬 CATEGORIES 的分類頁（?product_list_limit=150 一次取全部），
     自動抓出「目前在架」的商品 key。
  2. 與 products.json（已知商品）合併：
       - 新出現的 → 自動補進 products.json（永不自動刪除）。
       - 已知但這次沒出現的 → 標記 listed=false（已下架），仍保留追蹤。
  3. 逐一抓商品頁，解析特價／一般價格與庫存。
  4. 輸出 prices.json（含 listed 上架狀態、漲跌、庫存），附加 history.csv。

只用 Python 標準函式庫，免安裝任何套件。
"""
import json, re, csv, sys, time, gzip, datetime, pathlib
import urllib.request, urllib.error

ROOT     = pathlib.Path(__file__).parent
PRODUCTS = ROOT / "products.json"
PRICES   = ROOT / "prices.json"
HISTORY  = ROOT / "history.csv"

# 要自動抓取的分類頁（可自行增減；新分類的商品會自動被發現）
CATEGORIES = [
    {"name": "feeder",   "url": "https://shop.petpark.com.tw/houseware/supllies-tableware-automatic-feeder"},
    {"name": "litter",   "url": "https://shop.petpark.com.tw/houseware/catlitter-machine"},
    {"name": "fountain", "url": "https://shop.petpark.com.tw/houseware/drinking-fountain"},
]
LIST_LIMIT = 150   # petpark 分類頁每頁可顯示 50/100/150，取最大值以一次抓完

UA  = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TZ8 = datetime.timezone(datetime.timedelta(hours=8))
POLITE_DELAY = 1.0
BASE = "https://shop.petpark.com.tw/"

# 商品 URL slug 形態：wp+數字 或 6 碼以上純數字（可排除 nav/分類/活動頁連結）
PROD_SLUG = re.compile(r'^(?:wp\d+|\d{6,})$')
LINK_RE   = re.compile(r'https?://shop\.petpark\.com\.tw/([A-Za-z0-9_-]+)')
# 商品格線區塊（Magento 標準 <ol class="products list items product-items">）
GRID_RE   = re.compile(r'<ol[^>]*class="[^"]*product-items[^"]*"[\s\S]*?</ol>')
NON_PRODUCT = set()   # 若日後發現誤判，可把 slug 加進來排除


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9",
                "Accept-Encoding": "gzip", "Accept": "text/html,application/xhtml+xml",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", "ignore")
        except Exception as e:                       # noqa
            last = e; time.sleep(2 * (i + 1))
    raise last


def discover(cat_url):
    """回傳分類頁目前在架的商品 key（依出現順序、去重）。"""
    sep = "&" if "?" in cat_url else "?"
    html = fetch(f"{cat_url}{sep}product_list_limit={LIST_LIMIT}")
    m = GRID_RE.search(html)          # 優先只在商品格線區塊內找，避開頁首頁尾
    scope = m.group(0) if m else html
    keys, seen = [], set()
    for lm in LINK_RE.finditer(scope):
        slug = lm.group(1)
        if PROD_SLUG.match(slug) and slug not in seen and slug not in NON_PRODUCT:
            seen.add(slug); keys.append(slug)
    return keys


def _num(s): return int(re.sub(r"[^\d]", "", s))

def parse_product(html):
    sale = None
    m = (re.search(r'product:price:amount"\s*content="([\d.]+)"', html)
         or re.search(r'content="([\d.]+)"\s*property="product:price:amount"', html))
    if m: sale = int(float(m.group(1)))
    ms = re.search(r'特價[^$0-9]{0,80}\$?\s*([\d,]{2,})', html)
    mo = re.search(r'一般價格[^$0-9]{0,80}\$?\s*([\d,]{2,})', html)
    if sale is None and ms: sale = _num(ms.group(1))
    orig = _num(mo.group(1)) if mo else None
    if sale is None:
        m2 = re.search(r'\$\s*([\d,]{2,})', html)
        if m2: sale = _num(m2.group(1))
    if orig is None: orig = sale
    stock, qty = "unknown", None
    if any(k in html for k in ("無庫存", "補貨中", "已售完", "缺貨")):
        stock = "out"
    else:
        mq = re.search(r'僅剩[^0-9]{0,20}(\d{1,4})', html)
        if mq: stock, qty = "low", int(mq.group(1))
        elif "有庫存" in html: stock = "in"
    mt = re.search(r'og:title"\s*content="([^"]+)"', html)
    title = mt.group(1).strip() if mt else None
    return sale, orig, stock, qty, title


def load_json(path, default):
    try: return json.loads(path.read_text("utf-8"))
    except Exception: return default


def main():
    known = load_json(PRODUCTS, [])
    known_by_key = {p["key"]: dict(p) for p in known}
    prev = load_json(PRICES, {}).get("items", {})
    now = datetime.datetime.now(TZ8)
    today = now.strftime("%Y/%m/%d")

    # 1) 自動抓取各分類目前在架商品
    listed_keys = set()
    disc_fail = 0
    for cat in CATEGORIES:
        try:
            ks = discover(cat["url"])
            print(f"分類 {cat['name']}: 在架 {len(ks)} 項")
            for k in ks:
                listed_keys.add(k)
                if k not in known_by_key:
                    known_by_key[k] = {"key": k, "category": cat["name"],
                                       "name": None, "url": BASE + k}
                    print(f"  ＋ 新商品自動加入：{k}")
        except Exception as e:                        # noqa
            disc_fail += 1
            print(f"分類 {cat['name']} 抓取失敗：{e}", file=sys.stderr)
        time.sleep(POLITE_DELAY)

    # 若所有分類都抓失敗，保守起見不改動上架狀態（避免誤標全部下架）
    trust = disc_fail < len(CATEGORIES)

    # 2) 對 known ∪ discovered 逐一抓商品頁
    items, hist = {}, []
    ok = fail = 0
    for key, meta in known_by_key.items():
        url = meta["url"]; old = prev.get(key, {})
        try:
            sale, orig, stock, qty, title = parse_product(fetch(url))
            if sale is None: raise ValueError("找不到價格")
            osale = old.get("sale")
            if osale is not None and osale != sale:
                prev_sale, last_change = osale, today
            else:
                prev_sale, last_change = old.get("prev_sale"), old.get("last_change")
            listed = (key in listed_keys) if trust else old.get("listed", True)
            if title and not meta.get("name"): meta["name"] = title
            items[key] = {"sale": sale, "orig": orig, "stock": stock, "qty": qty,
                          "prev_sale": prev_sale, "last_change": last_change,
                          "listed": listed, "category": meta.get("category"),
                          "title": meta.get("name") or title, "stale": False}
            ok += 1
            print(f"OK   {key:<11} 特價 ${sale:<6} 一般 ${orig:<6} {stock}"
                  + (f" 僅剩{qty}" if qty else "") + ("" if listed else "  [已下架]"))
        except Exception as e:                        # noqa
            fail += 1
            keep = dict(old); keep["stale"] = True; keep["error"] = str(e)[:120]
            keep.setdefault("sale", None)
            keep["listed"] = (key in listed_keys) if trust else old.get("listed", True)
            items[key] = keep
            print(f"ERR  {key:<11} {e}", file=sys.stderr)
        hist.append([now.strftime("%Y-%m-%d %H:%M"), key, items[key].get("sale"),
                     items[key].get("orig"), items[key].get("stock"),
                     int(bool(items[key].get("listed")))])
        time.sleep(POLITE_DELAY)

    listed_ct = sum(1 for v in items.values() if v.get("listed"))
    out = {"generated_at": now.isoformat(),
           "generated_at_display": now.strftime("%Y/%m/%d %H:%M") + "（台灣時間）",
           "source": "shop.petpark.com.tw", "count": len(items),
           "listed": listed_ct, "delisted": len(items) - listed_ct,
           "ok": ok, "fail": fail, "items": items}
    PRICES.write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")

    # 回寫 products.json（新商品補入，永不自動刪除）
    merged = sorted(known_by_key.values(), key=lambda p: (p.get("category") or "", p["key"]))
    PRODUCTS.write_text(json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")

    is_new = not HISTORY.exists()
    with HISTORY.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if is_new: w.writerow(["datetime", "key", "sale", "orig", "stock", "listed"])
        w.writerows(hist)

    print(f"\n完成：{ok} ok / {fail} fail；在架 {listed_ct}、已下架 {len(items)-listed_ct} → {PRICES.name}")
    if ok == 0: sys.exit(1)


if __name__ == "__main__":
    main()
