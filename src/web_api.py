import os
import sys
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from manager_agent import ManagerAgent

app = FastAPI(title="AutoFarm-30 Control Hub", version="2.0.0")
DB_PATH = "autofarm.db"

class TaskPayload(BaseModel):
    device_id: int = 1
    post_link: str
    action_type: str = "COMMENT"
    comment_text: str = "Harika paylasim! 🚀"

@app.get("/api/status")
def get_status():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, serial, local_ip, proxy, status FROM devices")
    devices = [{"id": r[0], "name": r[1], "serial": r[2], "local_ip": r[3], "proxy": r[4], "status": r[5]} for r in c.fetchall()]
    c.execute("SELECT COUNT(*) FROM targeted_tasks WHERE status = 'PENDING'")
    pending = c.fetchone()[0]
    conn.close()
    return {"total_devices": len(devices), "pending_tasks": pending, "devices": devices}

@app.get("/api/report")
def get_report():
    return {"report": ManagerAgent.get_fleet_report()}

@app.post("/api/tasks")
def create_task(task: TaskPayload):
    if not task.post_link.strip():
        raise HTTPException(status_code=400, detail="Post linki bos olamaz")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO targeted_tasks (device_id, post_link, action_type, comment_text, status) VALUES (?, ?, ?, ?, 'PENDING')",
              (task.device_id, task.post_link, task.action_type, task.comment_text))
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    return {"status": "success", "task_id": task_id, "message": "Gorev kuyruga eklendi!"}

@app.get("/", response_class=HTMLResponse)
def dashboard_view():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>AutoFarm-30 Web Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { background-color: #11111b; color: #cdd6f4; font-family: -apple-system, sans-serif; padding: 20px; }
        .card { background: #1e1e2e; border: 1px solid #313244; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
        h1 { color: #89b4fa; font-size: 20px; }
        input, select, button { padding: 10px; margin: 5px 0; border-radius: 6px; border: 1px solid #45475a; }
        input { background: #181825; color: #fff; width: 100%; box-sizing: border-box; }
        button { background: #a6e3a1; color: #11111b; font-weight: bold; width: 100%; cursor: pointer; border: none; }
        button:hover { background: #94e2d5; }
        pre { background: #181825; padding: 15px; border-radius: 6px; color: #a6e3a1; overflow-x: auto; font-size: 12px; }
    </style>
</head>
<body>
    <h1>🚀 AutoFarm-30 Uzaktan Web Kontrol Paneli</h1>
    <div class="card">
        <h3>🎯 Yeni Hedefli Gorev Ata</h3>
        <input id="link" placeholder="Facebook Gonderi Linki (https://...)" />
        <input id="comment" placeholder="Ozel Yorum Metni..." />
        <button onclick="sendTask()">Gorevi Baslat</button>
        <p id="result" style="color: #f9e2af;"></p>
    </div>
    <div class="card">
        <h3>📊 Yonetici Ajan Anlik Raporu</h3>
        <pre id="report">Yukleniyor...</pre>
    </div>
    <script>
        async function loadReport() {
            const res = await fetch('/api/report');
            const data = await res.json();
            document.getElementById('report').innerText = data.report;
        }
        async function sendTask() {
            const link = document.getElementById('link').value;
            const comment = document.getElementById('comment').value;
            const res = await fetch('/api/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ post_link: link, comment_text: comment })
            });
            const data = await res.json();
            document.getElementById('result').innerText = data.message || 'Gorev iletildi!';
            document.getElementById('link').value = '';
            document.getElementById('comment').value = '';
            loadReport();
        }
        loadReport();
        setInterval(loadReport, 10000);
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
