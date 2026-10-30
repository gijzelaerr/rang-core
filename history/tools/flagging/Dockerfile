FROM rust:1.93-slim@sha256:c0a38f5662afdb298898da1d70b909af4bda4e0acff2dc52aea6360a9b9c6956 AS kernels
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --offline --release --lib

FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
# Use public PyPI explicitly, including the pinned transitive dependencies.
COPY tools/flagging/requirements.lock /opt/rang/requirements.lock
RUN python -m pip --isolated install --no-cache-dir --index-url https://pypi.org/simple \
    -r /opt/rang/requirements.lock
COPY --from=kernels /build/target/release/librang_toy.so /opt/rang/librang_toy.so
ENV PYTHONPATH=/workspace/python RANG_TOY_LIB=/opt/rang/librang_toy.so \
    NUMBA_CACHE_DIR=/tmp/numba MPLCONFIGDIR=/tmp/matplotlib \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /workspace
ENTRYPOINT ["stimela"]
