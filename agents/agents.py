# agents/agents.py
# CrewAI Agent definitions — uses crewai's NATIVE LLM class (no LiteLLM, no langchain-groq)
#
# CrewAI >= 1.0 connects to Groq directly via the groq SDK.
# Model string format: "groq/<model-name>"

import os
import logging
from crewai import Agent, LLM

logger = logging.getLogger(__name__)


def _build_llm() -> LLM:
    nvidia_model = os.getenv("NVIDIA_MODEL")
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    nvidia_base_url = os.getenv("NVIDIA_BASE_URL")
    return LLM(
        model=f"openai/{nvidia_model}",   # prefix openai/ → LiteLLM pakai OpenAI-compatible mode
        api_key=nvidia_api_key,
        base_url=nvidia_base_url,
        temperature=0.2,
        max_tokens=4096,
    )


# ─────────────────────────────────────────────────────────────────
# Agent 1 – Scraper Agent
# ─────────────────────────────────────────────────────────────────

def build_scraper_agent() -> Agent:
    return Agent(
        role="Job Data Scraper",
        goal=(
            "Receive a list of raw job objects and clean them into a "
            "consistent, structured format. Ensure every job has a "
            "title, company, location, salary, url, non-empty description, published at and contract type."
        ),
        backstory=(
            "You are a meticulous data engineer specialising in normalising "
            "messy job postings scraped from multiple platforms (LinkedIn, "
            "JobStreet, Google Jobs). You strip HTML artefacts, fix encoding "
            "issues, and ensure every field is a clean string or null. You "
            "never hallucinate — if a field is missing, you leave it as null."
        ),
        llm=_build_llm(),
        verbose=True,
        allow_delegation=False,
    )


# ─────────────────────────────────────────────────────────────────
# Agent 2 – Summarizer Agent
# ─────────────────────────────────────────────────────────────────

def build_summarizer_agent() -> Agent:
    return Agent(
        role="AI/ML Job Content Analyst",
        goal=(
            "For each cleaned job, extract required technical skills, "
            "identify key qualifications, and write a 3–5 bullet-point "
            "summary. Output strict JSON only."
        ),
        backstory=(
            "You are a senior AI/ML recruiter with deep expertise in Data "
            "Science, ML, and AI Engineering. You instantly recognise keywords "
            "like PyTorch, LangChain, RAG, QLoRA, RLHF, ROUGE, dbt, Spark. "
            "You extract only what is explicitly stated in the text — never "
            "inventing skills. Your summaries are crisp and technical."
        ),
        llm=_build_llm(),
        verbose=True,
        allow_delegation=False,
    )


# ─────────────────────────────────────────────────────────────────
# Agent 3 – Validator Agent
# ─────────────────────────────────────────────────────────────────

def build_validator_agent() -> Agent:
    return Agent(
        role="Data Quality Validator",
        goal=(
            "Filter, deduplicate, and validate the enriched job list. "
            "Only approve jobs relevant to AI/ML/Data Science. "
            "Output a final clean JSON array ready for database insertion."
        ),
        backstory=(
            "You are a data quality engineer with zero tolerance for duplicate "
            "or irrelevant records. You verify unique URLs within the batch, "
            "check that each role contains at least one AI/ML/Data keyword, "
            "and ensure mandatory fields are present. Roles like 'Sales Manager' "
            "that slipped through are flagged is_valid=false. Your output is "
            "pure JSON — no markdown, no commentary whatsoever."
        ),
        llm=_build_llm(),
        verbose=True,
        allow_delegation=False,
    )
