FROM python:3.12-slim
WORKDIR /app
ARG INSTALL_ORCHESTRATION=false
COPY requirements.txt requirements.lock.txt requirements-orchestration.txt requirements-orchestration.lock.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-wqy-microhei \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi-dev \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/* \
    && if [ "$INSTALL_ORCHESTRATION" = "true" ]; then \
         pip install --no-cache-dir -r requirements-orchestration.lock.txt; \
       else \
         pip install --no-cache-dir -r requirements.lock.txt; \
       fi
COPY . .
# 首次部署时手动执行种子：docker compose run backend python seed_data.py
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
