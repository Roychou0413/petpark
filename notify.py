#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
價格變動通知
------------
讀取 scrape.py 寫入 prices.json 的 events（降價、漲價、補貨、缺貨、新上架、下架）
與 health（爬蟲異常），組成一則訊息後送到有設定的管道。

管道由環境變數（GitHub → Settings → Secrets and variables → Actions）決定，
沒設定的就略過；全都沒設定時只印出訊息、不會失敗：

  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID   Telegram Bot
  DISCORD_WEBHOOK_URL                     Discord 頻道 Webhook
  SLACK_WEBHOOK_URL                       Slack Incoming Webhook
  LINE_CHANNEL_TOKEN + LINE_TO            LINE Messaging API（push 給使用者／群組 ID）
  NOTIFY_TYPES（選填）                    只通知這些事件，逗號分隔，例如 "down,restock,new"
                                          （health 爬蟲異常警告一律通知）

只用 Python 標準函式庫。
"""
import json, os, sys, pathlib, datetime, urllib.request

ROOT   = pathlib.Path(__file__).parent
PRICES = ROOT / "prices.json"
PAGES_URL = os.environ.get("PAGES_URL", "")

CAT = {"feeder": "餵食器", "litter": "貓砂機", "fountain": "飲水機"}
LABEL = {   # 事件類型 → (標題, 排序)
    "down":     ("🟢 降價", 0),
    "restock":  ("📦 補貨", 1),
    "new":      ("🆕 新上架", 2),
    "relisted": ("🔁 重新上架", 3),
    "up":       ("🔺 漲價", 4),
    "soldout":  ("⚠️ 缺貨", 5),
    "delisted": ("⛔ 下架", 6),
}


def money(n): return f"${n:,}" if isinstance(n, int) else "—"


def line_of(e):
    cat = CAT.get(e.get("category"), e.get("category") or "")
    s = f"・[{cat}] {e['name']} {money(e.get('sale'))}"
    if e["type"] in ("down", "up") and isinstance(e.get("from"), int):
        d = e["sale"] - e["from"]
        pct = round(abs(d) / e["from"] * 100)
        s = f"・[{cat}] {e['name']} {money(e['from'])} → {money(e['sale'])}（{'+' if d > 0 else '−'}{pct}%）"
    return s


def build_message(data):
    allow = {t.strip() for t in os.environ.get("NOTIFY_TYPES", "").split(",") if t.strip()}
    events = [e for e in data.get("events", []) if not allow or e["type"] in allow]
    health = data.get("health", [])
    if not events and not health: return None
    out = [f"🐾 寵物公園價格監控 {data.get('generated_at_display', '')}"]
    for h in health: out.append(f"❗ 爬蟲異常：{h}（網站可能改版，請檢查 Actions 紀錄）")
    for t, (title, _) in sorted(LABEL.items(), key=lambda kv: kv[1][1]):
        group = [e for e in events if e["type"] == t]
        if not group: continue
        out.append(f"\n{title}（{len(group)}）")
        out += [line_of(e) for e in group]
    if PAGES_URL: out.append(f"\n比較表：{PAGES_URL}")
    return "\n".join(out)


def post(url, payload, headers=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r: r.read()


def chunks(text, n):
    """依行切成不超過 n 字的段落（各平台都有單則訊息長度上限）。"""
    buf = ""
    for ln in text.split("\n"):
        if buf and len(buf) + len(ln) + 1 > n: yield buf; buf = ""
        buf = f"{buf}\n{ln}" if buf else ln
    if buf: yield buf


def main():
    try: data = json.loads(PRICES.read_text("utf-8"))
    except Exception as e:                            # noqa
        print(f"讀不到 {PRICES.name}：{e}", file=sys.stderr); return
    # prices.json 不是這次產生的（爬蟲中途當掉）→ 不重送舊事件，只發異常警告
    try:
        age = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(data["generated_at"])
        fresh = age < datetime.timedelta(hours=3)
    except Exception: fresh = False                    # noqa
    if not fresh:
        data = {**data, "events": [], "health": ["本次執行未產生新的 prices.json"]}
    msg = build_message(data)
    if not msg: print("沒有需要通知的變動。"); return
    print(msg)

    env = os.environ.get
    senders = []
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        senders.append(("Telegram", 4000, lambda t: post(
            f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
            {"chat_id": env("TELEGRAM_CHAT_ID"), "text": t, "disable_web_page_preview": True})))
    if env("DISCORD_WEBHOOK_URL"):
        senders.append(("Discord", 1900, lambda t: post(env("DISCORD_WEBHOOK_URL"), {"content": t})))
    if env("SLACK_WEBHOOK_URL"):
        senders.append(("Slack", 3500, lambda t: post(env("SLACK_WEBHOOK_URL"), {"text": t})))
    if env("LINE_CHANNEL_TOKEN") and env("LINE_TO"):
        senders.append(("LINE", 4900, lambda t: post(
            "https://api.line.me/v2/bot/message/push",
            {"to": env("LINE_TO"), "messages": [{"type": "text", "text": t}]},
            {"Authorization": f"Bearer {env('LINE_CHANNEL_TOKEN')}"})))
    if not senders:
        print("\n（未設定任何通知管道，僅輸出於此。設定方式見 README。）"); return

    failed = 0
    for name, limit, send in senders:
        try:
            for part in chunks(msg, limit): send(part)
            print(f"已送出 → {name}")
        except Exception as e:                        # noqa
            failed += 1; print(f"送出失敗 → {name}：{e}", file=sys.stderr)
    if failed == len(senders): sys.exit(1)


if __name__ == "__main__":
    main()
