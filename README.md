# ⚡ AI Job Tracker

> Agentic AI system that automatically scrapes, analyses, and displays
> Data Science / AI / ML job listings using **CrewAI + NVIDIA NIM + Flask + Supabase**.
> link : https://ai-job-tracker-production-e225.up.railway.app/

## Background

This project was built to address the challenge of monitoring the fast-changing job market in Data Science, Artificial Intelligence, and Machine Learning. Manually checking multiple job boards is time-consuming and often causes talented candidates to miss relevant opportunities. AI Job Tracker automates the process of discovering, collecting, and analyzing job listings, then presents the results in a clear and accessible dashboard.

By combining AI agents, web scraping, and a simple web application, this project helps users save time, identify relevant roles more quickly, and focus on the skills that matter most in today’s competitive job market.

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
