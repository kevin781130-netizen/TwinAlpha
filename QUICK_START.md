# Quick Start

## 1. 建立環境

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r frontend/requirements.txt
cp .env.example .env            # Windows 可手動複製
```

## 2. 驗證

```bash
python scripts/smoke_test.py
```

## 3. 啟動後端

```bash
./start_backend.sh
# Windows: start_backend.bat
```

FastAPI 文件：`http://127.0.0.1:8000/docs`

## 4. 啟動前端

另開終端：

```bash
./start_frontend.sh
# Windows: start_frontend.bat
```

Streamlit：`http://127.0.0.1:8501`

## 5. 單文件文檔

直接雙擊 `invest-os.html`。Markdown 渲染與語法高亮使用 CDN，因此第一次開啟需能連線到 CDN。

> Broker 實盤交易預設未啟用。先使用 Dry Run / Paper Trading 驗證。
