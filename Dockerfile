FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Ensure session volume mount point exists
RUN mkdir -p /session

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "attendance_bot.py"]
