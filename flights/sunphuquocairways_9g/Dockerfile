FROM python:3.13-slim

ENV TZ="Asia/Shanghai" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends dos2unix \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m celeryuser

WORKDIR /app

RUN mkdir -p /app/flights/sunphuquocairways_9g \
    && mkdir -p /app/common \
    && mkdir -p /app/task/9Gapp

COPY ./flights/sunphuquocairways_9g /app/flights/sunphuquocairways_9g
COPY ./common /app/common
COPY ./task/9Gapp /app/task/9Gapp
COPY ./requirements-py313.txt /app/requirements-py313.txt

RUN pip install -r /app/requirements-py313.txt

COPY ./flights/sunphuquocairways_9g/start.sh /app/start.sh
RUN find /app -type f -name "*.sh" -exec dos2unix {} \; \
    && chmod +x /app/start.sh \
    && chown -R celeryuser:celeryuser /app

USER celeryuser

ENTRYPOINT ["/app/start.sh"]
