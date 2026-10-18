FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (g++ and make needed for CmdStan/Prophet)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
ARG INSTALL_DEV=false
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$INSTALL_DEV" = "true" ]; then REQ=requirements-dev.txt; else REQ=requirements.txt; fi && \
    pip install --no-cache-dir --timeout=120 -r "$REQ"

# Install CmdStan for Prophet (pinned version for reproducibility)
RUN python -m cmdstanpy.install_cmdstan --version 2.38.0 --cores 2 --dir /opt/cmdstan && \
    echo "CMDSTAN=/opt/cmdstan/cmdstan-2.38.0" >> /etc/environment
ENV CMDSTAN=/opt/cmdstan/cmdstan-2.38.0

# Copy application code
COPY . .

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
