# pydantic-ai MCP telemetry leak (GHSA-xv4x-g8mx-ch56)

Reproduces a security advisory patched in `pydantic-ai-slim` 2.58.0 / 1.107.8
(released 2026-10-19): a provider-native MCP connection's server URL,
authorization token, and custom header values could land in plaintext inside
an OpenTelemetry trace span, even with `include_content=False` set.

`include_content=False` is the setting someone reaches for specifically to
stop prompts, tool arguments, and tool responses from being recorded. It
works for that. It does not touch a second, separate attribute,
`model_request_parameters`, which dumps the full native-tool configuration,
credentials included, and is governed by its own flag
(`include_model_request_parameters`, default `True`) that most people
drafting an `include_content=False` config would never think to also set.

## The value proposition this maps to

Anyone running agents with provider-native MCP connectors (Anthropic, OpenAI
Responses, xAI) and exporting OpenTelemetry traces to a backend with broader
read access than the production secret store -- a shared observability
platform, a third-party APM vendor, a teammate with trace-viewer access but
not secrets-manager access -- had the MCP server's bearer token and any
custom auth headers sitting in that backend in plaintext, for every traced
request, regardless of `include_content`.

## Quickstart

```bash
git clone https://github.com/themsquared/pydantic-ai-mcp-telemetry-leak.git
cd pydantic-ai-mcp-telemetry-leak
./scripts/demo.sh
```

This builds two throwaway virtualenvs and runs the identical repro script
against both:

- `pydantic-ai-slim==2.56.0` (vulnerable)
- `pydantic-ai-slim==2.58.0` (fixed)

No network calls and no API key: a 15-line stub `Model` stands in for
Anthropic/OpenAI/xAI, because the leak lives in pydantic-ai's own
instrumentation layer (`pydantic_ai/_instrumentation.py`), which wraps every
provider identically. The stub just has to declare it supports
`MCPServerTool` as a native tool; the span is built the same way regardless
of what backend eventually receives the (never-sent, in this repro) request.

## What it shows

Against 2.56.0, the `model_request_parameters` span attribute, with
`include_content=False` set on the exact same span:

```json
{"native_tools":[{"kind":"mcp_server","id":"internal-billing-mcp",
  "url":"https://internal-mcp.example.com/mcp",
  "authorization_token":"sk-mcp-prod-SUPER-SECRET-TOKEN-abc123",
  "headers":{"X-Tenant-Key":"tenant-9f8e-SECRET"}}], ...}
```

Against 2.58.0, same script, same inputs:

```json
{"native_tools":[{"kind":"mcp_server","id":"internal-billing-mcp",
  "url":"[REDACTED]","authorization_token":"[REDACTED]",
  "headers":{"X-Tenant-Key":"[REDACTED]"}}], ...}
```

Meanwhile `gen_ai.input.messages` is correctly withheld (structure only, no
text) on both versions -- `include_content=False` was never broken for the
thing it's documented to cover. The fix specifically closes the second
attribute, the one that isn't gated by that flag.

## Architecture

```
scripts/repro_leak.py   # the repro, unmodified across both versions
scripts/demo.sh         # builds .venv-vuln (2.56.0) + .venv-fixed (2.58.0), runs both
```

No MCP server, no agent loop, no cluster. `InstrumentedModel.request()` is
called directly with a `ModelRequestParameters(native_tools=[MCPServerTool(...)])`
and an in-memory OTel span exporter, which is the minimum surface that
actually exercises the span-building code path responsible for the leak.

## Mitigation if you're on an affected version

Per the advisory: upgrade to 2.58.0 (or 1.107.8 on the 1.x line). If you
can't upgrade immediately, restrict access to historical traces and rotate
any credential that was ever passed through a provider-native MCP tool
config while instrumented.

## Related advisory in the same release

v2.58.0 also fixed GHSA-5pfm-2g3g-gh85: with non-empty server-side
`message_history` and `manage_system_prompt='server'` (the default), Vercel
AI and AG-UI adapters could execute an available tool with client-chosen
arguments without an actual model request. Not reproduced in this repo --
see the [advisory](https://github.com/pydantic/pydantic-ai/security/advisories/GHSA-5pfm-2g3g-gh85)
and the [release notes](https://github.com/pydantic/pydantic-ai/releases/tag/v2.58.0).

## Topics

`mcp` `ai-agents` `opentelemetry` `security` `pydantic-ai`
