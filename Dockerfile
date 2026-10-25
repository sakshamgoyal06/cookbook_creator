FROM python:3.12-slim

# WeasyPrint needs Pango and HarfBuzz at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-noto-core ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
# Railway (and most hosts) set PORT. Uploads transcribe and structure inside the request
# until the background worker lands, so allow long requests.
CMD python wsgi.py migrate && gunicorn wsgi:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --timeout 300
