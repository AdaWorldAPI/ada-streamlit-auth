FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m -u 1000 ada && chown -R ada:ada /app
USER ada
ENV PORT=8000
CMD ["sh", "-c", "streamlit run main.py --server.port ${PORT} --server.address 0.0.0.0 --server.headless true"]
