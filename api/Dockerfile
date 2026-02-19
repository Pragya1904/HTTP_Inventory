FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r ./api/requirements.txt



EXPOSE 6577

CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "6577"]
