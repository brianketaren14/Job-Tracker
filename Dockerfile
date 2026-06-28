# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps (for BeautifulSoup lxml parser)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

EXPOSE 5000

CMD ["gunicorn", "app:app", "-c", "gunicorn.conf.py"]
