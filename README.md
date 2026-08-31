# 寵物公園 智能家電比較表 · 自動更新價格（auto-discovery 版）

一個可直接放上 GitHub 的小專案：每天自動從寵物公園（shop.petpark.com.tw）的
三個分類頁（自動餵食器 / 智能貓砂機 / 自動飲水機）**自動抓取目前在架的商品清單**，
更新價格與庫存，並在比較表網頁上標示最新價格、庫存、上下架狀態與「較前次的漲跌」。

## 這版解決了什麼

舊版是「固定商品清單」，分類頁上下架後不會同步，會發生：漏抓新上架商品、
或持續追蹤已下架商品。這版改為 **auto-discovery**：

- 爬蟲每次執行都先去分類頁抓「目前在架」的商品，**新上架的自動加入**。
- 分類頁上不再出現的，標記為 **已下架**（listed=false）並持續保留追蹤（不自動刪除），
  網頁會顯示「已下架」灰標。
- `products.json` 會被自動補上新商品；已下架的仍留著（要不要移除由你決定）。

## 檔案說明

| 檔案 | 用途 |
| --- | --- |
| `index.html` | 比較表網頁。讀取同資料夾的 `prices.json` 顯示即時價格、庫存、上下架、漲跌 |
| `prices.json` | 目前價格快照（由爬蟲產生，網頁讀這份）。已內含初始資料 |
| `products.json` | 已知商品清單（爬蟲會自動補新商品；已下架的會保留） |
| `scrape.py` | 爬蟲：自動抓分類 → 解析每頁價格/庫存 → 寫 `prices.json`、附加 `history.csv`。純標準庫、免安裝 |
| `history.csv` | 每次執行附加，累積價格與上下架歷史，可丟 Excel 看趨勢 |
| `.github/workflows/update-prices.yml` | GitHub Actions 排程：每天自動跑並提交更新 |

## 為什麼不能讓 HTML 自己抓價？

瀏覽器的跨來源限制（CORS）會擋掉網頁直接抓 petpark。做法是由 GitHub 伺服器
（Actions）負責抓價、寫成 `prices.json`，網頁只讀「同一個網址底下」的 `prices.json`
→ 同源、沒有 CORS 問題。
（用檔案總管直接打開 `index.html`（file://）只會看到靜態快照；發佈到 Pages 後才會顯示每日更新。）

## 安裝步驟（約 5 分鐘）

1. **建立 repo**：GitHub 建新儲存庫（Public 才能用免費 Pages），上傳全部檔案，
   **保留 `.github/workflows/` 資料夾結構**。
2. **開啟 Pages**：Settings → Pages → Source 選 `main` / `/(root)` → Save，
   取得網址 `https://<帳號>.github.io/<repo>/`。
3. **允許 Actions 寫入**：Settings → Actions → General → Workflow permissions →
   選 **Read and write permissions** → Save。
4. 排程每天台灣時間 06:00 自動更新；也可到 **Actions → Update petpark prices →
   Run workflow** 手動跑一次。

## 首次執行請檢查

到 Actions 記錄確認每個分類都有印出「在架 N 項」、且商品多為 `OK`。
自動抓取仰賴分類頁的商品格線結構（Magento `product-items`）；若寵物公園大改版，
可能需要微調 `scrape.py` 的 `discover()` 或 `parse_product()`。

## 調整分類 / 商品

- **要監控的分類**：改 `scrape.py` 的 `CATEGORIES`（新分類的商品會自動被發現）。
- **在比較表顯示規格/圖片**：新商品會自動進入 `prices.json`（有名稱/價格/庫存），
  但比較表的功能規格與圖片仍是手動整理的——需到 `index.html` 的 `DATA` 內補一筆
  （欄位參考現有商品，`url` 用同一個 petpark 網址，key 會自動對應）；未補的商品
  只是不會出現在表格，價格照樣被抓取記錄。
- **移除已下架商品**：從 `products.json` 刪除該筆即可（預設保留並標示已下架）。

## 注意事項

- 抓取頻率預設一天一次、每次請求間隔 1 秒，對站方友善；請勿改成高頻抓取。
- 價格解析自 petpark 頁面的 meta 與文字；站方改版可能需要微調解析規則。
- 分類頁一次以 `?product_list_limit=150` 取全部；若單一分類超過 150 項才需加分頁處理。
- 本工具僅供內部競品比價參考，價格以商城即時顯示為準。
