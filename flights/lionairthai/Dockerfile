FROM python:3.9-slim


# 安装 dos2unix 工具用于转换换行符
RUN apt-get update && apt-get install -y dos2unix

ENV TINI_VERSION v0.19.0
ADD https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini /tini
RUN chmod +x /tini

# 创建用户
RUN useradd -m celeryuser

# 设置工作目录
WORKDIR /app

# 创建目标目录
RUN mkdir -p /app/flight/lionairthai
RUN mkdir -p /app/common

# 复制应用代码和依赖文件
COPY ./flights/lionairthai /app/flights/lionairthai
COPY ./common /app/common
COPY ./task/SLweb /app/task/SLweb
COPY ./requirements.txt /app/requirements.txt



# 安装依赖
RUN pip install -r ./requirements.txt

# 设置时区
ENV TZ="Asia/Shanghai"

# 复制启动脚本并设置执行权限
COPY ./flights/lionairthai/start.sh /app/start.sh
# 转换换行符为 Unix 格式
RUN find /app -type f -name "*.sh" -exec dos2unix {} \;


RUN chmod +x /app/start.sh
# 更改目录所有者
RUN chown -R celeryuser:celeryuser /app

# 切换用户
USER celeryuser

ENTRYPOINT ["/tini", "--"]
# 设置入口点
CMD ["/app/start.sh"]
