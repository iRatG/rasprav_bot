FROM python:3.12-slim

# Устанавливаем системные зависимости для psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код копируется последним — чтобы кэш слоёв с зависимостями не инвалидировался
COPY . .

CMD ["python", "main.py"]
