FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

# Set timezone to Europe/Berlin (CET/CEST)
ENV TZ=Europe/Berlin
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Ensure session volume mount point exists
RUN mkdir -p /session

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "attendance_bot.py"]
