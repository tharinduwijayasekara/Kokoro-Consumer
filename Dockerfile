FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg (and runtime deps for pydub)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN adduser --disabled-password --gecos "" --uid 1000 ttsuser

# Switch to the new user
USER ttsuser

#CMD ["python", "-u", "/app/app/generate_audiobook.py"]