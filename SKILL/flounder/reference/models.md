# Choosing and configuring a model

Flounder discovers providers and models from its installed pi runtime. A provider
selects the service, endpoint, and credential identity; a model selects the model
on that service. Use the catalog exposed by your installation rather than guessing
provider names from model families. A model available through one provider is not
necessarily available through another.

## 1. Discover the provider and model

Open **Settings -> Providers -> New Provider**. Select the provider, then choose
its model and one of the offered thinking levels. The lists reflect the server's
installed pi catalog; keep the server and execution daemons on matching Flounder
and pi versions.

On the execution machine, list providers and their local credential status:

```sh
flounder daemon provider list
```

For programmatic model discovery, the running control plane exposes
`GET /api/pi/providers` and `GET /api/pi/models/<provider>`.

## 2. Configure credentials on the execution machine

The project runs on its selected daemon. Configure credentials there, even when
your browser and control-plane server run elsewhere. Provider profiles do not
store API keys.

### OAuth providers

For a provider that supports OAuth, run login and complete the displayed browser
or device-code flow. For example:

```sh
flounder daemon provider login openai-codex
flounder daemon provider check openai-codex
```

### API key providers

Supply the provider's required environment variable to the daemon process through
your shell or service manager's secret configuration. `login` does not currently
prompt for or save a new API key; without existing pi credentials, it explains
which environment variables to set. A subscription such as GLM Coding Plan can
also use an API key: subscription billing does not imply OAuth login.

Examples supported by the pinned pi catalog:

| Service | Provider | Daemon environment | Example model |
| --- | --- | --- | --- |
| DeepSeek official API | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` |
| GLM international Coding Plan | `zai` | `ZAI_API_KEY` | `glm-4.7` |
| GLM mainland China Coding Plan | `zai-coding-cn` | `ZAI_CODING_CN_API_KEY` | `glm-4.7` |

Choose a model available to your account. The GLM providers above use Coding Plan
endpoints in the pinned runtime. An ordinary metered API account may require a
different endpoint; changing the model ID does not change the endpoint. Do not
switch a customer's plan or invent a provider alias to resolve this distinction.

For example, after securely supplying `DEEPSEEK_API_KEY` in your shell, run:

```sh
flounder daemon provider check deepseek
flounder ui
```

`flounder ui` starts a co-located daemon by default. For a separate executor, start
`flounder daemon start --server <server-url> --token <daemon-token>` with the key
in that process's environment. Restart an existing daemon after changing its
environment. A successful check in a different shell does not update a running
daemon. Keep API keys out of chat messages, provider profiles, committed files,
and command output.

### Existing pi credentials

If the same provider already has credentials in pi's default agent auth file,
Flounder imports that entry into its daemon-local auth file on `login` or `check`.
This applies to stored API keys as well as OAuth credentials. Stored Flounder
credentials take precedence over environment keys; if an old key keeps being
used, update the daemon-local credential entry securely.

## 3. Check configuration, then assign the profile

Run `flounder daemon provider check <provider>` on the selected executor. A failed
check gives login or environment guidance. A passing check verifies credential
presence, not validity, model entitlement, quota, or a successful remote request.

Save the provider profile in **Settings -> Providers**. Select that profile and
the intended daemon on the project. Check any per-phase overrides too: each
provider used by prepare, map, dig, or confirm needs credentials on the executor.

Run the intended audit and inspect its activity for provider errors. If you only
want to validate access, use a small authorized local fixture and explicitly
bounded coverage/model turns; starting a normal audit can consume paid usage.
Report credential checks and actual model-call results separately.

## 4. If the desired model is missing

- **Known provider, missing model ID:** In Settings -> Providers, enter the exact
  model ID and select a known same-provider **Compatibility base**. Use this only
  when the new model shares the base's API, tools, context limits, and reasoning
  behavior. The custom ID travels with the job to the daemon. This does not add
  account access or change the endpoint.
- **Missing provider or incompatible protocol:** Check whether a newer supported
  pi runtime includes it. A daemon-local pi `models.json` entry alone is not a
  supported way to register a new provider in Flounder's control-plane catalog.
  Custom profile IDs only extend known providers; do not promise arbitrary
  endpoint support through this feature.
- **Catalog entry exists but calls fail:** Check daemon credentials, account/model
  access, service region, endpoint/plan, quota, and the provider's reported error.
  Avoid changing audit prompts or adding model adapters to fix authentication.

When pi already supplies the provider, transport, and compatible model metadata,
Flounder does not need a vendor-specific adapter. New pi catalog support may still
require upgrading the installed runtime; it is not fetched automatically online.
