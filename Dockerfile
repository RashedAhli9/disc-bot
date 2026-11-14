# Python + headless Chromium (for the daily server Excel download). The Playwright base image already
# carries every system library Chromium needs; the bot itself is still just `python bot.py`.
FROM mcr.microsoft.com/playwright/python:v1.56.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .
CMD ["python", "bot.py"]
