FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY indicator_bridge ./indicator_bridge
RUN pip install --no-cache-dir .

EXPOSE 9527
CMD ["indicator-bridge"]
