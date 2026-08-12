# ============================================================
# Policy Red Team — Cloud Run Container
# ============================================================
# Build:  docker build -t policy-red-team .
# Run locally (Mode A):
#   docker run -p 8080:8080 \
#     -e APP_PASSWORD=yourpassword \
#     -e APP_MODE=developer_pays \
#     -e LLAMA_CLOUD_API_KEY=llx-... \
#     -e GOOGLE_CLOUD_PROJECT=your-project \
#     -e GOOGLE_CLOUD_LOCATION=us-central1 \
#     -e GCS_BUCKET=policy-red-team-dev \
#     -e GOOGLE_APPLICATION_CREDENTIALS=/app/sa_key.json \
#     policy-red-team
# ============================================================

FROM python:3.11-slim

# System deps for FAISS CPU and PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached)
COPY requirements.txt requirements.streamlit.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements.streamlit.txt

# Copy source code
COPY . .

# Cloud Run always uses port 8080
EXPOSE 8080

# Disable Streamlit's browser-open and telemetry for headless Cloud Run
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_HEADLESS=true

# Run FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]


