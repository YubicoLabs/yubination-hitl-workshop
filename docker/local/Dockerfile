FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml VERSION README.md LICENSE ./
COPY backend/ backend/
COPY scripts/start_trial_api.sh scripts/init_db.py scripts/init_system_roles.py scripts/
COPY docker/local/requirements-pqc.lock docker/local/constraints-pqc.txt docker/local/
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes --no-deps -r docker/local/requirements-pqc.lock \
    && pip install --no-cache-dir -c docker/local/constraints-pqc.txt -e . \
    && python -c "from importlib.metadata import version; from fido2.cose import CoseKey; assert version('fido2') == '2.2.1'; assert version('cryptography') == '49.0.0'; assert {-48, -49, -50}.issubset(CoseKey.supported_algorithms())"
EXPOSE 8000
CMD ["sh", "scripts/start_trial_api.sh"]
