FROM python:3.12-slim
WORKDIR /app/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV CLEARVIEW_DB=/data/clearview.db
CMD ["sh", "-c", "python -m clearview.seed && uvicorn clearview.api:app --host 0.0.0.0 --port 8000"]
