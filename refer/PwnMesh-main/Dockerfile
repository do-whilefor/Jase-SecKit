FROM node:22-bookworm AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN --network=none npm run build

FROM node:24-bookworm-slim AS pi-runtime
WORKDIR /opt/pwnmesh/runtime/pi
COPY runtime/pi/package.json runtime/pi/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund
COPY runtime/pi/ ./
RUN --network=none node kernel.mjs --check

FROM pi-runtime AS pi-package
RUN rm -f sync-source.mjs package-lock.json

FROM golang:1.26-bookworm AS source
RUN apt-get update && apt-get install -y --no-install-recommends python3 ripgrep \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
# Test and documentation edits must not invalidate the application build.
COPY cmd/ ./cmd/
COPY internal/ ./internal/
COPY scripts/build.sh scripts/common.sh scripts/package-pi.mjs ./scripts/
COPY --from=pi-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=pi-runtime /opt/pwnmesh/runtime/pi ./runtime/pi

FROM source AS backend-build
RUN --network=none PWNMESH_HEADLESS=1 bash scripts/build.sh /out/pwnmesh

FROM backend-build AS backend-test
COPY tests/ ./tests/
COPY dispatch.example.yaml ./
COPY scripts/test.sh ./scripts/test.sh
RUN --network=none go vet -mod=readonly -tags=headless ./cmd/... ./internal/... \
    && go test -mod=readonly -timeout=60s ./tests/... \
    && node --test tests/pi/*.test.mjs tests/pi-packaging.test.mjs \
    && PWNMESH_TEST_HEADLESS=1 bash scripts/test.sh /out/pwnmesh

FROM source AS build
COPY web/embed.go ./web/embed.go
COPY --from=web-build /web/dist ./web/dist
RUN --network=none PWNMESH_WEB_PREBUILT=1 bash scripts/build.sh /out/pwnmesh

FROM build AS test
COPY tests/ ./tests/
COPY dispatch.example.yaml ./
COPY scripts/test.sh ./scripts/test.sh
# CI builds this same target through the default runtime image.
RUN --network=none go vet -mod=readonly ./cmd/... ./internal/... ./web \
    && go test -mod=readonly -timeout=60s ./tests/... \
    && node --test tests/pi/*.test.mjs tests/pi-packaging.test.mjs \
    && bash scripts/test.sh /out/pwnmesh

FROM node:24-bookworm-slim AS runtime-base
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl bash ripgrep \
    && rm -rf /var/lib/apt/lists/*
COPY --from=pi-package /opt/pwnmesh/runtime/pi /opt/pwnmesh/runtime/pi
ENV PWNMESH_PI_RUNTIME=/opt/pwnmesh/runtime/pi/kernel.mjs
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/pwnmesh"]
CMD ["serve", "--host", "0.0.0.0", "--db-path", "/data/pwnmesh.db"]

# Explicit opt-in for development; the default final target retains validation.
FROM runtime-base AS development
COPY --from=build /out/pwnmesh /usr/local/bin/pwnmesh

# API, Dispatcher and Worker without the Web build dependency.
FROM runtime-base AS headless
COPY --from=backend-test /out/pwnmesh /usr/local/bin/pwnmesh

FROM runtime-base AS runtime
COPY --from=test /out/pwnmesh /usr/local/bin/pwnmesh
