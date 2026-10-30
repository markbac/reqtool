# reqtool server image (#367): the shared server, login required, serving the requirements repository in /repo.
#
#   docker build -t reqtool .
#   docker compose up -d            # see docker-compose.yml and scripts/docker.ps1

# The web UI, built as release.yml builds it, so the Python package below includes it.
FROM node:20-slim AS ui
WORKDIR /ui
COPY src/reqtool/ui/package.json src/reqtool/ui/package-lock.json ./
RUN npm ci
COPY src/reqtool/ui/ ./
RUN npm run build

FROM python:3.13-slim

# git: the ctxlogkit dependency is installed from git, and reqtool commits, tags and syncs with it.
# openssh-client: sync with an ssh:// or scp-style remote.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The user the server runs as. Match the owner of a host folder mounted at /repo with --build-arg UID=... GID=...
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" reqtool \
    && useradd --uid "${UID}" --gid "${GID}" --create-home --shell /bin/bash reqtool \
    && mkdir /repo && chown reqtool:reqtool /repo \
    # A mounted folder can belong to another user; git refuses to work in it unless it is named as safe.
    && git config --system safe.directory /repo

WORKDIR /opt/reqtool
COPY . .
COPY --from=ui /ui/dist src/reqtool/ui/dist
RUN pip install --no-cache-dir . && rm -rf /opt/reqtool

ENV REQTOOL_REPO=/repo \
    REQTOOL_MODE=server \
    REQTOOL_AUTH=required \
    REQTOOL_DISABLE_REPO_SWITCH=1 \
    PYTHONUNBUFFERED=1

USER reqtool
WORKDIR /repo
VOLUME ["/repo"]
EXPOSE 8765

# /health needs no login.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4)" || exit 1

CMD ["req", "serve", "--repo", "/repo", "--host", "0.0.0.0", "--port", "8765", "--mode", "server", "--auth", "required"]
