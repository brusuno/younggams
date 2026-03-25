FROM python:3.10-slim
WORKDIR /app
COPY . /app
ENV PORT=4173
EXPOSE 4173
CMD ["python3", "server.py"]
