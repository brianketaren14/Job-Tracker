# ⚡ AI Job Tracker

> Agentic AI system that automatically scrapes, analyses, and displays
> Data Science / AI / ML job listings using **CrewAI + Groq + Flask + Supabase**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     APScheduler (24h)                    │
└──────────────────────────┬──────────────────────────────┘
                           │ triggers
┌──────────────────────────▼──────────────────────────────┐
│                    CrewAI Pipeline                       │
│                                                          │
│  [SerpApi/RemoteOK]                                      │
│       ↓ raw jobs                                         │
│  Scraper Agent  →  Summarizer Agent  →  Validator Agent  │
│  (clean data)      (skills + summary)   (validate + tag) │
│                                              ↓ JSON      │
└──────────────────────────────────────────────┬──────────┘
                                               │ upsert
                                    ┌──────────▼──────────┐
                                    │  Supabase (Postgres) │
                                    │  jobs, skills, runs  │
                                    └──────────┬──────────┘
                                               │ query
                              ┌────────────────▼─────────┐
                              │       Flask Web App       │
                              │  /          – job list    │
                              │  /job/<id>  – detail      │
                              │  /dashboard – charts      │
                              └──────────────────────────┘
```

---

## Quick Start

### 1. Clone & install

```bash
git clone <your-repo>
cd ai_job_tracker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in all values
```

### 3. Set up Supabase

- Create a project at https://supabase.com
- Open the **SQL Editor** and run `schema.sql`

### 4. Run development server

```bash
python app.py
```

Open http://localhost:5000

### 5. Manually trigger the pipeline (for testing)

```bash
curl -X POST http://localhost:5000/api/trigger \
  -H "Authorization: Bearer YOUR_FLASK_SECRET_KEY"
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `GROQ_API_KEY` | Groq API key | ✅ |
| `GROQ_MODEL` | Model name (default: llama3-70b-8192) | – |
| `SUPABASE_URL` | Your Supabase project URL | ✅ |
| `SUPABASE_KEY` | Supabase anon or service_role key | ✅ |
| `SERPAPI_KEY` | SerpApi key for Google Jobs | ✅ |
| `FLASK_SECRET_KEY` | Flask secret + API trigger auth | ✅ |
| `FLASK_ENV` | development / production | – |
| `JOB_QUERIES` | Comma-separated search queries | – |
| `JOB_LOCATION` | Job search location | – |
| `JOB_MAX_RESULTS` | Max results per query | – |
| `JOB_INTERVAL_HOURS` | Scheduler interval in hours | – |

---

## Production Deployment

```bash
# With Docker
docker build -t ai-job-tracker .
docker run -p 5000:5000 --env-file .env ai-job-tracker

# Or directly with Gunicorn
gunicorn app:app -c gunicorn.conf.py
```

> **Note:** Keep `workers = 1` in `gunicorn.conf.py`.  
> APScheduler must run in a single process to avoid duplicate pipeline runs.

---

## Project Structure

```
ai_job_tracker/
├── app.py                  # Flask app + routes
├── scheduler.py            # APScheduler + pipeline entry point
├── schema.sql              # Supabase DDL
├── requirements.txt
├── gunicorn.conf.py
├── Dockerfile
├── .env.example
├── agents/
│   ├── agents.py           # CrewAI Agent definitions (Groq LLM)
│   ├── tasks.py            # CrewAI Task definitions + prompts
│   └── crew.py             # Crew assembly + output parsing
├── utils/
│   ├── db.py               # Supabase query helpers
│   └── scraper.py          # SerpApi + RemoteOK fetchers
├── templates/
│   ├── base.html
│   ├── jobs.html
│   ├── job_detail.html
│   └── dashboard.html
└── static/
    └── css/
        └── main.css
```
