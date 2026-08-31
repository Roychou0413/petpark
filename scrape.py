#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
寵物公園（shop.petpark.com.tw）價格監控爬蟲
--------------------------------------------------
讀取 products.json（商品清單），逐一抓取每個商品頁，
解析「特價 / 一般價格」與庫存狀態，輸出：
  - prices.json  ← 供 index.html 同源讀取（含更新時間、漲跌、庫存）
  - history.csv  ← 每次執行附加一列，累積價格歷史（可做趨勢分析）

只用 Python 標準函式庫，無需 pip 安裝任何套件。
"""

import json, re, csv, sys, time, gzip, datetime, pathlib
import urllib.request, urllib.error

ROOT     = pathlib.Path(__file__).parent
PRODUCTS = ROOT / "products.json"
PRICES   = ROOT / "prices.json"
HISTORY  = ROOT / "history.csv"

UA  = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TZ8 = datetime.timezone(datetime.timedelta(hours=8))   # 台灣時間
POLITE_DELAY = 1.0   # 每次請求間隔秒數，對站方友善


def fetch(url, tries=3):
    """抓取頁面 HTML，含重試與 gzip 解壓。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept-Language": "zh-TW,zh;q=0.9",
                "Accept-Encoding": "gzip",
                "Accept": "text/html,application/xhtml+xml",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", "ignore")
        except Exception as e:               # noqa
            last = e
            time.sleep(2 * (i + 1))
    raise last


def _num(s):
    return int(re.sub(r"[^\d]", "", s))


def parse(html):
    """
    從商品頁 HTML 解析 (sale, orig, stock, qty, title)。
    價格以 Open Graph meta 為主，輔以頁面文字；容忍中間夾帶 HTML 標籤。
    """
    # --- 特價（目前售價）：優先取 og price meta ---
    sale = None
    m = (re.search(r'product:price:amount"\s*content="([\d.]+)"', html)
         or re.search(r'content="([\d.]+)"\s*property="product:price:amount"', html))
    if m:
        sale = int(float(m.group(1)))

    # --- 頁面文字中的「特價 / 一般價格」（容忍夾帶標籤/空白）---
    ms = re.search(r'特價[^$0-9]{0,80}\$?\s*([\d,]{2,})', html)
    mo = re.search(r'一般價格[^$0-9]{0,80}\$?\s*([\d,]{2,})', html)
    if sale is None and ms:
        sale = _num(ms.group(1))
    orig = _num(mo.group(1)) if mo else None

    # 後備：抓買區附近第一個 $ 金額
    if sale is None:
        m2 = re.search(r'\$\s*([\d,]{2,})', html)
        if m2:
            sale = _num(m2.group(1))
    if orig is None:
        orig = sale   # 沒有標一般價 → 視為無折扣（頁面端不顯示折扣）

    # --- 庫存 ---
    stock, qty = "unknown", None
    if any(k in html for k in ("無庫存", "補貨中", "已售完", "缺貨")):
        stock = "out"
    else:
        mq = re.search(r'僅剩[^0-9]{0,20}(\d{1,4})', html)
        if mq:
            stock, qty = "low", int(mq.group(1))
        elif "有庫存" in html:
            stock = "in"

    # --- 標題 ---
    mt = re.search(r'og:title"\s*content="([^"]+)"', html)
    title = mt.group(1).strip() if mt else None

    return sale, orig, stock, qty, title


def load_json(path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:                        # noqa
        return default


def main():
    products = load_json(PRODUCTS, [])
    if not products:
        print("products.json 為空或讀取失敗", file=sys.stderr)
        sys.exit(1)

    prev  = load_json(PRICES, {}).get("items", {})
    now   = datetime.datetime.now(TZ8)
    today = now.strftime("%Y/%m/%d")

    items, rows = {}, []
    ok = fail = 0

    for prod in products:
        key, url = prod["key"], prod["url"]
        old = prev.get(key, {})
        try:
            sale, orig, stock, qty, title = parse(fetch(url))
            if sale is None:
                raise ValueError("找不到價格")

            old_sale = old.get("sale")
            if old_sale is not None and old_sale != sale:
                prev_sale, last_change = old_sale, today          # 價格有變 → 記錄
            else:
                prev_sale = old.get("prev_sale")                  # 沿用先前的變動紀錄
                last_change = old.get("last_change")

            items[key] = {
                "sale": sale, "orig": orig, "stock": stock, "qty": qty,
                "prev_sale": prev_sale, "last_change": last_change,
                "title": title or prod.get("name"), "stale": False,
            }
            ok += 1
            print(f"OK   {key:<11} 特價 ${sale:<6} 一般 ${orig:<6} 庫存={stock}"
                  + (f" 僅剩{qty}" if qty else ""))
        except Exception as e:               # noqa
            fail += 1
            keep = dict(old)                 # 抓失敗 → 保留前次資料，標記 stale
            keep["stale"] = True
            keep["error"] = str(e)[:120]
            keep.setdefault("sale", None)
            items[key] = keep
            print(f"ERR  {key:<11} {e}", file=sys.stderr)

        rows.append([now.strftime("%Y-%m-%d %H:%M"), key,
                     items[key].get("sale"), items[key].get("orig"),
                     items[key].get("stock")])
        time.sleep(POLITE_DELAY)

    out = {
        "generated_at": now.isoformat(),
        "generated_at_display": now.strftime("%Y/%m/%d %H:%M") + "（台灣時間）",
        "source": "shop.petpark.com.tw",
        "count": len(items), "ok": ok, "fail": fail,
        "items": items,
    }
    PRICES.write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")

    is_new = not HISTORY.exists()
    with HISTORY.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["datetime", "key", "sale", "orig", "stock"])
        w.writerows(rows)

    print(f"\n完成：{ok} 筆成功、{fail} 筆失敗 → {PRICES.name}")
    if ok == 0:                              # 全部失敗才讓 CI 失敗
        sys.exit(1)


if __name__ == "__main__":
    main()
