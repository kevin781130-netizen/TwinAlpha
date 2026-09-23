# 批次 1 設計說明

手寫幾萬行 HTML 標籤沒有意義。採用**單文件 HTML + Markdown 內嵌**方案：交付物可直接雙擊打開、帶導航和搜索的 HTML 文件，但內容仍以 Markdown 格式維護。後續批次只需追加 `<script type="text/plain" data-title="...">` 段落，瀏覽器會自動渲染。

## 原始使用方式

1. 將完整 HTML 存成 `invest-os.html`。
2. 雙擊即可在瀏覽器打開，無需伺服器。
3. 操作：左側導航切換章節；`Ctrl+K` 聚焦搜尋；`Esc` 清除搜尋；`Ctrl+P` 列印；可用 `invest-os.html#architecture` 深連結。
4. 批次 2–5 原設計為替換 `batch2`–`batch5` placeholder；本打包版已全部合併完成，不需再手動替換。

## 批次進度

| 批次 | 內容 | 狀態 |
|------|------|------|
| 1 | README + ARCHITECTURE + HTML 骨架 | ✅ 已整合 |
| 2 | MODULES Part 1-5（核心/數據/回測/風控/因子） | ✅ 已整合 |
| 3 | MODULES Part 6-11（Agent/組合/執行/審計/API/歸檔） | ✅ 已整合 |
| 4 | RUNBOOK + CHANGELOG | ✅ 已整合 |
| 5 | Streamlit 前端 + CLI 腳本 | ✅ 已整合 |
