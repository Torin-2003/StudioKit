FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg gcc g++ libgomp1 curl fontconfig libass-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && fc-cache -fv && apt-get clean && rm -rf /var/lib/apt/lists/* \
    || (echo "WARNING: CJK font install failed" && apt-get clean && rm -rf /var/lib/apt/lists/*)

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app.py run_app.py license_client.py license_guard.py heartbeat.py paths.py config_client.py db.py ./
COPY hypecutter/ ./hypecutter/
COPY scene_manager/ ./scene_manager/
COPY license/ ./license/

RUN mkdir -p downloads output data/projects

ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    PYTHONUNBUFFERED=1

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py"]
