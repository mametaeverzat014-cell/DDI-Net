# Two stages. The first runs the real pipeline once to produce the artifact; the
# second serves it with numpy alone.
#
# The split is the point: the frozen checkpoint, torch, torch_geometric and
# rdkit are needed to COMPUTE the drug encodings, and needed by nothing at
# request time. Keeping them out of the final image takes RSS from ~1.15 GiB to
# ~158 MiB — the difference between a 2 GB instance and a free 512 MB one.
#
# The artifact is derived, so it is built here rather than committed. Its inputs
# are hash-checked by serving/integrity.py before it is produced.

# ---------------------------------------------------------------- build stage
FROM python:3.11-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
        libxrender1 libxext6 libgomp1 curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY serving/requirements.txt serving/requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        -r serving/requirements.txt

COPY src/ src/
COPY serving/ serving/
COPY data/mechanism_v1/ data/mechanism_v1/

ARG RELEASE_TAG=v2-final-github-safe-2026-09-03
ARG CHECKPOINT=bd45f84e3c1b2c33.pt
RUN mkdir -p runtime/model_assets && \
    curl -sSL --retry 3 -o runtime/model_assets/${CHECKPOINT} \
      "https://github.com/mametaeverzat014-cell/DDI-Net/releases/download/${RELEASE_TAG}/${CHECKPOINT}" && \
    echo "b828a471fcb8d38e0b29d9c67eddec76c1428bc996cc0d4e5b10c026bf659d6f  runtime/model_assets/${CHECKPOINT}" \
      | sha256sum -c -

# Runs the integrity gate, loads the frozen model, encodes all 1,705 drugs once.
ENV PYTHONPATH=/build:/build/src
RUN python -m serving.precompute

# ------------------------------------------------------------- runtime stage
FROM python:3.11-slim AS runtime

WORKDIR /app
COPY serving/requirements-lean.txt serving/requirements-lean.txt
RUN pip install --no-cache-dir -r serving/requirements-lean.txt

# The whole package, not a hand-listed subset. Listing files individually is
# how serving/parity.py came to be missing from the image while api.py imported
# it — a 500 on every request that /api/health could not see. The directory is
# a few tens of KB; the artifact lives under runtime/ and is copied separately.
COPY serving/ serving/
COPY --from=build /build/runtime/model_assets/lean_decoder_v1.npz \
                  /build/runtime/model_assets/lean_decoder_v1.json \
                  /app/runtime/model_assets/

ENV PYTHONPATH=/app
ENV DDINET_ENGINE=lean
EXPOSE 8000

# $PORT is what Render and most PaaS hosts inject; 8000 is the local default.
CMD ["sh", "-c", "uvicorn serving.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
