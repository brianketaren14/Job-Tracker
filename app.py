# app.py
# Flask application — entry point for the web server
#
# Windows asyncio fix MUST be the very first thing that runs,
# before any import that might touch asyncio (crewai, supabase, etc.)

import sys
import asyncio

if sys.platform == "win32":
    # CrewAI / httpx use asyncio internally. The default ProactorEventLoop
    # on Windows doesn't support all the operations they need.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Now safe to import everything else ─────────────────────────
import os
import logging
from dotenv import load_dotenv

load_dotenv()  # load .env before os.environ is read downstream

from flask import Flask, render_template, request, jsonify, abort
from scheduler import start_scheduler, stop_scheduler, get_next_run, run_pipeline
from utils.db import fetch_jobs, fetch_job_by_id, fetch_skill_frequency, fetch_recent_runs

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App setup ─────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")


# ══════════════════════════════════════════════════════════════
# Web Routes
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Job listing page with pagination and search."""
    page   = max(1, request.args.get("page", 1, type=int))
    search = request.args.get("q", "").strip()
    data   = fetch_jobs(page=page, per_page=20, search=search)
    return render_template(
        "jobs.html",
        jobs=data["jobs"],
        page=data["page"],
        pages=data["pages"],
        total=data["total"],
        search=search,
    )


@app.route("/job/<job_id>")
def job_detail(job_id: str):
    job = fetch_job_by_id(job_id)
    if not job:
        abort(404)
    return render_template("job_detail.html", job=job)


@app.route("/dashboard")
def dashboard():
    skills      = fetch_skill_frequency(limit=20)
    recent_runs = fetch_recent_runs(limit=5)
    next_run    = get_next_run()
    return render_template(
        "dashboard.html",
        skills=skills,
        recent_runs=recent_runs,
        next_run=next_run,
    )


# ══════════════════════════════════════════════════════════════
# API Routes (JSON)
# ══════════════════════════════════════════════════════════════

@app.route("/api/jobs")
def api_jobs():
    page   = max(1, request.args.get("page", 1, type=int))
    search = request.args.get("q", "").strip()
    return jsonify(fetch_jobs(page=page, per_page=20, search=search))


@app.route("/api/skills")
def api_skills():
    limit = min(50, request.args.get("limit", 20, type=int))
    return jsonify(fetch_skill_frequency(limit=limit))


@app.route("/api/trigger", methods=["POST"])
def api_trigger():
    """Manually trigger a scrape run. Protected by Bearer token."""
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {app.secret_key}":
        return jsonify({"error": "Unauthorized"}), 401

    import threading
    threading.Thread(target=run_pipeline, daemon=True).start()
    return jsonify({"status": "Pipeline triggered in background."})


@app.route("/api/status")
def api_status():
    next_run = get_next_run()
    return jsonify({
        "scheduler_running": next_run is not None,
        "next_run": next_run.isoformat() if next_run else None,
        "recent_runs": fetch_recent_runs(limit=3),
    })


# ══════════════════════════════════════════════════════════════
# App lifecycle
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    start_scheduler()
    try:
        app.run(
            host="0.0.0.0",
            port=int(os.getenv("PORT", 5000)),
            debug=(os.getenv("FLASK_ENV") == "development"),
            use_reloader=False,   # MUST be False — scheduler must start only once
        )
    finally:
        stop_scheduler()
