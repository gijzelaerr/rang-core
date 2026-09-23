# Separate legacy Numba environment: do not downgrade QuartiCal's solver.
FROM rang-flagging:local
COPY tools/flagging/comparators/requirements.lock /opt/rang/tricolour-requirements.lock
RUN python -m venv /opt/tricolour && /opt/tricolour/bin/python -m pip --isolated install \
    --no-cache-dir --index-url https://pypi.org/simple \
    -r /opt/rang/tricolour-requirements.lock
ENV RANG_TRICOLOUR_PYTHON=/opt/tricolour/bin/python
