FROM python:3.11-slim

# Забороняємо Python буферизувати вивід (щоб одразу бачити логи)
ENV PYTHONUNBUFFERED=1

# Встановлюємо Chromium, WebDriver та залежності для psycopg2
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]