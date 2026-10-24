FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=5000 \
    MAX_UPLOAD_MB=50 \
    SUPABASE_STORAGE_PRIMARY=true \
    COOKIE_SECURE=true

EXPOSE 5000

CMD gunicorn run:app --bind 0.0.0.0:${PORT} --workers 2 --timeout 180
