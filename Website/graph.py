# ==========================
# Standard Library
# ==========================
import os
import re
import datetime as _dt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import TypedDict, Literal, Optional

# ==========================
# Third-Party Libraries
# ==========================
import requests
import serpapi
from dotenv import load_dotenv
from IPython.display import Image, display
from pydantic import BaseModel, Field, model_validator
from supabase import Client, create_client

load_dotenv()

# ==========================
# LangChain / LangGraph / LangSmith
# ==========================
from langchain.agents import create_agent
from langchain_groq import ChatGroq
from langchain_nvidia_ai_endpoints import ChatNVIDIADynamo

from langgraph.graph import StateGraph, START, END

from langsmith import traceable

# ==========================
# Load Environment Variables
# ==========================

class JobInformation(BaseModel):
    title: Optional[str] = Field(default=None, description="Job Title")
    company_name: Optional[str] = Field(default=None, description="Company Name")
    location: Optional[str] = Field(default=None, description="Job Location")
    posted_at: Optional[str] = Field(default=None, description="Raw posted date text as stated in source, e.g. '2 hari yang lalu'")
    posted_date_exact: datetime = Field(
        default=None,
        description="Computed exact posting date (auto-filled, do not fill manually)"
    )
    salary: Optional[str] = Field(default=None, description="Job Salary")
    schedule_type: Optional[str] = Field(default=None, description="Job Contract Type")
    source_link: Optional[str] = Field(default=None, description="Job Source Link")
    thumbnail: Optional[str] = Field(default=None, description="Job Thumbnail Image Link")
    description: Optional[str] = Field(default=None, description="Job Description")
    valid_url: bool = Field(
        default=False,
        description="Auto-computed by validator, do not fill manually"
    )

    extracted_at: datetime = datetime.now(ZoneInfo("Asia/Jakarta"))

    @model_validator(mode="after")
    def normalize_empty_fields(self):
        # Semua field string kosong/None diseragamkan jadi "Not specified"
        # supaya konsisten dan tidak ada None yang lolos ke tahap berikutnya
        string_fields = [
            "title", "company_name", "location", "posted_at",
            "salary", "schedule_type", "source_link", "thumbnail", "description"
        ]
        for field_name in string_fields:
            value = getattr(self, field_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                setattr(self, field_name, "Not specified")
        return self

    @model_validator(mode="after")
    def compute_posted_date(self):
        now = self.extracted_at
        text = (self.posted_at or "").lower().strip()

        if not text:
            text = "hari ini"

        match = re.search(r"(\d+)\s*(menit|jam|hari|minggu|bulan|tahun)", text)

        if "hari ini" in text or "today" in text:
            self.posted_date_exact = now
        elif "kemarin" in text or "yesterday" in text:
            self.posted_date_exact = now - timedelta(days=1)
        elif match:
            value = int(match.group(1))
            unit = match.group(2)
            unit_map = {
                "menit": timedelta(minutes=value),
                "jam": timedelta(hours=value),
                "hari": timedelta(days=value),
                "minggu": timedelta(weeks=value),
                "bulan": timedelta(days=value * 30),   # approximation
                "tahun": timedelta(days=value * 365),  # approximation
            }
            delta = unit_map.get(unit, timedelta(0))
            self.posted_date_exact = now - delta
        else:
            # format tidak dikenali → default ke hari ini
            self.posted_date_exact = now

        return self

    @model_validator(mode="after")
    def compute_valid_url(self):
        timeout = 8
        link = self.source_link
        if not link or not isinstance(link, str) or link == "Not specified":
            self.valid_url = False
            return self

        url_pattern = re.compile(
            r'^https?://'
            r'([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}'
            r'(:\d+)?'
            r'(/.*)?$'
        )
        if not url_pattern.match(link):
            self.valid_url = False
            return self

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        }

        try:
            response = requests.get(
                link, headers=headers, timeout=timeout,
                allow_redirects=True, stream=True
            )
            # Sebagian situs balikin 403 ke bot tapi link sebenarnya valid.
            # Anggap valid kalau status < 400, ATAU statusnya 403 (kemungkinan besar bot-block, bukan link mati)
            if response.status_code < 400 or response.status_code == 403:
                self.valid_url = True
            else:
                self.valid_url = False
        except requests.RequestException:
            self.valid_url = False

        return self

llm = ChatGroq(
    api_key = os.getenv("GROQ_API_KEY"),
    model = "meta-llama/llama-4-scout-17b-16e-instruct",
    max_tokens=8192,
    temperature=0
)

extractor_agent = create_agent(
    model=llm,
    response_format=JobInformation,
    system_prompt="""Kamu adalah agent ekstraksi informasi dari hasil scraping halaman lowongan pekerjaan dari data yang diberikan. Kembalikan jawaban HANYA berdasarkan data yang diberikan, tanpa menambahkan, mengasumsikan, atau mengurangi informasi apa pun.

Beberapa field (posted_at, salary, schedule_type) mungkin berada di dalam objek bernama "detected_extensions" pada data sumber, bukan di level utama. Cari field tersebut di dalam "detected_extensions" jika tidak ditemukan di level utama.

Ekstrak hanya field-field berikut, dan kembalikan sebagai Dictionary flat (bukan nested) dengan key persis seperti berikut:
- title
- company_name
- location
- posted_at: (ambil dari detected_extensions.posted_at jika ada)
- salary: (ambil dari detected_extensions.salary jika ada)
- schedule_type: (ambil dari detected_extensions.schedule_type jika ada)
- source_link
- thumbnail
- description

Aturan:
1. Jangan mengubah, menyimpulkan, atau menambahkan informasi yang tidak ada secara eksplisit pada data sumber.
2. Jika suatu field benar-benar tidak ditemukan di data (baik di level utama maupun di dalam detected_extensions), isi dengan None.
3. Jangan mengembalikan field lain selain 10 field berikut: title, company_name, location, posted_at, salary, schedule_type, source_link, thumbnail, description, valid_url.
4. Output HARUS berupa Dictionary valid dengan key sesuai daftar di atas, tanpa teks tambahan di luar Dictionary."""
)

class SkillsInformation(BaseModel):
    skills : Optional[list[str]] = Field(default=[], description="Skill-skill dalam lowongan")

extractor_skills_agent = create_agent(
    model = llm,
system_prompt = """Anda adalah agent yang bertugas mengekstrak skill (keahlian teknis maupun non-teknis)
yang DIMINTA/DISYARATKAN dalam sebuah lowongan kerja.

ATURAN NORMALISASI:
Satukan istilah yang bermakna sama meskipun penulisannya berbeda, gunakan bentuk
paling umum sebagai representasi final. Contoh:
- "ml", "machine learning" -> "machine learning"
- "llm", "large language model(s)" -> "llm"
- "py", "python3", "python 3" -> "python"
- "db", "database" -> "database"
- "k8s", "kubernetes" -> "kubernetes"
- "ai", "artificial intelligence" -> "artificial intelligence"
- "rag", "retrieval augmented generation" -> "rag"
- "vector db", "vector databases" -> "vector database"
Terapkan logika serupa untuk istilah lain berdasarkan konteks.

DEFINISI SKILL YANG VALID (hanya ini yang boleh diekstrak):
1. Bahasa pemrograman (contoh: python, javascript, java)
2. Framework/library dengan NAMA SPESIFIK (contoh: langchain, llamaindex, react, django)
3. Platform/tools dengan NAMA SPESIFIK (contoh: dataiku dss, kubernetes, docker, aws)
4. Database/teknologi data dengan NAMA SPESIFIK (contoh: postgresql, vector database, mongodb)
5. Domain keahlian yang jadi bidang kerja (contoh: machine learning, data science, llm, rag, nlp)
6. Metodologi kerja (contoh: agile, scrum)
7. Sertifikasi
8. Soft skill eksplisit (contoh: komunikasi, koordinasi, leadership)

BATASAN JUMLAH DAN KOMPOSISI (PENTING):
- Ekstrak MAKSIMAL 10 skill saja, yang paling penting/relevan berdasarkan seberapa
  sering ditekankan atau seberapa krusial posisinya dalam kualifikasi lowongan.
- Komposisi WAJIB: 8 hard skill (teknis, kategori 1-5 di atas) + 2 soft skill
  (kategori 8 di atas).
- Jika hard skill yang eksplisit disebutkan lebih dari 8, pilih 8 yang PALING
  SERING disebut/PALING DITEKANKAN sebagai requirement utama (bukan skill
  tambahan/nice-to-have).
- Jika soft skill yang disebutkan lebih dari 2, pilih 2 yang paling ditekankan.
- Jika soft skill yang disebutkan KURANG dari 2, isi sisa kuota dengan hard skill
  tambahan (total tetap maksimal 10).
- Jika hard skill yang disebutkan KURANG dari 8, cukup ambil semua yang ada
  (jangan mengarang skill yang tidak disebutkan dalam teks).
- Urutkan list dari yang PALING PENTING ke yang KURANG PENTING.

ATURAN TAMBAHAN:
- Perbaiki typo (contoh: "koordiansi" -> "koordinasi").
- Semua huruf kecil, tanpa duplikat.
- Jangan memasukkan nama jabatan, nama perusahaan, atau kalimat penuh.
- Jangan menambahkan skill yang tidak disebutkan/tersirat jelas dalam teks.
- Jika tidak ada skill ditemukan, kembalikan list kosong.

Isi field `skills` sesuai aturan di atas.
""",
    response_format=SkillsInformation
)

class SummaryDescription(BaseModel):
    description_summary: Optional[str] = Field(default=None, description="Ringkasan singkat 2-4 kalimat dari job description")

import re

def description_to_html(text: str) -> str:
    """Konversi teks deskripsi pekerjaan menjadi HTML (heading + list)."""

    if not text or text.strip() == "" or text == "Not specified":
        return "<p>Not specified</p>"

    raw_lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in raw_lines if line]

    HEADING_KEYWORDS = [
        "kualifikasi", "qualification", "requirements", "persyaratan",
        "deskripsi pekerjaan", "job description", "responsibilities", "tanggung jawab",
        "tugas", "about the role", "about the team", "about us", "tentang",
        "benefit", "benefits", "fasilitas", "nilai plus", "preferred", "plus point",
        "skills", "keahlian", "requirement", "what you'll do", "what we offer",
        "key responsibilities", "who you are", "nice to have", "must have"
    ]

    bullet_pattern = re.compile(r"^[-•●▪*]\s*")

    def is_bullet(line: str) -> bool:
        return bool(bullet_pattern.match(line))

    expanded_lines = []
    for line in lines:
        if not is_bullet(line):
            match = re.match(r"^([A-Za-z\s]{3,30}):\s*(.+)$", line)
            if match and match.group(1).strip().lower() in HEADING_KEYWORDS:
                expanded_lines.append(match.group(1).strip() + ":")
                expanded_lines.append(match.group(2).strip())
                continue
        expanded_lines.append(line)
    lines = expanded_lines

    def is_heading(line: str) -> bool:
        clean = line.rstrip(":").strip().lower()
        if any(keyword == clean or clean.startswith(keyword) for keyword in HEADING_KEYWORDS):
            return True
        if line.endswith(":") and len(line) < 60 and not is_bullet(line):
            return True
        words = line.split()
        if (
            not is_bullet(line)
            and len(line) < 50
            and len(words) <= 6
            and not line.endswith((".", ",", ")"))
            and sum(1 for w in words if w[:1].isupper()) >= max(1, len(words) - 1)
        ):
            return True
        return False

    html_parts = []
    current_list = []

    def flush_list():
        nonlocal current_list
        if current_list:
            html_parts.append(
                "<ul>" + "".join(f"<li>{item}</li>" for item in current_list) + "</ul>"
            )
            current_list = []

    for line in lines:
        if is_bullet(line):
            item = bullet_pattern.sub("", line).strip()
            current_list.append(item)
        elif is_heading(line):
            flush_list()
            heading_text = line.rstrip(":").strip()
            html_parts.append(f"<h3>{heading_text}</h3>")
        else:
            flush_list()
            html_parts.append(f"<p>{line}</p>")

    flush_list()
    return "".join(html_parts)

# Agent HANYA untuk tugas yang butuh reasoning: meringkas
summerize_agent = create_agent(
    model=llm,
    response_format=SummaryDescription,
    system_prompt="""Kamu adalah agent peringkas deskripsi lowongan pekerjaan.

Kamu akan menerima teks deskripsi pekerjaan. Tugas kamu HANYA membuat ringkasan singkat (2-4 kalimat) dari teks tersebut dalam Bahasa Indonesia.

Aturan:
1. Jangan mengarang atau menambahkan informasi yang tidak ada di teks asli.
2. Jika teks yang diberikan kosong atau "Not specified", kembalikan description_summary = "Not specified".
3. Fokus pada: peran/tanggung jawab utama, kualifikasi kunci, dan hal penting lain yang relevan.
4. Jangan menyalin ulang teks asli secara verbatim, buat benar-benar ringkasan yang lebih pendek."""
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


"""
fixed_nodes.py
--------------
Berisi definisi state (JobTracker) dan node-node yang SUDAH DIPERBAIKI
dari rancangan awal kamu.

Catatan penting:
- Agent (extractor_agent, extractor_skills_agent, summerize_agent) diasumsikan
  sudah dibuat/diimport di luar file ini.
- Koneksi `supabase` diasumsikan sudah dibuat/diimport di luar file ini.
- `scraper_results` untuk sekarang pakai DUMMY DATA (lihat dummy_data.py)
  supaya testing tidak boros API/koneksi database.
- Semua fungsi konsisten memakai tipe `JobTracker` (sebelumnya ada yang
  salah pakai `JobInformation`, tipe yang tidak pernah didefinisikan).
"""

# from your_agents_module import extractor_agent, extractor_skills_agent, summerize_agent
# from your_db_module import supabase
# from your_scraper_module import scraper_results  # <-- di real case, bukan dummy


class JobTracker(TypedDict):
    list_raw_scaping_job: list
    counter_list: int
    processes_job: dict
    exist_job_vacancy: Literal["EXIST", "DOESN'T EXIST"]
    still_counting: Literal["YES", "NO"]
    # BARU: hasil batch-fetch existing jobs dari Supabase, dipakai untuk
    # pengecekan exist secara in-memory (tanpa query per-job di dalam loop).
    existing_source_links: set
    existing_title_company: set

def _to_iso(date_value):
    """
    Konversi nilai tanggal ke string ISO 8601 supaya aman di-serialize
    ke JSON oleh Supabase client.

    FIX untuk error:
    "TypeError: Object of type datetime is not JSON serializable"
    Penyebabnya: field seperti posted_date_exact bisa jadi objek
    datetime.date / datetime.datetime (bukan string) -- baik dari hasil
    parsing agent, atau dari _to_iso versi lama yang cuma `return date_str`
    tanpa benar-benar mengonversi tipe non-string.
    """
    if date_value is None:
        return None
    if isinstance(date_value, (_dt.datetime, _dt.date)):
        return date_value.isoformat()
    # kalau sudah string, kembalikan apa adanya
    return date_value


# ---------------------------------------------------------------------------
# NODE BARU: fetch_existing_jobs_node
# ---------------------------------------------------------------------------
def fetch_existing_jobs_node(state: JobTracker) -> JobTracker:
    """
    Batch-fetch data existing dari Supabase SEKALI di awal (bukan per-job
    di dalam loop). Hasilnya dipakai untuk pengecekan exist secara in-memory
    di extracting_node & check_job_vacancy_exists_node, sehingga:
      1. Tidak ada DB round-trip berulang per job untuk cek existence.
      2. Job yang sudah exist (dikenali dari source_link mentah) bisa di-skip
         SEBELUM memanggil extractor_agent -> hemat biaya API agent juga,
         bukan cuma hemat query DB.

    Cek dilakukan 2 tahap:
      a) source_link mentah dari hasil scraping (belum diproses agent)
      b) title + company_name mentah dari hasil scraping, sebagai fallback
         jaga-jaga kalau source_link berubah tapi lowongannya sama persis.
         (Perbandingan title/company final yang sudah dinormalisasi agent
         tetap dilakukan lagi di check_job_vacancy_exists_node, tapi tanpa
         query DB baru -- cukup dicocokkan ke set yang sudah diambil di sini.)
    """
    raw_jobs = state['list_raw_scaping_job']

    raw_source_links = [j.get('source_link') for j in raw_jobs if j.get('source_link')]
    raw_companies = list({j.get('company_name') for j in raw_jobs if j.get('company_name')})

    existing_source_links = set()
    if raw_source_links:
        result_links = (
            supabase.table("lowongan")
            .select("source_link")
            .in_("source_link", raw_source_links)
            .execute()
        )
        existing_source_links = {row["source_link"] for row in result_links.data}

    existing_title_company = set()
    if raw_companies:
        result_title_company = (
            supabase.table("lowongan")
            .select("title, company_name")
            .in_("company_name", raw_companies)
            .execute()
        )
        existing_title_company = {
            (row["title"], row["company_name"]) for row in result_title_company.data
        }

    state['existing_source_links'] = existing_source_links
    state['existing_title_company'] = existing_title_company
    return state


# ---------------------------------------------------------------------------
# NODE 1: scraping_node
# ---------------------------------------------------------------------------
def scraping_node(state: JobTracker) -> JobTracker:
    # FIX: scraper_results diasumsikan berasal dari luar (dummy saat testing,
    # scraper asli saat production). Tidak diubah strukturnya, cuma dipastikan
    # sumbernya jelas lewat import/parameter di luar node.
    query_jobs = os.getenv("QUERY_JOBS")
    scraper = serpapi.Client(api_key=os.getenv("SERP_API_KEY"))
    scraper_results = scraper.search({
        "engine": "google_jobs",
        "q": query_jobs,
        "location": "Indonesia",
        "google_domain": "google.co.id",
        "hl": "id",
        "gl": "id"
    })
    state['list_raw_scaping_job'] = scraper_results['jobs_results']
    return state


# ---------------------------------------------------------------------------
# NODE 2: check_duplicate_and_extracting_node
# ---------------------------------------------------------------------------
def check_duplicate_and_extracting_node(state: JobTracker) -> JobTracker:
    counter = state['counter_list']
    raw_data = state['list_raw_scaping_job'][counter]

    # FIX (hemat biaya agent): kalau source_link mentah ini sudah diketahui
    # exist di DB (dari batch fetch di fetch_existing_jobs_node), langsung
    # tandai EXIST dan JANGAN panggil extractor_agent sama sekali. Ini yang
    # tadinya jadi pemborosan: dulu agent selalu dipanggil dulu, baru dicek
    # exist belakangan -- sehingga job yang sudah ada tetap membayar biaya
    # API call agent secara sia-sia.
    raw_source_link = raw_data.get('source_link')
    if raw_source_link and raw_source_link in state['existing_source_links']:
        state['exist_job_vacancy'] = "EXIST"
        state['processes_job'] = {}
        # FIX: counter_list HARUS di-increment di sini juga. Jalur ini
        # (skip_to_counter) melewati check_job_vacancy_exists_node sama
        # sekali, yang biasanya tempat counter bertambah untuk kasus EXIST.
        # Tanpa ini, index job yang di-skip tidak pernah maju -> infinite
        # loop (GraphRecursionError).
        state['counter_list'] += 1
        return state
    else:
        state['exist_job_vacancy'] = "DOESN'T EXIST"

        result = extractor_agent.invoke({
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"tampilkan data scraping dari data ini dan cek apakah "
                        f"url lowongan nya valid atau tidak = {raw_data}"
                    ),
                }
            ]
        })
        state['processes_job'] = dict(result['structured_response'])
        return state


# ---------------------------------------------------------------------------
# NODE 3: check_job_vacancy_exists_node
# ---------------------------------------------------------------------------
def check_job_vacancy_exists_node(state: JobTracker) -> JobTracker:
    """
    Cek apakah lowongan (yang sudah lolos dari pre-check di check_duplicate_and_extracting_node)
    ternyata tetap sudah ada di DB, berdasarkan title + company_name yang
    SUDAH DINORMALISASI oleh extractor_agent (beda dengan raw title/company
    yang dipakai di fetch_existing_jobs_node).

    FIX (efisiensi + hindari PGRST100): node ini SEKARANG TIDAK melakukan
    query DB sama sekali. Sebelumnya di sini ada 1-2 query per job
    (source_link check + title/company check), sekarang cukup dicocokkan
    ke `existing_title_company` yang sudah diambil sekali di awal oleh
    fetch_existing_jobs_node. Ini juga otomatis menghindari error PGRST100
    (failed to parse logic tree) karena tidak ada string filter manual sama
    sekali yang perlu dibangun -- perbandingan cukup pakai tuple Python biasa.
    """
    title = state['processes_job'].get('title')
    company_name = state['processes_job'].get('company_name')

    if (title, company_name) in state['existing_title_company']:
        state['counter_list'] += 1
        state['exist_job_vacancy'] = "EXIST"
    else:
        state['exist_job_vacancy'] = "DOESN'T EXIST"

    return state


# ---------------------------------------------------------------------------
# NODE 4: extract_skills_node
# ---------------------------------------------------------------------------
def extract_skills_node(state: JobTracker) -> JobTracker:
    result_extract_skill = extractor_skills_agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": (
                    "Ekstrak skill-skill dalam lowongan ini:\n"
                    f"{state['processes_job']['description']}"
                ),
            }
        ]
    })
    state['processes_job']['skills'] = result_extract_skill['structured_response'].skills
    return state


# ---------------------------------------------------------------------------
# NODE 5: summarize_description_node
# ---------------------------------------------------------------------------
def summarize_description_node(state: JobTracker) -> JobTracker:
    # FIX: sebelumnya pakai `job_data['description']` yang tidak terdefinisi.
    # Seharusnya ambil dari state, bukan variabel luar yang tidak ada.
    summary_result = summerize_agent.invoke({
        "messages": [
            {
                "role": "user",
                "content": (
                    "Ringkas deskripsi pekerjaan berikut:\n\n"
                    f"{state['processes_job']['description']}"
                ),
            }
        ]
    })
    state['processes_job']['description_summary'] = (
        summary_result['structured_response'].description_summary
    )
    return state


# ---------------------------------------------------------------------------
# NODE 6: description_to_html_node
# ---------------------------------------------------------------------------
def description_to_html_node(state: JobTracker) -> JobTracker:
    """Konversi teks deskripsi pekerjaan menjadi HTML (heading + list)."""
    text = state['processes_job']['description']

    # FIX: sebelumnya early-return berupa STRING ("<p>Not specified</p>"),
    # bukan `state`. Ini melanggar kontrak node LangGraph yang harus selalu
    # mengembalikan state (dict). Sekarang tetap update state lalu return state.
    if not text or text.strip() == "" or text == "Not specified":
        state['processes_job']['description'] = "<p>Not specified</p>"
        return state

    raw_lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in raw_lines if line]

    HEADING_KEYWORDS = [
        "kualifikasi", "qualification", "requirements", "persyaratan",
        "deskripsi pekerjaan", "job description", "responsibilities", "tanggung jawab",
        "tugas", "about the role", "about the team", "about us", "tentang",
        "benefit", "benefits", "fasilitas", "nilai plus", "preferred", "plus point",
        "skills", "keahlian", "requirement", "what you'll do", "what we offer",
        "key responsibilities", "who you are", "nice to have", "must have"
    ]

    bullet_pattern = re.compile(r"^[-•●▪*]\s*")

    def is_bullet(line: str) -> bool:
        return bool(bullet_pattern.match(line))

    expanded_lines = []
    for line in lines:
        if not is_bullet(line):
            match = re.match(r"^([A-Za-z\s]{3,30}):\s*(.+)$", line)
            if match and match.group(1).strip().lower() in HEADING_KEYWORDS:
                expanded_lines.append(match.group(1).strip() + ":")
                expanded_lines.append(match.group(2).strip())
                continue
        expanded_lines.append(line)
    lines = expanded_lines

    def is_heading(line: str) -> bool:
        clean = line.rstrip(":").strip().lower()
        if any(keyword == clean or clean.startswith(keyword) for keyword in HEADING_KEYWORDS):
            return True
        if line.endswith(":") and len(line) < 60 and not is_bullet(line):
            return True
        words = line.split()
        if (
            not is_bullet(line)
            and len(line) < 50
            and len(words) <= 6
            and not line.endswith((".", ",", ")"))
            and sum(1 for w in words if w[:1].isupper()) >= max(1, len(words) - 1)
        ):
            return True
        return False

    html_parts = []
    current_list = []

    def flush_list():
        nonlocal current_list
        if current_list:
            html_parts.append(
                "<ul>" + "".join(f"<li>{item}</li>" for item in current_list) + "</ul>"
            )
            current_list = []

    for line in lines:
        if is_bullet(line):
            item = bullet_pattern.sub("", line).strip()
            current_list.append(item)
        elif is_heading(line):
            flush_list()
            heading_text = line.rstrip(":").strip()
            html_parts.append(f"<h3>{heading_text}</h3>")
        else:
            flush_list()
            html_parts.append(f"<p>{line}</p>")

    flush_list()
    state['processes_job']['description'] = "".join(html_parts)

    return state


# ---------------------------------------------------------------------------
# NODE 7: delete_unnecessary_field_node
# ---------------------------------------------------------------------------
def delete_unnecessary_field_node(state: JobTracker) -> JobTracker:
    # FIX: tipe parameter/return disamakan ke JobTracker (sebelumnya JobInformation
    # yang tidak terdefinisi). FIX: sebelumnya tidak ada `return state` di akhir,
    # sehingga LangGraph menerima None sebagai update state -> error/hilang state.
    # FIX tambahan: pakai .pop(..., None) supaya tidak KeyError kalau field
    # sudah tidak ada (misal dipanggil dua kali / field opsional dari agent).
    state['processes_job'].pop('posted_at', None)
    state['processes_job'].pop('valid_url', None)
    state['processes_job'].pop('extracted_at', None)
    return state


# ---------------------------------------------------------------------------
# NODE 8: insert_lowongan_node
# ---------------------------------------------------------------------------
def insert_job_node(state: JobTracker) -> JobTracker:
    """
    Insert satu data lowongan (dict) beserta skills-nya ke Supabase.
    """
    data = state['processes_job']
    skills = data.get("skills", [])

    lowongan_payload = {
        "title": data.get("title"),
        "company_name": data.get("company_name"),
        "location": data.get("location"),
        "posted_date_exact": _to_iso(data.get("posted_date_exact")),
        "salary": data.get("salary"),
        "schedule_type": data.get("schedule_type"),
        "source_link": data.get("source_link"),
        "thumbnail": data.get("thumbnail"),
        "description": data.get("description"),
        "description_summary": data.get("description_summary"),
    }

    # FIX (pengaman tambahan): jaga-jaga kalau ada field lain yang ternyata
    # bertipe datetime/date (misal dari hasil parsing agent yang tidak
    # terduga), konversi otomatis ke string ISO sebelum dikirim ke Supabase.
    # Ini mencegah "TypeError: Object of type datetime is not JSON
    # serializable" muncul lagi dari field manapun, bukan cuma posted_date_exact.
    for key, value in lowongan_payload.items():
        if isinstance(value, (_dt.datetime, _dt.date)):
            lowongan_payload[key] = value.isoformat()

    # FIX (pengaman tambahan): "value too long for type character varying(500)"
    # Ini muncul kalau kolom di Supabase dibatasi varchar(N) sementara datanya
    # (paling sering `description` setelah dikonversi ke HTML) lebih panjang
    # dari batas itu. Solusi UTAMA yang direkomendasikan: ubah tipe kolom
    # yang relevan (description, description_summary, dst) jadi `text` di
    # Supabase, karena deskripsi lowongan secara alami bisa sangat panjang:
    #   ALTER TABLE lowongan ALTER COLUMN description TYPE text;
    # Baris di bawah ini HANYA pengaman defensif supaya proses tidak crash
    # kalau suatu saat memang ada kolom yang sengaja dibatasi panjangnya --
    # bukan pengganti fix schema di atas.
    MAX_LENGTHS = {
        "title": 500,
        "company_name": 500,
        "location": 500,
        "salary": 500,
        "schedule_type": 500,
        "source_link": 2000,
        "thumbnail": 2000,
        "description": 20000,
        "description_summary": 2000,
    }
    for field, max_len in MAX_LENGTHS.items():
        value = lowongan_payload.get(field)
        if isinstance(value, str) and len(value) > max_len:
            lowongan_payload[field] = value[:max_len]

    result = (
        supabase.table("lowongan")
        .upsert(lowongan_payload, on_conflict="source_link")
        .execute()
    )

    if not result.data:
        raise RuntimeError(f"Gagal insert lowongan: {result}")

    id_lowongan = result.data[0]["id_lowongan"]

    for nama_skill in skills:
        nama_skill_clean = nama_skill.strip().lower()

        skill_result = (
            supabase.table("skill")
            .upsert({"nama_skill": nama_skill_clean}, on_conflict="nama_skill")
            .execute()
        )

        if not skill_result.data:
            raise RuntimeError(f"Gagal insert skill '{nama_skill_clean}': {skill_result}")

        id_skill = skill_result.data[0]["id_skill"]

        supabase.table("lowongan_skill").upsert(
            {"id_lowongan": id_lowongan, "id_skill": id_skill},
            on_conflict="id_lowongan,id_skill",
        ).execute()

    # FIX: counter_list HARUS di-increment di sini untuk job yang BARU
    # (tidak exist). Sebelumnya, counter hanya bertambah di
    # check_job_vacancy_exists_node saat job EXIST, sehingga untuk job baru,
    # counter_list tidak pernah maju -> job index yang sama diproses ulang
    # terus-menerus (infinite loop).
    state['counter_list'] += 1

    return state


# ---------------------------------------------------------------------------
# NODE 9: counter_check (bukan node kondisional murni, tapi node update state)
# ---------------------------------------------------------------------------
def counter_check(state: JobTracker) -> JobTracker:
    # FIX: sebelumnya mengacu ke state["list_number"] yang tidak ada di
    # TypedDict. Field yang benar adalah "list_raw_scaping_job".
    if state["counter_list"] < len(state["list_raw_scaping_job"]):
        state["still_counting"] = "YES"
    else:
        state["still_counting"] = "NO"

    return state


# ---------------------------------------------------------------------------
# CONDITIONAL EDGE FUNCTIONS
# ---------------------------------------------------------------------------
def should_continue(state: JobTracker) -> str:
    if state["still_counting"] == "YES":
        return "continue"
    return "finish"


def route_after_extracting(state: JobTracker) -> str:
    """
    Routing setelah check_duplicate_and_extracting_node. Kalau job sudah ditandai EXIST lewat
    pre-check batch (source_link mentah cocok), langsung ke counter_check
    -- skip check_job_vacancy_exists_node karena processes_job sengaja
    dikosongkan (tidak ada hasil agent untuk job yang di-skip).
    """
    if state["exist_job_vacancy"] == "EXIST":
        return "skip_to_counter"
    return "process"


def route_after_check_exists(state: JobTracker) -> str:
    """Routing setelah cek apakah lowongan sudah ada di DB."""
    if state["exist_job_vacancy"] == "EXIST":
        return "exist"
    return "not_exist"

builder = StateGraph(JobTracker)
 
    # --- register nodes ---
builder.add_node("scraping_node", scraping_node)
builder.add_node("fetch_existing_jobs_node", fetch_existing_jobs_node)
builder.add_node("check_duplicate_and_extracting_node", check_duplicate_and_extracting_node)
builder.add_node("check_job_vacancy_exists_node", check_job_vacancy_exists_node)
builder.add_node("extract_skills_node", extract_skills_node)
builder.add_node("summarize_description_node", summarize_description_node)
builder.add_node("description_to_html_node", description_to_html_node)
builder.add_node("delete_unnecessary_field_node", delete_unnecessary_field_node)
builder.add_node("insert_job_node", insert_job_node)
builder.add_node("counter_check", counter_check)
 
    # --- edges (jalur utama, linear) ---
builder.add_edge(START, "scraping_node")
builder.add_edge("scraping_node", "fetch_existing_jobs_node")
builder.add_edge("fetch_existing_jobs_node", "check_duplicate_and_extracting_node")
 
    # --- conditional: pre-check by raw source_link (in-memory) ---
builder.add_conditional_edges(
    "check_duplicate_and_extracting_node",
    route_after_extracting,
    {
        "skip_to_counter": "counter_check",
        "process": "check_job_vacancy_exists_node",
    },
)
 
    # --- conditional: sudah ada di DB atau belum (in-memory) ---
builder.add_conditional_edges(
    "check_job_vacancy_exists_node",
    route_after_check_exists,
    {
        "exist": "counter_check",
        "not_exist": "extract_skills_node",
    },
)
 
    # --- jalur job baru (belum ada di DB) ---
builder.add_edge("extract_skills_node", "summarize_description_node")
builder.add_edge("summarize_description_node", "description_to_html_node")
builder.add_edge("description_to_html_node", "delete_unnecessary_field_node")
builder.add_edge("delete_unnecessary_field_node", "insert_job_node")
builder.add_edge("insert_job_node", "counter_check")
 
    # --- conditional: masih ada job tersisa untuk diproses? ---
builder.add_conditional_edges(
    "counter_check",
    should_continue,
    {
        "continue": "check_duplicate_and_extracting_node",
        "finish": END,
    },
)

graph = builder.compile()

@traceable(name="call_graph")
def call_graph():
    initial_state = {
        "list_raw_scaping_job": [],
        "counter_list": 0,
        "processes_job": {},
        "exist_job_vacancy": "DOESN'T EXIST",
        "still_counting": "YES",
        "existing_source_links": set(),      # FIX: field baru yang wajib ada
        "existing_title_company": set(),     # FIX: field baru yang wajib ada
    }

    print("=== INVOKE START ===")
    final_state = graph.invoke(initial_state)
    print("=== INVOKE END ===")
    return final_state

result = call_graph()