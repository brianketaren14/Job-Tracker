# JobRadar — Web Interface untuk Job Tracker

Frontend Flask untuk proyek LangGraph job scraping pipeline.

## Struktur Proyek

```
job-tracker-web/
├── app.py               ← Flask app (routes, scheduler, API)
├── graph.py             ← COPY file graph LangGraph kamu ke sini
├── requirements.txt
├── .env.example
├── templates/
│   ├── base.html
│   ├── index.html       ← Halaman utama (daftar lowongan + search)
│   ├── dashboard.html   ← Dashboard analitik + trigger scraping
│   └── detail.html      ← Detail pekerjaan
└── static/
    ├── css/style.css
    └── js/
        ├── index.js
        ├── dashboard.js
        └── detail.js
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Konfigurasi environment
```bash
cp .env.example .env
# Edit .env dengan nilai asli kamu
```

### 3. Letakkan file graph
Copy semua kode LangGraph pipeline kamu ke `graph.py` di folder ini.
`app.py` akan melakukan `from graph import call_graph` secara lazy.

### 4. Jalankan Flask
```bash
python app.py
# Development: http://localhost:5000

# Production (gunakan gunicorn):
gunicorn -w 1 -b 0.0.0.0:5000 app:app
# Note: gunakan -w 1 karena APScheduler harus jalan di satu process
```

## Fitur

| Halaman | URL | Fungsi |
|---------|-----|--------|
| Beranda | `/` | Daftar lowongan, pencarian real-time, pagination |
| Dashboard | `/dashboard` | Grafik skill, timeline posting, tipe kontrak, trigger scraping manual |
| Detail | `/job/<id>` | Info lengkap, deskripsi HTML, sidebar, tombol lamar |

### API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/api/jobs` | List lowongan (query: `q`, `page`, `per_page`) |
| GET | `/api/jobs/<id>` | Detail satu lowongan |
| GET | `/api/analytics/skills` | Top skill (query: `limit`) |
| GET | `/api/analytics/jobs-per-day` | Posting per hari |
| GET | `/api/analytics/schedule-type` | Distribusi tipe kontrak |
| GET | `/api/analytics/summary` | Total jobs, skills, latest posting |
| POST | `/api/scrape/trigger` | Trigger manual (`body: {password}`) |
| GET | `/api/scrape/status` | Status scraping + riwayat |

### Jadwal Otomatis
APScheduler menjalankan `call_graph()` setiap hari **pukul 12.00 WIB** secara otomatis.

### Trigger Manual
Buka **/dashboard**, masukkan `ADMIN_PASSWORD` dari `.env`, klik **Jalankan Sekarang**.

## Catatan Produksi
- Gunakan `gunicorn -w 1` agar APScheduler tidak duplikat di multiple workers.
- Untuk multi-worker production, pindahkan scheduler ke Celery + Redis atau gunakan cron system.
- Pastikan kolom `description` di Supabase bertipe `text` (bukan `varchar`) agar tidak terpotong.
