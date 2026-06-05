FROM python:3.13-slim

ENV TZ="Asia/Shanghai" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app


# 安装 dos2unix 工具用于转换换行符
RUN apt-get update \
    && apt-get install -y --no-install-recommends dos2unix \
    && rm -rf /var/lib/apt/lists/*

# 创建用户
RUN useradd -m celeryuser

# 设置工作目录
WORKDIR /app

# 创建目标目录
RUN mkdir -p /app/flights/cebupacificair_5j
RUN mkdir -p /app/common
RUN mkdir -p /app/task/5Jweb

# 复制应用代码和依赖文件
COPY ./flights/cebupacificair_5j /app/flights/cebupacificair_5j
COPY ./common /app/common
COPY ./task/5Jweb /app/task/5Jweb
COPY ./requirements-py313.txt /app/requirements-py313.txt

RUN pip install -i https://mirrors.aliyun.com/pypi/simple/ -r /app/requirements-py313.txt
# 复制启动脚本并设置执行权限
COPY ./flights/cebupacificair_5j/start.sh /app/start.sh
# 转换换行符为 Unix 格式
RUN find /app -type f -name "*.sh" -exec dos2unix {} \;


RUN chmod +x /app/start.sh
# 更改目录所有者
RUN chown -R celeryuser:celeryuser /app

# 切换用户
USER celeryuser

# 设置入口点
ENTRYPOINT ["/app/start.sh"]
