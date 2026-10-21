# Checks

Use Linux. Checks need no model credentials and make no external requests.
Runners live in `scripts/`; test cases and assertions live in `tests/`.

```sh
# Offline boundary regressions; no Web assets or live providers are required.
npm --prefix runtime/pi ci
node --test tests/pi/*.test.mjs tests/pi-packaging.test.mjs
go test -mod=readonly -timeout=60s ./tests/...

# Existing binary: CLI, health, embedded assets and SQLite persistence.
bash scripts/test.sh "$(pwd)/bin/pwnmesh"

# Default image build includes frontend type checks, Go build/vet and binary checks.
docker build -t pwnmesh:check .
bash scripts/test-docker.sh pwnmesh:check
docker image rm pwnmesh:check

# Existing Worker image: separate from the default CI job.
docker run --rm --pull never --network none --init \
  --mount "type=bind,source=$(pwd)/tests/worker,target=/checks,readonly" \
  --entrypoint timeout pwnmesh-worker:dev 60 sh /checks/check.sh
```

CI builds the default application image once, runs `scripts/test-docker.sh`, then removes it.
Image checks remove their temporary containers, including on failure. Dependency
installation during image builds needs network access; validation runs offline.
The full Kali Worker build and live-model tests are outside default CI.
