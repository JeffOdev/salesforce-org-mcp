FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    npm \
    && npm install -g @salesforce/cli \
    && rm -rf /var/lib/apt/lists/*

COPY . /app
RUN pip --no-cache-dir install /app

WORKDIR /workdir

ARG USERID=nobody
ARG GROUPID=nogroup
USER $USERID:$GROUPID

ENTRYPOINT ["salesforce-org-mcp"]
