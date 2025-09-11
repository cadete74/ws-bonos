FROM python:3.12-slim

# Config Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Código de la app
COPY app.py /app/app.py
COPY market_clients /app/market_clients
COPY static /app/static

# Puerto interno (Uvicorn)
EXPOSE 8000

# Vars default
ENV FETCH_INTERVAL_SECONDS=5

# Comando de arranque
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
