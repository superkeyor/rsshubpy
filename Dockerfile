# # 使用官方的 Python 镜像作为基础镜像
# FROM python:3.12-slim-bookworm

# PIN python, chromium and driver version
FROM superkeyor/python_chromium_driver:latest

# ENV TZ=US/Central
# RUN apt-get update && apt-get install -y tzdata && \
#     ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
#     dpkg-reconfigure -f noninteractive tzdata

WORKDIR /app

# copy requirements first so pip layer is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt  # --no-cache-dir reduces image size

# copy remaining source files
COPY . .

# # Selenium
# RUN apt-get update && \
#     apt-get install -y \
#     chromium \
#     chromium-driver \
#     xvfb \
#     xauth && \
#     apt-get clean && \
#     rm -rf /var/lib/apt/lists/*

# 暴露端口
EXPOSE 5000

# 启动应用程序
CMD ["gunicorn", "--timeout", "600", "-b", "0.0.0.0:5000", "main:app"]
