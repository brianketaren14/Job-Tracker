# scheduler.py
# Background job scheduler – runs the scrape+AI pipeline once a day at WIB time

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from utils.scraper import fetch_jobs_serpapi, fetch_jobs_remoteok
from utils.db import upsert_job, insert_skills, start_run, finish_run, get_existing_urls
from agents.crew import run_crew

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

# ── Config ───────────────────────────────────────────────────────

QUERIES         = [q.strip() for q in os.getenv("JOB_QUERIES", "Data Scientist,AI Engineer,ML Engineer").split(",")]
LOCATION        = os.getenv("JOB_LOCATION", "Indonesia")
WIB             = ZoneInfo("Asia/Jakarta")           # UTC+7
SCHEDULE_HOUR   = int(os.getenv("SCHEDULE_HOUR",   "8"))  # default: 08:00 WIB
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "0"))


# ── Core pipeline function ────────────────────────────────────────

def run_pipeline() -> dict:
    """
    Full pipeline:
      1. Scrape raw jobs dari SerpApi (+ RemoteOK fallback)
      2. Feed ke CrewAI untuk cleaning, enrichment, validation
      3. Simpan ke Supabase
    """
    run_id = start_run()
    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
    logger.info("=== Scrape run started [%s] at %s ===", run_id, now_wib)

    jobs_added   = 0
    jobs_skipped = 0
    error_msg    = None

    try:
        # ── Step 1: Scrape ───────────────────────────────────────
        raw_jobs: list[dict] = []
        existing_urls = get_existing_urls()
        logger.info("Ditemukan %d URL pekerjaan di database.", len(existing_urls))
        
        for query in QUERIES:
            serpapi_jobs = fetch_jobs_serpapi(query, LOCATION)
            raw_jobs.extend(serpapi_jobs)

        # Fallback: RemoteOK
        remoteok_jobs = fetch_jobs_remoteok(QUERIES)
        raw_jobs.extend(remoteok_jobs)

        # Deduplikasi by URL sebelum masuk CrewAI DAN pengecekan dengan Database
        seen_urls: set[str] = set()
        unique_raw: list[dict] = []
        
        for job in raw_jobs:
            url = job.get("url", "")
            
            # Cek 3 hal: 
            # 1. URL tidak kosong
            # 2. URL belum diproses di iterasi ini (seen_urls)
            # 3. URL belum ada di Supabase (existing_urls)
            if url and (url not in seen_urls) and (url not in existing_urls):
                seen_urls.add(url)
                unique_raw.append(job)
            else:
                # Menambah hitungan skip jika URL kosong atau sudah ada
                jobs_skipped += 1

        logger.info("Total unique raw jobs baru untuk CrewAI: %d", len(unique_raw))

        if not unique_raw:
            logger.warning("Tidak ada job baru yang dikumpulkan.")
            finish_run(run_id, 0, jobs_skipped, "No new raw jobs collected")
            return {"added": 0, "skipped": jobs_skipped, "error": "No new raw jobs collected"}

        # ── Step 2: CrewAI pipeline ──────────────────────────────
        processed_jobs = run_crew(unique_raw)

        # ── Step 3: Simpan ke Supabase ───────────────────────────
        for job in processed_jobs:
            if not job.get("url"):
                jobs_skipped += 1
                continue

            db_row = {
                "title":           job.get("title"),
                "company":         job.get("company"),
                "location":        job.get("location"),
                "salary":          job.get("salary"),
                "url":             job["url"],
                "description_raw": job.get("description_raw"),
                "summary":         job.get("summary"),
                "is_valid":        job.get("is_valid", True),
                "domain_tags":     job.get("domain_tags", []),
            }

            saved = upsert_job(db_row)

            if saved:
                job_id = saved["id"]
                skills = job.get("skills", [])
                if skills:
                    insert_skills(job_id, skills)
                jobs_added += 1
                
                # Masukkan ke existing_urls agar aman jika ada pemrosesan berulang (opsional)
                existing_urls.add(job["url"])
            else:
                jobs_skipped += 1

        logger.info("Run selesai – ditambahkan: %d, dilewati: %d", jobs_added, jobs_skipped)

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Pipeline gagal: %s", exc)

    finally:
        finish_run(run_id, jobs_added, jobs_skipped, error_msg)

    return {
        "added":   jobs_added,
        "skipped": jobs_skipped,
        "error":   error_msg,
        "run_id":  run_id,
    }


# ── Scheduler lifecycle ───────────────────────────────────────────

def start_scheduler():
    """Inisialisasi dan jalankan APScheduler dengan timezone WIB."""
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("Scheduler sudah berjalan – skip init.")
        return

    # BackgroundScheduler dengan timezone WIB
    _scheduler = BackgroundScheduler(timezone=WIB, daemon=True)

    # CronTrigger: jalankan setiap hari pada SCHEDULE_HOUR:SCHEDULE_MINUTE WIB
    trigger = CronTrigger(
        hour=SCHEDULE_HOUR,
        minute=SCHEDULE_MINUTE,
        timezone=WIB,
    )

    _scheduler.add_job(
        func=run_pipeline,
        trigger=trigger,
        id="job_scrape_pipeline",
        name="AI Job Scrape & Enrich (WIB)",
        replace_existing=True,
        misfire_grace_time=3600,  # toleransi 1 jam jika server sempat mati
    )

    _scheduler.start()

    next_run = _scheduler.get_job("job_scrape_pipeline").next_run_time
    logger.info(
        "Scheduler aktif – pipeline berjalan setiap hari pukul %02d:%02d WIB. "
        "Jadwal berikutnya: %s",
        SCHEDULE_HOUR,
        SCHEDULE_MINUTE,
        next_run.strftime("%Y-%m-%d %H:%M:%S %Z"),
    )


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler dihentikan.")


def get_next_run() -> datetime | None:
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("job_scrape_pipeline")
        return job.next_run_time if job else None
    return None