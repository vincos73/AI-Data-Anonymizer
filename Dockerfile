FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[web]"

EXPOSE 8080

CMD ["ai-data-anonymizer-web", "--host", "0.0.0.0", "--port", "8080"]
