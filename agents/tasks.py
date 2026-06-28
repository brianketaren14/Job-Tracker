# agents/tasks.py
# CrewAI Task definitions – each maps to one agent

import json
from crewai import Task
from crewai.agent import Agent


# ─────────────────────────────────────────────────────────────────
# Task 1 – Clean & Standardise
# Input  : raw_jobs (list of dicts from the scraper utility)
# Output : cleaned JSON string passed to Task 2
# ─────────────────────────────────────────────────────────────────

def build_scraper_task(agent: Agent, raw_jobs: list[dict]) -> Task:
    raw_json = json.dumps(raw_jobs, ensure_ascii=False, indent=2)

    description = f"""
You are given the following raw job data collected from various job boards.

<RAW_JOBS>
{raw_json}
</RAW_JOBS>

Your job:
1. Parse every item in the list.
2. Normalise each job into this exact schema:
   {{
     "title":           string,
     "company":         string,
     "location":        string | null,
     "salary":          string | null,
     "url":             string,            ← required; discard jobs without URL
     "description_raw": string,            ← max 2000 characters; truncate if needed
     "published_at":    string | null,
     "contract_type":   string | null
   }}
3. Strip any HTML tags from description_raw.
4. Remove jobs that have no URL or no title.
5. Return ONLY a valid JSON array. No markdown. No explanation.
"""
    return Task(
        description=description,
        agent=agent,
        expected_output=(
            "A valid JSON array of cleaned job objects. "
            "Each object must have: title, company, location, salary, url, "
            "description_raw, published_at, job_type. "
            "No markdown fences. Pure JSON only."
        ),
    )


# ─────────────────────────────────────────────────────────────────
# Task 2 – Enrich with Skills & Summary
# Input  : output of Task 1 (cleaned JSON string)
# Output : enriched JSON string passed to Task 3
# ─────────────────────────────────────────────────────────────────

def build_summarizer_task(agent: Agent, scraper_task: Task) -> Task:
    description = """
You will receive the output of the previous task: a JSON array of cleaned job objects.

For EACH job in the array, add the following fields by analysing description_raw:

1. "skills"         : list[str]  – technical skills, tools, frameworks mentioned
                      (e.g. ["Python", "PyTorch", "LangChain", "Docker", "SQL"])
2. "qualifications" : list[str]  – key qualifications / requirements
                      (e.g. ["3+ years ML experience", "BSc in Computer Science"])
3. "summary"        : str        – 3 to 5 bullet points (start each with "• ")
                      summarising what the role involves

Rules:
- Extract only what is explicitly stated or strongly implied in description_raw.
- Do NOT invent skills or qualifications not present in the text.
- Keep each bullet point under 20 words.
- Keep the skill names canonical (e.g. "PyTorch" not "pytorch", "SQL" not "sql").
- Preserve ALL existing fields including "published_at" — do not remove or alter them.
- Return ONLY the enriched JSON array. No markdown. No commentary.
"""
    return Task(
        description=description,
        agent=agent,
        context=[scraper_task],
        expected_output=(
            "A valid JSON array where every object from the previous task "
            "now also contains: skills (list), qualifications (list), summary (str). "
            "All original fields (including published_at) must be preserved. "
            "No markdown fences. Pure JSON only."
        ),
    )


# ─────────────────────────────────────────────────────────────────
# Task 3 – Validate, Deduplicate, Tag
# Input  : output of Task 2
# Output : final production-ready JSON
# ─────────────────────────────────────────────────────────────────

AIML_KEYWORDS = [
    "data scientist", "data science", "machine learning", "ml engineer",
    "ai engineer", "artificial intelligence", "deep learning", "nlp",
    "computer vision", "llm", "generative ai", "mlops", "data analyst",
    "analytics engineer", "research scientist", "python", "pytorch",
    "tensorflow", "hugging face", "langchain", "rag", "transformer",
]

def build_validator_task(agent: Agent, summarizer_task: Task) -> Task:
    kw_list = ", ".join(f'"{k}"' for k in AIML_KEYWORDS)

    description = f"""
You will receive a JSON array of enriched job objects from the previous task.

Your responsibilities:

1. DEDUPLICATE
   - If two or more jobs share the same "url", keep only the first occurrence.

2. RELEVANCE CHECK
   - A job is relevant if its title OR description_raw contains at least ONE
     of these keywords (case-insensitive): {kw_list}
   - Set "is_valid": true for relevant jobs, "is_valid": false for irrelevant ones.
   - Do NOT remove invalid jobs – keep them in the array but flag them.

3. DOMAIN TAGGING
   - Add "domain_tags": list[str] to each job.
   - Possible values: "Data Science", "Machine Learning", "AI Engineering",
     "MLOps", "NLP", "Computer Vision", "Data Engineering", "BI/Analytics"
   - A job can have multiple tags. Use an empty list [] if none apply.

4. FINAL SCHEMA
   Ensure every object in the output array has exactly these fields:
   {{
     "title":           string,
     "company":         string,
     "location":        string | null,
     "salary":          string | null,
     "url":             string,
     "description_raw": string,
     "skills":          list[str],
     "qualifications":  list[str],
     "summary":         string,
     "is_valid":        bool,
     "domain_tags":     list[str],
     "published_at":    string | null,
     "contract_type": string | null
   }}

5. OUTPUT
   Return ONLY the final JSON array. No markdown. No explanation. Pure JSON.
"""
    return Task(
        description=description,
        agent=agent,
        context=[summarizer_task],
        expected_output=(
            "A final, production-ready JSON array. Every object contains all "
            "12 fields listed in the task. No duplicates. is_valid correctly set. "
            "published_at preserved from input (ISO-8601 string or null). "
            "No markdown fences. Pure JSON only."
        ),
    )