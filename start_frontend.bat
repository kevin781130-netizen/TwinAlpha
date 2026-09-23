@echo off
cd /d %~dp0
python -m streamlit run frontend\app.py --server.port 8501
