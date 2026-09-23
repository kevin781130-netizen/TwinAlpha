"""審計日誌頁面。"""

import hashlib
import json
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="審計日誌", page_icon="🔐", layout="wide")

from utils.theme import inject_custom_css

inject_custom_css()

st.title("🔐 審計日誌")

ROOT = Path(__file__).resolve().parent.parent.parent
AUDIT_PATH = ROOT / "data_lake" / "audit" / "events.jsonl"
PAPER_AUDIT_PATH = ROOT / "data_lake" / "audit" / "paper_trading.jsonl"

log_choice = st.selectbox("選擇日誌", ["主審計日誌", "模擬盤審計日誌"])
log_path = AUDIT_PATH if log_choice == "主審計日誌" else PAPER_AUDIT_PATH

if not log_path.exists():
    st.warning(f"找不到日誌檔案：{log_path}")
    st.stop()

try:
    with open(log_path) as f:
        records = [json.loads(line) for line in f if line.strip()]
except Exception as e:
    st.error(f"讀取失敗：{e}")
    st.stop()

st.markdown(f"**檔案**：`{log_path.name}` · **共 {len(records)} 筆**")
st.divider()

st.subheader("🛡️ 完整性驗證")
if st.button("🔍 驗證日誌完整性", type="primary"):
    prev_hash = "0" * 64
    errors = []
    for i, record in enumerate(records):
        if record.get("prev_hash") != prev_hash:
            errors.append({"line": i, "error": "hash chain broken",
                           "expected": prev_hash[:16] + "...",
                           "actual": (record.get("prev_hash") or "")[:16] + "..."})

        actual_hash = record.get("hash")
        check = {k: v for k, v in record.items() if k != "hash"}
        canonical = json.dumps(check, sort_keys=True, default=str)
        expected = hashlib.sha256(canonical.encode()).hexdigest()

        if actual_hash != expected:
            errors.append({"line": i, "error": "hash mismatch",
                           "expected": expected[:16] + "...",
                           "actual": (actual_hash or "")[:16] + "..."})

        prev_hash = actual_hash or prev_hash

    if errors:
        st.error(f"❌ 發現 {len(errors)} 個錯誤")
        st.dataframe(pd.DataFrame(errors), use_container_width=True)
    else:
        st.success(f"✅ 全部 {len(records)} 筆記錄完整無損")
        st.caption(f"最終哈希：`{prev_hash[:32]}...`")

st.divider()
st.subheader("📊 事件類型分佈")

event_types = {}
for r in records:
    et = r.get("event_type", "UNKNOWN")
    event_types[et] = event_types.get(et, 0) + 1

if event_types:
    import plotly.graph_objects as go
    fig = go.Figure(data=[go.Bar(x=list(event_types.keys()),
                                  y=list(event_types.values()),
                                  marker_color="#00A3A3")])
    fig.update_layout(template="plotly_dark", height=300,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=40, r=20, t=20, b=40))
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("📋 最近記錄")

limit = st.slider("顯示筆數", 10, 200, 50)
records_display = []
for r in records[-limit:][::-1]:
    records_display.append({
        "時間": r.get("timestamp", "")[:19],
        "類型": r.get("event_type", ""),
        "摘要": json.dumps(r.get("data", {}), ensure_ascii=False)[:100],
        "哈希": (r.get("hash") or "")[:16] + "...",
    })

if records_display:
    st.dataframe(pd.DataFrame(records_display), use_container_width=True, hide_index=True)

with st.expander("查看完整記錄"):
    selected_idx = st.number_input("記錄索引（從 0 開始）",
                                    min_value=0, max_value=max(0, len(records) - 1),
                                    value=max(0, len(records) - 1))
    if 0 <= selected_idx < len(records):
        st.json(records[selected_idx])
