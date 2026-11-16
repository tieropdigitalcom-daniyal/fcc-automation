FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY packages ./packages
COPY services ./services
COPY scripts ./scripts
COPY migrations ./migrations
COPY fixtures ./fixtures
COPY alembic.ini pyproject.toml ./
RUN useradd --create-home app && mkdir -p /app/runtime && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
