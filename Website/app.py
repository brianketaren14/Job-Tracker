import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request
from supabase import Client, create_client
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

load_dotenv()

app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────────
# Scraping state (in-memory, per-process)
# ─────────────────────────────────────────────
scrape_status = {
    "running": False,
    "last_run": None,
    "last_run_status": None,   # "success" | "error"
    "last_run_message": "",
    "history": [],             # list of {time, status, message}
}
scrape_lock = threading.Lock()


def run_graph():
    """Jalankan LangGraph pipeline di thread terpisah."""
    from graph import call_graph   # import lazy supaya Flask tidak crash kalau deps belum siap
    wib = ZoneInfo("Asia/Jakarta")
    start_time = datetime.now(wib)

    with scrape_lock:
        scrape_status["running"] = True

    try:
        call_graph()
        status, message = "success", "Scraping selesai tanpa error."
    except Exception as e:
        status, message = "error", str(e)
    finally:
        end_time = datetime.now(wib)
        entry = {
            "time": end_time.strftime("%Y-%m-%d %H:%M:%S WIB"),
            "status": status,
            "message": message,
            "duration_sec": round((end_time - start_time).total_seconds()),
        }
        with scrape_lock:
            scrape_status["running"] = False
            scrape_status["last_run"] = entry["time"]
            scrape_status["last_run_status"] = status
            scrape_status["last_run_message"] = message
            scrape_status["history"].insert(0, entry)
            scrape_status["history"] = scrape_status["history"][:20]   # simpan 20 terakhir


# ─────────────────────────────────────────────
# APScheduler – setiap hari 12:00 WIB
# ─────────────────────────────────────────────
scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
scheduler.add_job(
    run_graph,
    trigger=CronTrigger(hour=0, minute=0, timezone="Asia/Jakarta"),
    id="daily_scrape",
    replace_existing=True,
)
scheduler.start()


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/job/<int:job_id>")
def job_detail(job_id):
    return render_template("detail.html", job_id=job_id)


# ─────────────────────────────────────────────
# API – Jobs (listing + search)
# ─────────────────────────────────────────────

@app.route("/api/jobs")
def api_jobs():
    q = request.args.get("q", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    per_page = int(request.args.get("per_page", 12))
    offset = (page - 1) * per_page

    query = (
        supabase.table("lowongan")
        .select(
            "id_lowongan, title, company_name, location, salary, "
            "schedule_type, posted_date_exact, description_summary, thumbnail, source_link, "
            "lowongan_skill(skill(nama_skill))",
            count="exact",
        )
        .order("posted_date_exact", desc=True)
        .range(offset, offset + per_page - 1)
    )

    if q:
        query = query.or_(
            f"title.ilike.%{q}%,company_name.ilike.%{q}%,location.ilike.%{q}%"
        )

    result = query.execute()

    jobs = []
    for row in result.data:
        skills = []
        for ls in (row.get("lowongan_skill") or []):
            skill_obj = ls.get("skill")
            if skill_obj and skill_obj.get("nama_skill"):
                skills.append(skill_obj["nama_skill"])
        row["skills"] = skills
        row.pop("lowongan_skill", None)
        jobs.append(row)

    return jsonify({
        "jobs": jobs,
        "total": result.count or 0,
        "page": page,
        "per_page": per_page,
    })


# ─────────────────────────────────────────────
# API – Job detail
# ─────────────────────────────────────────────

@app.route("/api/jobs/<int:job_id>")
def api_job_detail(job_id):
    result = (
        supabase.table("lowongan")
        .select(
            "*, lowongan_skill(skill(nama_skill))"
        )
        .eq("id_lowongan", job_id)
        .single()
        .execute()
    )
    if not result.data:
        return jsonify({"error": "Not found"}), 404

    row = result.data
    skills = []
    for ls in (row.get("lowongan_skill") or []):
        skill_obj = ls.get("skill")
        if skill_obj and skill_obj.get("nama_skill"):
            skills.append(skill_obj["nama_skill"])
    row["skills"] = skills
    row.pop("lowongan_skill", None)
    return jsonify(row)


# ─────────────────────────────────────────────
# API – Dashboard analytics
# ─────────────────────────────────────────────

@app.route("/api/analytics/skills")
def api_skill_chart():
    """Top N skill paling banyak muncul di lowongan."""
    limit = int(request.args.get("limit", 20))
    result = (
        supabase.table("lowongan_skill")
        .select("skill(nama_skill)", count="exact")
        .execute()
    )
    from collections import Counter
    counter = Counter()
    for row in result.data:
        name = (row.get("skill") or {}).get("nama_skill")
        if name:
            counter[name] += 1

    top = counter.most_common(limit)
    return jsonify({"labels": [x[0] for x in top], "values": [x[1] for x in top]})


@app.route("/api/analytics/jobs-per-day")
def api_jobs_per_day():
    """Jumlah lowongan yang diposting per hari (30 hari terakhir)."""
    result = (
        supabase.table("lowongan")
        .select("posted_date_exact")
        .not_.is_("posted_date_exact", "null")
        .order("posted_date_exact", desc=True)
        .execute()
    )
    from collections import Counter
    counter = Counter()
    for row in result.data:
        raw = row.get("posted_date_exact", "")
        if raw:
            day = str(raw)[:10]
            counter[day] += 1

    sorted_items = sorted(counter.items())[-30:]
    return jsonify({"labels": [x[0] for x in sorted_items], "values": [x[1] for x in sorted_items]})


@app.route("/api/analytics/schedule-type")
def api_schedule_type():
    result = (
        supabase.table("lowongan")
        .select("schedule_type")
        .execute()
    )
    from collections import Counter
    counter = Counter()
    for row in result.data:
        val = row.get("schedule_type") or "Not specified"
        counter[val] += 1
    items = counter.most_common()
    return jsonify({"labels": [x[0] for x in items], "values": [x[1] for x in items]})


@app.route("/api/analytics/summary")
def api_analytics_summary():
    total_jobs = supabase.table("lowongan").select("id_lowongan", count="exact").execute()
    total_skills = supabase.table("skill").select("id_skill", count="exact").execute()
    latest = (
        supabase.table("lowongan")
        .select("posted_date_exact")
        .not_.is_("posted_date_exact", "null")
        .order("posted_date_exact", desc=True)
        .limit(1)
        .execute()
    )
    latest_date = ""
    if latest.data:
        latest_date = str(latest.data[0]["posted_date_exact"])[:10]

    return jsonify({
        "total_jobs": total_jobs.count or 0,
        "total_skills": total_skills.count or 0,
        "latest_posting": latest_date,
    })


# ─────────────────────────────────────────────
# API – Scrape trigger & status
# ─────────────────────────────────────────────

@app.route("/api/scrape/trigger", methods=["POST"])
def api_scrape_trigger():
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if password != ADMIN_PASSWORD:
        return jsonify({"error": "Password salah."}), 403

    with scrape_lock:
        if scrape_status["running"]:
            return jsonify({"error": "Scraping sedang berjalan."}), 409

    thread = threading.Thread(target=run_graph, daemon=True)
    thread.start()
    return jsonify({"message": "Scraping dimulai."})


@app.route("/api/scrape/status")
def api_scrape_status():
    with scrape_lock:
        return jsonify(dict(scrape_status))


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
