@echo off
cd /d "C:\Users\banan\.gemini\antigravity\scratch\renfaire-ticket-scout"
start "" /b ".venv\Scripts\python.exe" -u dashboard_server.py
start "" /b "cloudflared.exe" tunnel --url http://127.0.0.1:8765 --metrics 127.0.0.1:20241
start "" /b ".venv\Scripts\python.exe" -u renfaire_ticket_scout.py --browser --headless --interval 300
