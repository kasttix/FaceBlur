FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsm6 libxext6 libgl1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app.py /app/
COPY templates/ /app/templates/
COPY static/ /app/static/

RUN pip install --no-cache-dir \
    flask==3.0.0 \
    werkzeug==3.0.1 \
    opencv-python-headless==4.10.0.84 \
    numpy==1.26.4

RUN mkdir -p /app/uploads /app/exports

EXPOSE 9000

# просто запустим flask-приложение
CMD ["python", "app.py"]