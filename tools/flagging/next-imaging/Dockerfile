# Keep the signed-package build and original solver image intact. Apply the
# final checked native kernel independently, without repeating any downloads.
FROM rang-flagging-imaging:local
COPY --from=rang-flagging-next:local /opt/rang/librang_toy.so /opt/rang/librang_toy.so
ENV RANG_TOY_LIB=/opt/rang/librang_toy.so
