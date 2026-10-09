FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy only runtime files. Private records, seed credentials and recovery HTML
# are intentionally excluded from the public web-service image.
COPY app_server.py index.html ./
COPY pages ./pages
COPY images ./images
COPY achievements.json faculty.json timetable.json section-roster.json official-sources.json ./

EXPOSE 10000
CMD ["python", "app_server.py", "--host", "0.0.0.0"]
