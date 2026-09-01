# Build from the repo root (needs pyproject.toml + src/ in the build context):
#   docker build -f src/jottermem/relay/Dockerfile -t jottermem-relay .
#   docker run -p 8000:8000 --env-file .env.relay jottermem-relay
#
# See README.md in this directory for what .env.relay needs and where to
# get it (a Google Cloud OAuth app) before this will actually do anything.

FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir ".[relay]"

EXPOSE 8000

CMD ["uvicorn", "jottermem.relay.app:app", "--host", "0.0.0.0", "--port", "8000"]
