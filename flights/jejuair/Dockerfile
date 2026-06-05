FROM python:3.13-slim

ENV TZ="Asia/Shanghai" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends dos2unix \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m celeryuser

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

RUN mkdir -p /app/flights/jejuair /app/common /app/task/7Cweb

COPY ./flights/jejuair /app/flights/jejuair
COPY ./common /app/common
COPY ./task/7Cweb /app/task/7Cweb

COPY ./flights/jejuair/start.sh /app/start.sh
RUN dos2unix /app/start.sh \
    && chmod +x /app/start.sh \
    && chown -R celeryuser:celeryuser /app

USER celeryuser

ENTRYPOINT ["/app/start.sh"]
