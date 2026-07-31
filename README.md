# Job Tracker

An automated job-listing pipeline that scrapes job postings (via SerpApi's Google Jobs engine), enriches them with LLM-powered extraction, deduplicates against an existing database, and serves the results through a Flask dashboard. The extraction/enrichment pipeline is orchestrated as a **LangGraph** state machine, built with **LangChain** agents, and traced end-to-end with **LangSmith**.

## Website
link website : https://web-production-e5c88.up.railway.app/

## Features

- **Automated scraping** of job postings from Google Jobs (via SerpApi) across multiple search queries
- **LLM-based structured extraction** of job fields (title, company, location, salary, schedule type, description, etc.)
- **Skill extraction** — normalizes and extracts up to 10 relevant hard/soft skills per job posting
- **Description summarization** and automatic conversion of raw descriptions to HTML
- **Deduplication** against existing records (by source link and by title + company) to avoid reprocessing/re-inserting the same job
- **URL validity check** for each scraped source link
- **Supabase** as the backing database (`lowongan`, `skill`, `lowongan_skill`, `scrape_lock` tables)
- **Distributed scrape lock** (via Supabase) to prevent concurrent/duplicate scraping runs across processes or containers
- **Daily scheduled scraping** at 00:00 WIB using APScheduler, plus a manual trigger endpoint
- **Dashboard & API** (Flask) for browsing jobs, viewing job details, and analytics (top skills, jobs per day, schedule type breakdown)
- **Full observability** of the LangGraph pipeline via LangSmith tracing

## Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) |
| LLM framework / agents | [LangChain](https://github.com/langchain-ai/langchain) (`create_agent`) |
| Observability / tracing | [LangSmith](https://smith.langchain.com/) |
| LLM provider | Groq (`ChatGroq`, `llama-4-scout-17b-16e-instruct`) |
| Job scraping | [SerpApi](https://serpapi.com/) (Google Jobs engine) |
| Database | [Supabase](https://supabase.com/) (PostgreSQL) |
| Web backend | Flask |
| Scheduling | APScheduler (cron trigger, WIB timezone) |

## Architecture

The core pipeline lives in `graph.py` and is built as a `StateGraph` (`JobTracker` state) with the following flow:

1. **`scraping_node`** — scrapes raw job postings from SerpApi across all configured queries, deduplicating in-memory by `job_id`
2. **`fetch_existing_jobs_node`** — batch-fetches existing `source_link`s and `(title, company_name)` pairs from Supabase once, to avoid per-job DB round-trips
3. **`check_duplicate_and_extracting_node`** — pre-checks the raw source link against known existing links; if new, invokes the extraction agent to structure the raw scraped data (`JobInformation`)
4. **`check_job_vacancy_exists_node`** *(conditional)* — re-checks existence using the agent-normalized title/company against the batch-fetched set
5. **`extract_skills_node`** — extracts up to 10 normalized skills (8 hard skills + 2 soft skills) from the job description
6. **`summarize_description_node`** — generates a short 2–4 sentence summary of the job description
7. **`description_to_html_node`** — converts the plain-text description into structured HTML (headings + bullet lists)
8. **`delete_unnecessary_field_node`** — strips intermediate/unneeded fields before persistence
9. **`insert_job_node`** — upserts the job and its associated skills into Supabase (`lowongan`, `skill`, `lowongan_skill`)
10. **`counter_check`** *(conditional loop)* — advances to the next scraped job or finishes the run

Every invocation of the graph (`call_graph`) is wrapped with `@traceable` so the entire run — including every LLM agent call inside each node — is visible in LangSmith.
<p align="center">
  <img width="564" height="1222" alt="image" src="https://github.com/user-attachments/assets/0a95ac85-1414-490c-8696-f7c792d4749f" />
</p>
