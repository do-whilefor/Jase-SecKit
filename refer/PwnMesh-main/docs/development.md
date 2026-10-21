# PwnMesh development

Use Linux, Go 1.26, Node 22.19+, Python 3.11+ and ripgrep. Install dependencies before
running offline checks; no model credentials are needed.

## Local build and checks

```sh
go mod download
go mod verify
npm --prefix web ci
npm --prefix runtime/pi ci
bash scripts/build.sh
node --test tests/pi/*.test.mjs tests/pi-packaging.test.mjs
go vet -mod=readonly ./cmd/... ./internal/... ./web
go test -mod=readonly -timeout=60s ./tests/...
bash scripts/test.sh "$(pwd)/bin/pwnmesh"
```

`build.sh [output]` embeds the built frontend in `bin/pwnmesh` by default.
`PWNMESH_WEB_PREBUILT=1` reuses existing assets without checking freshness.
`PWNMESH_HEADLESS=1 bash scripts/build.sh bin/pwnmesh-headless` skips Web assets.
Workers still require Node and the packaged `runtime/pi/` directory beside the binary.
Test it with `PWNMESH_TEST_HEADLESS=1 bash scripts/test.sh PATH`.
The Docker `headless` target includes the same offline boundary and binary checks.
The [test runner](../tests/README.md) clears model and acceptance settings and
uses existing build outputs.

## Docker and CI

```sh
docker build -t pwnmesh:dev .
bash scripts/test-docker.sh pwnmesh:dev
```

The default image and CI share frontend build/type checks, Go vet, boundary and
application smoke tests. Checks run without network access; CI caches build layers
and checks final-image startup and shutdown. The `development` target skips application
test gates; use the default target before publishing.
Worker builds have separate offline checks and are outside default CI.
See [container instructions](../container/README.md) for Worker builds and validation.

Pi source provenance and hashes are in `runtime/pi/upstream/provenance.json`.
`node runtime/pi/sync-source.mjs --check` verifies the retained source.
Deployed runtimes omit the source maintenance script and npm install lockfile.

Set `PWNMESH_OPENAI_REASONING_CONTENT=true` in the Worker's model environment only
for OpenAI-compatible endpoints requiring same-model `reasoning_content` replay.

For UI development, run `npm --prefix web run dev` with the server on port 8000.
Keep trusted-host and same-origin write checks enabled for remote access.

Set the same `PWNMESH_CONTROL_TOKEN` (generate with `openssl rand -hex 32`) in
Server and Dispatcher environments. Compose reads it from ignored `.env`.
`model_settings_source: server` uses this channel; `file` explicitly retains
local settings and credential access. Neither token belongs in Worker settings.
