# Reuse the pinned, locally validated solver environment.
# Only the dependency-free Rust library is rebuilt for action-response kernels.
FROM rust:1.93-slim@sha256:c0a38f5662afdb298898da1d70b909af4bda4e0acff2dc52aea6360a9b9c6956 AS kernels
WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --offline --release --lib

FROM rang-flagging:local
COPY --from=kernels /build/target/release/librang_toy.so /opt/rang/librang_toy.so
# These response/replay recipes do not need Crystalball or Tricolour venvs.
RUN python -m pip check
