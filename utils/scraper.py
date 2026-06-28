# utils/scraper.py
# Raw job data fetching via SerpApi (Google Jobs endpoint)
# Falls back to a lightweight BeautifulSoup scraper if needed.

import os
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
MAX_RESULTS = int(os.getenv("JOB_MAX_RESULTS", "20"))


def _parse_serpapi_date(item: dict) -> Optional[str]:
    """
    Ekstrak tanggal publikasi dari hasil SerpApi.
    SerpApi menyediakan detected_extensions.posted_at (e.g. "3 days ago")
    dan kadang job_highlights atau via_date.
    Mengembalikan string ISO-8601 (UTC) atau None.
    """
    extensions = item.get("detected_extensions", {})

    # Coba ambil nilai relatif seperti "3 days ago", "1 week ago"
    posted_at_raw = extensions.get("posted_at", "") or ""

    now = datetime.now(timezone.utc)

    if posted_at_raw:
        text = posted_at_raw.lower().strip()
        try:
            if "just now" in text or "today" in text:
                return now.isoformat()
            elif "hour" in text:
                hours = int("".join(filter(str.isdigit, text)) or "1")
                return (now - timedelta(hours=hours)).isoformat()
            elif "day" in text:
                days = int("".join(filter(str.isdigit, text)) or "1")
                return (now - timedelta(days=days)).isoformat()
            elif "week" in text:
                weeks = int("".join(filter(str.isdigit, text)) or "1")
                return (now - timedelta(weeks=weeks)).isoformat()
            elif "month" in text:
                months = int("".join(filter(str.isdigit, text)) or "1")
                return (now - timedelta(days=months * 30)).isoformat()
        except (ValueError, TypeError):
            pass

    # Coba ambil tanggal absolut dari schedule_type / extensions
    for key in ("date_posted", "publish_date", "date"):
        val = extensions.get(key, "")
        if val:
            try:
                return datetime.fromisoformat(val).isoformat()
            except (ValueError, TypeError):
                pass

    return None


def fetch_jobs_serpapi(query: str, location: str = "Indonesia") -> list[dict]:
    """
    Fetch raw job listings from Google Jobs via SerpApi.

    Returns a list of raw job dicts with keys:
        title, company, location, salary, url, description_raw, published_at
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set – skipping SerpApi fetch.")
        return []

    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "google_domain": "google.co.id",
        "hl": "id",
        "gl": "id",
        "api_key": SERPAPI_KEY,
    }

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("SerpApi request failed: %s", e)
        return []

    jobs = []
    for item in data.get("jobs_results", []):
        extensions = item.get("detected_extensions", {})
        salary = extensions.get("salary", None)

        url = _extract_url(item)
        if not url:
            continue  # skip if no URL — can't deduplicate

        jobs.append({
            "title":           item.get("title", "").strip(),
            "company":         item.get("company_name", "").strip(),
            "location":        item.get("location", "").strip(),
            "salary":          salary,
            "url":             url,
            "description_raw": item.get("description", "").strip(),
            "published_at":    _parse_serpapi_date(item),
            "contract_type":   _parse_serpapi_contract(item),  # tipe kontrak
        })

    logger.info("SerpApi returned %d jobs for query '%s'", len(jobs), query)
    return jobs


def _extract_url(item: dict) -> Optional[str]:
    """Best-effort URL extraction from a SerpApi job result."""
    for opt in item.get("apply_options", []):
        link = opt.get("link", "")
        if link.startswith("http"):
            return link
    share = item.get("share_link", "")
    if share.startswith("http"):
        return share
    return None


# ──────────────────────────────────────────
# Lightweight fallback scraper (no API key needed)
# Scrapes RemoteOK public JSON feed – good for testing
# ──────────────────────────────────────────

def fetch_jobs_remoteok(keywords: list[str]) -> list[dict]:
    """
    Pull from RemoteOK's public JSON API as a free fallback.
    Filters results by keyword match in title or tags.
    """
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (AI-Job-Tracker/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("RemoteOK fetch failed: %s", e)
        return []

    kw_lower = [k.lower() for k in keywords]
    jobs = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = item.get("position", "")
        tags  = " ".join(item.get("tags", []))
        combined = (title + " " + tags).lower()

        if not any(k in combined for k in kw_lower):
            continue

        job_url = item.get("url", "")
        if not job_url:
            continue

        # RemoteOK menyediakan unix timestamp di field "date" / "epoch"
        published_at = _parse_remoteok_date(item)

        jobs.append({
            "title":           title.strip(),
            "company":         item.get("company", "").strip(),
            "location":        item.get("location", "Remote"),
            "salary":          _format_salary(item),
            "url":             job_url,
            "description_raw": item.get("description", "").strip()[:3000],
            "published_at":    published_at,
            "contract_type":   _parse_remoteok_contract(item),  # tipe kontrak
        })

    logger.info("RemoteOK returned %d matching jobs", len(jobs))
    return jobs


def _parse_remoteok_date(item: dict) -> Optional[str]:
    """Konversi unix timestamp RemoteOK ke ISO-8601."""
    epoch = item.get("epoch") or item.get("date")
    if epoch:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            pass
    return None


# Mapping kata kunci ke nilai standar tipe kontrak
_CONTRACT_ALIASES: dict[str, str] = {
    # Full-time
    "full-time": "Full-time", "full time": "Full-time", "fulltime": "Full-time",
    "permanent": "Full-time",
    # Part-time
    "part-time": "Part-time", "part time": "Part-time", "parttime": "Part-time",
    # Contract
    "contract": "Contract", "kontrak": "Contract", "fixed-term": "Contract",
    "fixed term": "Contract",
    # Freelance
    "freelance": "Freelance", "freelancer": "Freelance", "independent": "Freelance",
    # Internship
    "internship": "Internship", "intern": "Internship", "magang": "Internship",
    "graduate": "Internship",
    # Remote (bisa dikombinasikan, tapi beberapa sumber menaruhnya di sini)
    "remote": "Remote",
    # Temporary
    "temporary": "Temporary", "temp": "Temporary", "sementara": "Temporary",
}


def _normalise_contract_type(raw: str) -> Optional[str]:
    """
    Normalisasi string tipe kontrak ke nilai standar.
    Contoh: "FULL_TIME" → "Full-time", "internship" → "Internship".
    Mengembalikan None jika tidak dikenali.
    """
    if not raw:
        return None
    # SerpApi kadang mengirim format SCREAMING_SNAKE_CASE, e.g. "FULL_TIME"
    cleaned = raw.replace("_", " ").replace("-", " ").lower().strip()
    # Cek exact match dulu
    if cleaned in _CONTRACT_ALIASES:
        return _CONTRACT_ALIASES[cleaned]
    # Cek substring match (urutan panjang → pendek agar "full time" tidak dipotong jadi "full")
    for key in sorted(_CONTRACT_ALIASES, key=len, reverse=True):
        if key in cleaned:
            return _CONTRACT_ALIASES[key]
    # Kembalikan raw yang di-title-case sebagai fallback daripada None
    return raw.strip().title()


def _parse_serpapi_contract(item: dict) -> Optional[str]:
    """
    Ekstrak tipe kontrak dari hasil SerpApi.
    SerpApi menaruh nilai ini di detected_extensions.schedule_type,
    contoh: "Full-time", "Part-time", "Contractor", "FULL_TIME".
    """
    extensions = item.get("detected_extensions", {})
    raw = extensions.get("schedule_type") or extensions.get("work_from_home")
    if isinstance(raw, bool):
        # work_from_home = True bukan tipe kontrak, abaikan
        return None
    return _normalise_contract_type(raw) if raw else None


def _parse_remoteok_contract(item: dict) -> Optional[str]:
    """
    Ekstrak tipe kontrak dari hasil RemoteOK.
    RemoteOK menyediakan field 'job_type' (e.g. "full_time", "contract")
    dan kadang di dalam list 'tags'.
    """
    # Coba field eksplisit terlebih dahulu
    raw = item.get("job_type") or item.get("employment_type")
    if raw:
        return _normalise_contract_type(str(raw))

    # Fallback: cari kata kunci tipe kontrak di dalam tags.
    # Hanya return jika tag cocok dengan alias yang dikenal — hindari
    # mengembalikan nama teknologi (e.g. "Python") sebagai tipe kontrak.
    known_values = set(_CONTRACT_ALIASES.values())
    for tag in item.get("tags", []):
        cleaned = str(tag).replace("_", " ").replace("-", " ").lower().strip()
        for key in sorted(_CONTRACT_ALIASES, key=len, reverse=True):
            if key in cleaned:
                return _CONTRACT_ALIASES[key]

    return None


def _format_salary(item: dict) -> Optional[str]:
    lo = item.get("salary_min")
    hi = item.get("salary_max")
    if lo and hi:
        return f"${lo:,} – ${hi:,}"
    if lo:
        return f"${lo:,}+"
    return None