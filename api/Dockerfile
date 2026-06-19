FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY api/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY image_pipeline_common ./image_pipeline_common

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]