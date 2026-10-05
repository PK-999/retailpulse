FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RETAILPULSE_DATA_DIR=/app/data

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY dashboard ./dashboard
RUN python -m pip install --no-cache-dir '.[dashboard]'

RUN useradd --create-home --uid 10001 retailpulse \
    && mkdir -p /app/data \
    && chown -R retailpulse:retailpulse /app
USER retailpulse

EXPOSE 8501
CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0"]
