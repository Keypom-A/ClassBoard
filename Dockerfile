FROM python:3.11-slim

WORKDIR /app

# キャッシュ破壊
ARG CACHE_BREAKER=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-k", "eventlet", "-w", "1", "h2:app"]
