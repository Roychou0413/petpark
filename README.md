# 寵物公園 智能家電比較表 · 自動更新價格

一個可直接放上 GitHub 的小專案：每天自動抓取寵物公園（shop.petpark.com.tw）
23 款商品（自動餵食器 / 智能貓砂機 / 自動飲水機）的價格與庫存，
並在比較表網頁上顯示最新價格、庫存狀態與「較前次的漲跌」。

## 檔案說明

| 檔案 | 用途 |
| --- | --- |
| `index.html` | 比較表網頁（打開即用）。會讀取同資料夾的 `prices.json` 顯示即時價格 |
| `prices.json` | 目前價格快照（由爬蟲產生，網頁讀這份）。已內含一份初始資料 |
| `products.json` | 要監控的商品清單（key＋網址）。**要增減商品改這裡** |
| `scrape.py` | 爬蟲：抓價 → 寫 `prices.json`、附加 `history.csv`。只用 Python 標準庫，免安裝套件 |
| `history.csv` | 每次執行附加一列，累積價格歷史，可丟進 Excel 看趨勢 |
| `.github/workflows/update-prices.yml` | GitHub Actions 排程：每天自動跑爬蟲並提交更新 |

## 為什麼不能讓 HTML 自己抓？

瀏覽器的跨來源限制（CORS）會擋掉網頁直接去抓 petpark 的頁面。
本專案的做法是：**由 GitHub 伺服器（Actions）負責抓價**，把結果寫成 `prices.json`，
網頁只讀「同一個網址底下」的 `prices.json` → 同源、沒有 CORS 問題。

> 直接用檔案總管打開 `index.html`（file:// 開頭）時，瀏覽器同樣會擋本機檔的讀取，
> 因此只會看到「靜態快照」。要看到每日更新的即時價格，請依下方步驟發佈到 GitHub Pages
> （或放到任何一台網頁伺服器）。

## 安裝步驟（約 5 分鐘）

1. **建立 repo**：在 GitHub 建一個新的儲存庫（Public 即可用免費 Pages），
   把本資料夾所有檔案上傳（**保留 `.github/workflows/` 資料夾結構**）。
2. **開啟 Pages**：Repo → Settings → Pages → Source 選 `Deploy from a branch`，
   Branch 選 `main` / `/(root)` → Save。稍候會得到網址：
   `https://<你的帳號>.github.io/<repo 名稱>/`
3. **允許 Actions 寫入**：Repo → Settings → Actions → General →
   Workflow permissions → 選 **Read and write permissions** → Save。
4. **完成**。排程每天台灣時間早上 06:00 自動更新；
   也可到 **Actions 分頁 → Update petpark prices → Run workflow** 立即手動跑一次。

打開你的 Pages 網址，就會看到頂端顯示「🟢 即時價格 · 資料更新時間 …」，
各商品會標示庫存（有庫存／無庫存／僅剩 N）與較前次的漲跌（▼ 綠降價、▲ 紅漲價）。

## 增加 / 移除商品

1. 打開商品的 petpark 頁面，網址最後一段就是 **key**
   （例：`https://shop.petpark.com.tw/wp012155` → key = `wp012155`）。
2. 在 `products.json` 加一筆 `{"key": "...", "category": "...", "name": "...", "url": "..."}`。
   → 爬蟲下次就會抓它的價格與庫存。
3. 若也要在**比較表裡顯示這款的規格/圖片**，需到 `index.html` 的 `DATA` 物件裡，
   在對應分類（feeder / litter / fountain）的 `products` 陣列補一筆
   （欄位可參考現有商品；`url` 用同一個 petpark 網址，key 會自動對應）。
   只加到 `products.json`、沒加到 `index.html` 的話，價格照抓、只是不會出現在表格中。

## 手動在本機測試爬蟲

```bash
python3 scrape.py
```

會印出每款的抓取結果（OK / ERR），並更新 `prices.json` 與 `history.csv`。
（在本機需要能連到 shop.petpark.com.tw。）

## 注意事項 / 限制

- **依賴頁面結構**：價格是從 petpark 頁面的 meta 與文字解析而來。若站方大改版，
  可能需要微調 `scrape.py` 裡的解析規則（`parse()`）。
- **抓取頻率**：預設一天一次、每次請求間隔 1 秒，對站方友善；請勿改成高頻抓取。
- **商品下架 / 改網址**：該商品會抓取失敗，網頁會保留前次價格並標「價格待更新」；
  請到 `products.json` 更新或移除。
- **首次執行**：建議到 Actions 記錄檢查是否每款都顯示 `OK`；若有 `ERR`，
  多半是該商品網址失效或站方擋爬，依訊息調整即可。
- 本工具僅供內部競品比價參考，價格以商城即時顯示為準。
