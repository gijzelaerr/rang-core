# Build the base, sky and comparator images using their checked-in Dockerfiles.
# Distinct environments preserve QuartiCal's dependencies and each tool's ABI.
FROM rang-flagging-comparators:local AS comparators
FROM rang-flagging-sky:local
COPY --from=comparators /opt/tricolour /opt/tricolour
ENV RANG_TRICOLOUR_PYTHON=/opt/tricolour/bin/python
RUN python -m pip check && /opt/sky/bin/python -m pip check \
    && /opt/tricolour/bin/python -m pip check
