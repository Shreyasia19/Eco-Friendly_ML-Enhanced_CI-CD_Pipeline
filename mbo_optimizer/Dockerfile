FROM python:3.11-slim
WORKDIR /app
COPY optimizer.py .
RUN pip install requests kubernetes
CMD ["python", "optimizer.py"]
