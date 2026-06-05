FROM python:3.12-slim

RUN apt-get update && apt-get install -y dos2unix && rm -rf /var/lib/apt/lists/*

RUN useradd -m celeryuser

WORKDIR /app

COPY ./flights/vietnamairlines /app/flights/vietnamairlines
COPY ./common /app/common
COPY ./task /app/task
COPY ./requirements.txt /app/requirements.txt
COPY ./requirements-py312.txt /app/requirements-py312.txt

RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r ./requirements-py312.txt

ENV TZ="Asia/Shanghai"

COPY ./flights/vietnamairlines/start.sh /app/start.sh
RUN find /app -type f -name "*.sh" -exec dos2unix {} \;
RUN chmod +x /app/start.sh
RUN chown -R celeryuser:celeryuser /app

USER celeryuser

ENTRYPOINT ["/app/start.sh"]
