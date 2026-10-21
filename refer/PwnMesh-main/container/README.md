# PwnMesh containers

## Build and validate

Build from the repository root, application first. The full Worker image targets
Linux amd64 and includes Kali headless tools, Python packages and Chromium:

```sh
docker build -t pwnmesh:dev .
docker build -f container/Dockerfile -t pwnmesh-worker:dev .
```

The default application build runs Go vet and application smoke checks. For local
iteration after focused checks, `docker build --target development -t pwnmesh:dev .`
skips those gates; frontend build/type checks still run. Use the default target
before publishing. See [development](../docs/development.md) for Docker and CI checks.

Worker builds run [offline acceptance checks](../tests/worker/check.sh) for tools,
HTTP replay, Chromium and the CLI. Checks are mounted during the build and are
not shipped. To validate an existing image without pulling or network access:

```sh
docker run --rm --pull never --network none --init \
  --mount "type=bind,source=$(pwd)/tests/worker,target=/checks,readonly" \
  --entrypoint timeout pwnmesh-worker:dev 180 sh /checks/check.sh
```

Playwright CLI is pinned by `PLAYWRIGHT_CLI_VERSION`; validate the CLI and browser
before overriding it with `--build-arg`.

## Data and ownership

The server accepts an empty database or complete SQLite schema `4`; older schemas
are rejected without automatic migration. Before changing binaries, stop Server
and Dispatcher and back up SQLite consistently with workspace volumes, journals,
evidence and receipts. Preserve installation identity and a pre-upgrade backup.
See [supported formats](../docs/formats.md) and [recovery](../docs/recovery.md).

Worker ownership combines the database's installation ID, dispatcher namespace
and project ID. Only one dispatcher may be active per installation. Its namespace
binding survives lease expiry; changing it requires deliberate migration. Another
database cannot adopt or clean up these containers. Do not run a restored clone
independently on the same Docker daemon and namespace.

New Workers persist `/workspace` in a named volume, reused by later rounds.
`completed_action: remove` removes the container but preserves that volume;
project deletion removes it once unused. Volumes bind the image ID, network and
capabilities, so changing that runtime requires deliberate migration.

Owned containers without a workspace volume are stopped and preserved by
`completed_action: remove`; explicit project deletion still removes them. Legacy
`<namespace>-dispatch-<project>` containers block replacement creation. Back up
their `/workspace` before migrating. Unknown ownership or unexpected mounts are
rejected; PwnMesh does not automatically adopt or migrate these workspaces.

Compose shares `/data/model-settings.json` between Server and Dispatcher. Native
`serve` and `dispatch` use `$HOME/.local/share/pwnmesh/model-settings.json`:
run them under the same user or set the same absolute `PWNMESH_MODEL_CONFIG_PATH`.
If `serve` finds a database-adjacent legacy settings file elsewhere, it preserves
the file and requires that explicit setting before startup.
