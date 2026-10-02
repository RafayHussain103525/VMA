FROM python:3.11-slim

# Install system dependencies for asyncpg/psycopg if needed during build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
# Note: In docker-compose we will override this to add --reload for dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]