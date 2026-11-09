# E1's Tricolour 0.2.1 oracle (research/e1-chain.md). The pinned base and the
# lock of history/tools/flagging/comparators (the same /opt/tricolour venv as
# rang-flagging-comparators:local), without the retired Rust kernel stage,
# which Tricolour does not use. Build context: history/tools/flagging/comparators.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY requirements.lock /opt/rang/tricolour-requirements.lock
RUN python -m venv /opt/tricolour && /opt/tricolour/bin/python -m pip --isolated install \
    --no-cache-dir --index-url https://pypi.org/simple \
    -r /opt/rang/tricolour-requirements.lock && /opt/tricolour/bin/python -m pip check
ENV NUMBA_CACHE_DIR=/tmp/numba OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PATH=/opt/tricolour/bin:$PATH
WORKDIR /work
