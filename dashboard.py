import os
from pathlib import Path
from typing import Dict, List

from flask import Flask, redirect, render_template_string, request, url_for
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
RATINGS_FILE = DATA_DIR / "ratings.json"
VACATIONS_FILE = DATA_DIR / "vacations.json"
ATTENDANCE_FILE = DATA_DIR / "attendance.json"
STATS_FILE = DATA_DIR / "stats.json"
ACTIONS_FILE = DATA_DIR / "dashboard_actions.json"

DASHBOARD_TOKEN = os.getenv("DASHBOARD_TOKEN", "admin123")

app = Flask(__name__)


def load_json(path: Path, default):
    if not path.exists():
        path.write_text("{}" if isinstance(default, dict) else "[]", encoding="utf-8")
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    import json

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_action(action_type: str, payload: Dict):
    actions: List[Dict] = load_json(ACTIONS_FILE, [])
    import time, random

    actions.append(
        {
            "id": int(time.time() * 1000) + random.randint(1, 999),
            "type": action_type,
            "payload": payload,
            "status": "pending",
        }
    )
    save_json(ACTIONS_FILE, actions)


def authorized(req) -> bool:
    token = req.args.get("token") or req.form.get("token") or req.headers.get("X-Dashboard-Token")
    return token == DASHBOARD_TOKEN


HTML = """
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8"/>
  <title>لوحة تحكم البوت</title>
  <style>
    body{font-family:Arial;background:#10131a;color:#eee;margin:20px}
    .card{background:#171c26;padding:14px;border-radius:12px;margin-bottom:14px}
    input,select,button{padding:8px;border-radius:8px;border:1px solid #333;background:#0f1320;color:#fff}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    table{width:100%;border-collapse:collapse}
    td,th{padding:8px;border-bottom:1px solid #2b3140}
  </style>
</head>
<body>
  <h1>🎛️ لوحة تحكم Discord Staff Bot</h1>

  <div class="grid">
    <div class="card">
      <h3>إحصائيات</h3>
      <p>Admin actions: {{stats.get('admin_actions',0)}}</p>
      <p>Say count: {{stats.get('say_count',0)}}</p>
      <p>Ratings users: {{ratings|length}}</p>
      <p>Vacations active: {{vacations|length}}</p>
      <p>Attendance users: {{attendance|length}}</p>
    </div>

    <div class="card">
      <h3>تنفيذ أمر إداري</h3>
      <form method="post" action="/action">
        <input type="hidden" name="token" value="{{token}}"/>
        <select name="action_type">
          <option value="hire">توظيف</option>
          <option value="promote">ترقية</option>
          <option value="demote">تنزيل</option>
          <option value="promote_tier">ترقية-فئة</option>
          <option value="fire">فصل</option>
          <option value="vacation">اجازة</option>
        </select>
        <input name="member_id" placeholder="Member ID" required/>
        <input name="steps" placeholder="steps (for promote/demote)"/>
        <input name="hours" placeholder="hours (for vacation)"/>
        <button type="submit">إرسال للبوت</button>
      </form>
      <small>الأوامر تُحفظ في queue وينفذها البوت تلقائياً.</small>
    </div>
  </div>

  <div class="card">
    <h3>آخر عمليات Dashboard Queue</h3>
    <table>
      <tr><th>ID</th><th>Type</th><th>Status</th><th>Payload</th></tr>
      {% for a in actions %}
      <tr>
        <td>{{a.get('id')}}</td>
        <td>{{a.get('type')}}</td>
        <td>{{a.get('status')}}</td>
        <td>{{a.get('payload')}}</td>
      </tr>
      {% endfor %}
    </table>
  </div>

  <div class="card">
    <h3>روابط</h3>
    <p>شغّل: <code>python dashboard.py</code> على Termux</p>
    <p>افتح: <code>http://127.0.0.1:8080/?token={{token}}</code></p>
  </div>
</body>
</html>
"""


@app.get("/")
def home():
    if not authorized(request):
        return "Unauthorized. add ?token=YOUR_DASHBOARD_TOKEN", 401

    stats = load_json(STATS_FILE, {})
    ratings = load_json(RATINGS_FILE, {})
    vacations = load_json(VACATIONS_FILE, {})
    attendance = load_json(ATTENDANCE_FILE, {})
    actions = load_json(ACTIONS_FILE, [])[-20:][::-1]

    return render_template_string(
        HTML,
        stats=stats,
        ratings=ratings,
        vacations=vacations,
        attendance=attendance,
        actions=actions,
        token=DASHBOARD_TOKEN,
    )


@app.post("/action")
def action():
    if not authorized(request):
        return "Unauthorized", 401

    action_type = request.form.get("action_type", "").strip()
    member_id = request.form.get("member_id", "").strip()
    steps = request.form.get("steps", "").strip()
    hours = request.form.get("hours", "").strip()

    payload: Dict = {"member_id": member_id}
    if steps.isdigit():
        payload["steps"] = int(steps)
    if hours.isdigit():
        payload["hours"] = int(hours)

    add_action(action_type, payload)
    return redirect(url_for("home", token=DASHBOARD_TOKEN))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("DASHBOARD_PORT", "8080")), debug=False)
