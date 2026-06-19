FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY worker/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY worker/app ./app
COPY image_pipeline_common ./image_pipeline_common

CMD ["python", "-m", "app.worker"]