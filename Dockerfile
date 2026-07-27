# ─── Build frontend ──────────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ─── Production ──────────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app

# Fonts for rendered post images. Without these Chromium draws empty boxes
# instead of text, and emoji disappear entirely.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        fonts-noto-core \
        fonts-noto-color-emoji \
        fonts-noto-mono \
    && rm -rf /var/lib/apt/lists/*

# Install backend deps
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Headless Chromium for the image renderer
RUN playwright install --with-deps chromium

# Copy backend code
COPY backend/ ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./static

# Create data directories
RUN mkdir -p data data/media

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
