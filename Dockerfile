# 使用 Python 3.9 作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
# 复制项目文件
COPY . .

# 安装项目依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 暴露端口
EXPOSE 3008

# 启动命令
CMD ["python", "main.py"] 