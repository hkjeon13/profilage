FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir "defusedxml>=0.7.1" "fastapi>=0.115.0" "httpx>=0.27.0" "psycopg[binary]>=3.2.0" "redis>=5.0.0" "uvicorn[standard]>=0.30.0"

COPY app ./app

RUN addgroup --system profilage && adduser --system --ingroup profilage profilage
USER profilage

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
