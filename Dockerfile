FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source
COPY . .

# Expose port (HF Spaces uses 7860)
EXPOSE 7860

# Start server
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
