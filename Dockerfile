# Multi-stage build for smaller final image
FROM python:3.12-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip to avoid download issues
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model (optional - can also be done at runtime)
# Skip download if it fails - the app will handle missing model gracefully
RUN python -m spacy download en_core_web_sm --no-cache-dir || echo "SpaCy model download skipped - will be downloaded at runtime if needed"


# Final stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create app user
RUN useradd -m -u 1000 newsroom && \
    mkdir -p /app && \
    chown -R newsroom:newsroom /app

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=newsroom:newsroom . .

# Switch to app user
USER newsroom

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "main.py"]
