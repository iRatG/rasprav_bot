FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код копируется последним — чтобы кэш слоёв с зависимостями не инвалидировался
COPY . .

CMD ["python", "main.py"]
