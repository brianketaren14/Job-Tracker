# utils/db.py
# Supabase connection and query helpers

import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_db() -> Client:
    """Return a singleton Supabase client."""
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


# ──────────────────────────────────────────
# Jobs
# ──────────────────────────────────────────

def upsert_job(job: dict) -> dict | None:
    """
    Insert a job or update it if the URL already exists.
    Returns the inserted/updated row, or None on error.
    """
    db = get_db()
    try:
        res = (
            db.table("jobs")
            .upsert(job, on_conflict="url")
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("upsert_job failed: %s", e)
        return None


def fetch_jobs(page: int = 1, per_page: int = 20, search: str = "") -> dict:
    """
    Paginated job listing untuk web UI.
    Diurutkan berdasarkan published_at (terbaru lebih dulu).
    Job tanpa published_at muncul di akhir (NULLS LAST).
    """
    db = get_db()
    offset = (page - 1) * per_page

    query = (
        db.table("jobs")
        .select("*", count="exact")
        .eq("is_valid", True)
        .order("published_at", desc=True, nullsfirst=False)  # terbaru dulu, null di akhir
        .order("created_at", desc=True)                      # tiebreaker: waktu scrape
        .range(offset, offset + per_page - 1)
    )

    if search:
        query = query.ilike("title", f"%{search}%")

    res = query.execute()
    return {
        "jobs": res.data,
        "total": res.count,
        "page": page,
        "per_page": per_page,
        "pages": max(1, -(-res.count // per_page)),  # ceiling division
    }


def fetch_job_by_id(job_id: str) -> dict | None:
    db = get_db()
    res = db.table("jobs").select("*").eq("id", job_id).single().execute()
    return res.data


# ──────────────────────────────────────────
# Skills
# ──────────────────────────────────────────

def insert_skills(job_id: str, skills: list[str]) -> None:
    """Bulk-insert extracted skills for a job."""
    db = get_db()
    if not skills:
        return
    rows = [{"job_id": job_id, "skill": s.strip()} for s in skills if s.strip()]
    try:
        db.table("extracted_skills").insert(rows).execute()
    except Exception as e:
        logger.error("insert_skills failed for job %s: %s", job_id, e)


def fetch_skill_frequency(limit: int = 20) -> list[dict]:
    """Return top-N skills with their frequency count."""
    db = get_db()
    res = db.table("skill_frequency").select("skill, frequency").limit(limit).execute()
    return res.data or []


# ──────────────────────────────────────────
# Scrape Run Audit Log
# ──────────────────────────────────────────

def start_run() -> str | None:
    """Create a scrape_run record and return its ID."""
    db = get_db()
    res = db.table("scrape_runs").insert({"status": "running"}).execute()
    return res.data[0]["id"] if res.data else None


def finish_run(run_id: str, jobs_added: int, jobs_skipped: int, error: str = None):
    db = get_db()
    payload = {
        "status": "failed" if error else "success",
        "finished_at": "now()",
        "jobs_added": jobs_added,
        "jobs_skipped": jobs_skipped,
    }
    if error:
        payload["error_msg"] = error
    db.table("scrape_runs").update(payload).eq("id", run_id).execute()


def fetch_recent_runs(limit: int = 10) -> list[dict]:
    db = get_db()
    res = (
        db.table("scrape_runs")
        .select("*")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_existing_urls() -> set[str]:
    """
    Mengambil semua URL dari tabel jobs untuk pengecekan duplikasi.
    Menggunakan paginasi untuk mengatasi limit default Supabase (1000 baris).
    """
    db = get_db()
    existing_urls = set()

    limit = 1000
    offset = 0

    while True:
        try:
            res = (
                db.table("jobs")
                .select("url")
                .range(offset, offset + limit - 1)
                .execute()
            )

            if not res.data:
                break

            for row in res.data:
                if row.get("url"):
                    existing_urls.add(row["url"])

            if len(res.data) < limit:
                break

            offset += limit

        except Exception as e:
            logger.error("Gagal menarik existing URLs dari Supabase: %s", e)
            break

    return existing_urls