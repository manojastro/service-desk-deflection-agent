FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY apps ./apps
COPY services ./services
COPY packages ./packages
COPY infra ./infra
RUN pip install --no-cache-dir .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "python -m apps.api.app.seed && uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000"]
