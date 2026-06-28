# agents/crew.py
# Assembles and executes the CrewAI pipeline

import json
import logging
import re
from crewai import Crew, Process

from agents.agents import (
    build_scraper_agent,
    build_summarizer_agent,
    build_validator_agent,
)
from agents.tasks import (
    build_scraper_task,
    build_summarizer_task,
    build_validator_task,
)

logger = logging.getLogger(__name__)

# Batch size: how many jobs to send per CrewAI run.
# Keep small enough so LLM output never gets truncated.
BATCH_SIZE = 5


def run_crew(raw_jobs: list[dict]) -> list[dict]:
    """
    Execute the full CrewAI pipeline on a list of raw job dicts.
    Automatically batches jobs so LLM output is never truncated.
    """
    if not raw_jobs:
        logger.warning("run_crew called with empty job list – skipping.")
        return []

    logger.info(
        "Starting CrewAI pipeline with %d raw jobs (batch size: %d) …",
        len(raw_jobs), BATCH_SIZE,
    )

    all_results: list[dict] = []

    # ── Process in batches ──────────────────────────────────────
    for batch_num, i in enumerate(range(0, len(raw_jobs), BATCH_SIZE), start=1):
        batch = raw_jobs[i : i + BATCH_SIZE]
        logger.info("Processing batch %d (%d jobs) …", batch_num, len(batch))

        try:
            results = _run_single_batch(batch)
            all_results.extend(results)
            logger.info(
                "Batch %d complete – %d jobs extracted.", batch_num, len(results)
            )
        except Exception as e:
            logger.error("Batch %d failed: %s – skipping.", batch_num, e)
            continue

    logger.info(
        "All batches done. Total validated jobs: %d", len(all_results)
    )
    return all_results


def _run_single_batch(batch: list[dict]) -> list[dict]:
    """Run the three-agent pipeline on a single batch and return parsed jobs."""

    # Build agents
    scraper_agent    = build_scraper_agent()
    summarizer_agent = build_summarizer_agent()
    validator_agent  = build_validator_agent()

    # Build tasks
    scraper_task    = build_scraper_task(scraper_agent, batch)
    summarizer_task = build_summarizer_task(summarizer_agent, scraper_task)
    validator_task  = build_validator_task(validator_agent, summarizer_task)

    # Assemble & run crew
    crew = Crew(
        agents=[scraper_agent, summarizer_agent, validator_agent],
        tasks=[scraper_task, summarizer_task, validator_task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()

    output_text = _extract_text(result)
    return _parse_json_output(output_text)


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _extract_text(result) -> str:
    """Handle CrewAI returning either a string or an object with .raw."""
    if isinstance(result, str):
        return result
    if hasattr(result, "raw"):
        return result.raw
    return str(result)


def _parse_json_output(text: str) -> list[dict]:
    """
    Robustly parse LLM JSON output with three strategies:

    1. Standard parse after stripping markdown fences.
    2. Truncation repair: if the array is cut off, close it and retry.
    3. Object-by-object extraction: pull every complete {...} block
       individually as a last resort.
    """
    # ── Strip markdown fences ──────────────────────────────────
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

    # Find the outermost array bounds
    start = cleaned.find("[")
    if start == -1:
        logger.error("No JSON array found in output.")
        return _extract_objects_fallback(cleaned)

    end = cleaned.rfind("]")

    # ── Strategy 1: normal parse ───────────────────────────────
    if end != -1:
        json_str = cleaned[start : end + 1]
        try:
            jobs = json.loads(json_str)
            if isinstance(jobs, list):
                logger.info("Strategy 1 (normal parse): %d jobs.", len(jobs))
                return [j for j in jobs if isinstance(j, dict)]
        except json.JSONDecodeError:
            pass  # fall through to strategy 2

    # ── Strategy 2: truncation repair ─────────────────────────
    # Output was cut mid-stream. Take everything from "[" onward,
    # strip trailing incomplete object, and close the array.
    partial = cleaned[start:]
    # Remove the last incomplete object: find the last complete "},"  or "}"
    last_complete = max(partial.rfind("},"), partial.rfind("}\n"))
    if last_complete != -1:
        repaired = partial[: last_complete + 1] + "\n]"
        try:
            jobs = json.loads(repaired)
            if isinstance(jobs, list):
                logger.warning(
                    "Strategy 2 (truncation repair): recovered %d jobs.", len(jobs)
                )
                return [j for j in jobs if isinstance(j, dict)]
        except json.JSONDecodeError:
            pass

    # ── Strategy 3: object-by-object extraction ────────────────
    logger.warning("Strategies 1 & 2 failed – falling back to object extraction.")
    return _extract_objects_fallback(cleaned)


def _extract_objects_fallback(text: str) -> list[dict]:
    """
    Extract every syntactically complete JSON object from raw text.
    Used when the overall array is broken but individual objects are intact.
    """
    jobs = []
    depth = 0
    start = None

    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                fragment = text[start : i + 1]
                try:
                    obj = json.loads(fragment)
                    if isinstance(obj, dict) and "title" in obj and "url" in obj:
                        jobs.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None

    logger.warning("Strategy 3 (object extraction): recovered %d jobs.", len(jobs))
    return jobs