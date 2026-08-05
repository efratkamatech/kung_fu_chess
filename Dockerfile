# The Kung Fu Chess server, headless.
#
# Two stages: the first builds a virtualenv with the dependencies in it, the second
# copies only that venv and the source into a clean image, so pip, its cache, and any
# build tooling never reach the thing that runs. The graphics extra is deliberately NOT
# installed -- the server never imports cv2, and pulling OpenCV in would multiply the
# image size for code that is never executed here.

FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Extra trust anchors, if this machine's network inspects TLS: a filtering service or a
# corporate proxy re-signs every connection with its own authority, which the host
# trusts and a fresh container has never heard of, so pip cannot verify pypi.org. Any
# .crt dropped in certs/ is trusted for the build; an empty directory changes nothing.
# See certs/README.md. PIP_CERT points pip at the system bundle, because pip verifies
# against its own bundled one otherwise and would not see the addition.
COPY certs/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# The install is editable, so the venv records a path back to /app/src rather than
# copying the package in. That means the source has to live at the same path in the
# runtime stage as it did here -- which it does, both are /app.
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /venv && /venv/bin/pip install -e ".[server]"


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/venv/bin:$PATH"

# A non-root user owning /app: the server writes its log beside the source (config
# SERVER_LOG), so the directory has to be writable by whoever runs.
RUN useradd --create-home --uid 10001 kfchess

WORKDIR /app

COPY --from=build /venv /venv
COPY --from=build /app /app
# Only the starting position. The other 11 MB of assets/ -- the board image and every
# piece sprite -- belong to the graphics front-ends, which this image deliberately
# cannot run; config resolves them lazily, so their absence is never noticed.
COPY assets/board.csv ./assets/board.csv
COPY server_main.py gateway_main.py auth_main.py ./

RUN chown -R kfchess:kfchess /app
USER kfchess

# The WebSocket port. config.SERVER_HOST must be 0.0.0.0 for this to be reachable from
# outside the container -- docker-compose.yml sets KFC_SERVER_HOST to do that.
EXPOSE 8765

# Which process this image runs is chosen by compose: the shard (server_main.py), a
# gateway (gateway_main.py), or auth (auth_main.py). One image, three roles -- they
# share every line of code that is not the entry point.
CMD ["python", "server_main.py"]
