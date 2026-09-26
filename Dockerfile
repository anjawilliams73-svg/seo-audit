FROM python:3.11-slim

# Install system deps for WeasyPrint and Playwright
RUN apt-get update && apt-get install -y \
    gcc libxml2-dev libxslt-dev libjpeg-dev \
    libffi-dev libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 libglib2.0-0 \
    wget curl \
    fonts-liberation fonts-noto-color-emoji \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium (skip system deps, installed above)
RUN playwright install chromium

COPY . .

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
