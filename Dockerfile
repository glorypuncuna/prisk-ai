# Stage 1: Build Frontend Assets
FROM node:20-alpine AS frontend-builder
WORKDIR /build

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python 3.13 Backend
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies (curl for healthcheck, ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python backend dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source and compliance matrix
COPY backend/app ./app
COPY backend/compliance_framework_matrix.json ./compliance_framework_matrix.json

# Copy compiled frontend assets from Stage 1 into /app/frontend/dist
COPY --from=frontend-builder /build/dist /app/frontend/dist

# Set Cloud Run production environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    ENVIRONMENT=production

EXPOSE 8080

# Run uvicorn on $PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
