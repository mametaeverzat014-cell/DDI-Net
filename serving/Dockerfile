# CPU-only inference image for the DDI-Net research API.
#
# CPU by choice, not by limitation: a request is one decoder pass over a cached
# encoding and takes ~2 ms warm, so a GPU would add cost and a driver surface
# for nothing. It would also change the arithmetic — the frozen predictions were
# produced on a GPU and this pipeline's parity bound is measured for CPU.
FROM python:3.11-slim

# rdkit needs these at runtime for its C++ extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxrender1 libxext6 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU wheels only: the default index pulls ~2 GB of CUDA libraries this image
# will never use.
COPY serving/requirements.txt /app/serving/requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        -r serving/requirements.txt

COPY src/ /app/src/
COPY serving/ /app/serving/
COPY data/mechanism_v1/ /app/data/mechanism_v1/

# The 18 MB checkpoint is a GitHub Release asset, never a layer in git history.
# Fetched at build time and verified by SHA-256 at startup by serving/integrity.py.
ARG RELEASE_TAG=v2-final-github-safe-2026-09-03
ARG CHECKPOINT=bd45f84e3c1b2c33.pt
RUN mkdir -p /app/runtime/model_assets && \
    curl -sSL --retry 3 -o /app/runtime/model_assets/${CHECKPOINT} \
      "https://github.com/mametaeverzat014-cell/DDI-Net/releases/download/${RELEASE_TAG}/${CHECKPOINT}" && \
    echo "b828a471fcb8d38e0b29d9c67eddec76c1428bc996cc0d4e5b10c026bf659d6f  /app/runtime/model_assets/${CHECKPOINT}" \
      | sha256sum -c -

ENV PYTHONPATH=/app:/app/src
EXPOSE 8000

# One worker: the process holds the model and the cached encoding (~1.2 GB RSS),
# and a second worker would double that for no throughput gain at 2 ms/request.
CMD ["uvicorn", "serving.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
