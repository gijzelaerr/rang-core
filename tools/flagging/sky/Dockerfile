# Build the pinned base using tools/flagging/Dockerfile first. Record its image
# identity alongside every run. Crystalball requires psutil>=6.1 whereas
# Stimela2.1.4 requires psutil<6: do not install them into the same environment.
FROM rang-flagging:local
COPY tools/flagging/sky/requirements.lock /opt/rang/sky-requirements.lock
RUN python -m venv /opt/sky \
    && sed '/^psutil==/d' /opt/rang/requirements.lock > /opt/sky/base-constraints.lock \
    && /opt/sky/bin/python -m pip --isolated install --no-cache-dir \
    --index-url https://pypi.org/simple -r /opt/rang/sky-requirements.lock \
    -c /opt/sky/base-constraints.lock --report /opt/sky/install-report.json \
    && /opt/sky/bin/python -m pip check \
    && /opt/sky/bin/python -m pip freeze > /opt/sky/requirements.lock \
    && python -m pip check
ENV RANG_SKY_PREDICTOR=/opt/sky/bin/crystalball
