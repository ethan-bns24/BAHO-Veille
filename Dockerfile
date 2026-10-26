FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
RUN mkdir -p /data
ENV BAHO_CONFIG=/app/settings.toml
CMD ["baho-veille", "run"]
