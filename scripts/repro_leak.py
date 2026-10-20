"""Reproduce GHSA-xv4x-g8mx-ch56: provider-native MCP config leaking into OTel
traces through pydantic-ai's `model_request_parameters` span attribute, even
when `include_content=False` is set.

No network, no API key: a stub Model stands in for Anthropic/OpenAI/xAI,
because the leak lives in pydantic-ai's own instrumentation layer, which
wraps every provider identically, not in any one provider's SDK.

Run this unmodified against pydantic-ai-slim==2.56.0 (vulnerable) and
pydantic-ai-slim==2.58.0 (fixed) -- see scripts/demo.sh.
"""

import asyncio
import json
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.instrumented import InstrumentationSettings, InstrumentedModel
from pydantic_ai.native_tools import MCPServerTool
from pydantic_ai.usage import RequestUsage

exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)


class StubModel(Model):
    """Smallest possible Model: returns a canned response, no network, no API key."""

    async def request(self, messages, model_settings, model_request_parameters):
        return ModelResponse(
            parts=[TextPart(content="ok")],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
            model_name="stub",
            timestamp=datetime.now(timezone.utc),
        )

    @property
    def model_name(self) -> str:
        return "stub"

    @property
    def system(self) -> str:
        return "stub"

    @classmethod
    def supported_native_tools(cls):
        return frozenset({MCPServerTool})


SECRET_TOKEN = "sk-mcp-prod-SUPER-SECRET-TOKEN-abc123"

mcp_tool = MCPServerTool(
    id="internal-billing-mcp",
    url="https://internal-mcp.example.com/mcp",
    authorization_token=SECRET_TOKEN,
    headers={"X-Tenant-Key": "tenant-9f8e-SECRET"},
)

# The setting someone reaches for specifically to stop prompts, tool args,
# and tool responses from landing in traces.
settings = InstrumentationSettings(include_content=False)
model = InstrumentedModel(StubModel(), settings)

params = ModelRequestParameters(native_tools=[mcp_tool])
messages: list[ModelMessage] = [ModelRequest(parts=[UserPromptPart(content="hello")])]

asyncio.run(model.request(messages, None, params))

spans = exporter.get_finished_spans()
span = spans[0]
attrs = dict(span.attributes or {})
mrp = attrs.get("model_request_parameters", "<missing>")

print(f"pydantic-ai version check: see 'pip show pydantic-ai-slim'")
print(f"captured {len(spans)} span(s); include_content=False on this one\n")
print("model_request_parameters span attribute:")
print(f"  {mrp}\n")

if SECRET_TOKEN in json.dumps(attrs):
    print(f"LEAKED: authorization_token and headers appear in plaintext above.")
else:
    print(f"REDACTED: authorization_token and headers do not appear in plaintext.")

print(f"\nFor comparison, prompt content IS correctly withheld on this span:")
print(f"  gen_ai.input.messages = {attrs.get('gen_ai.input.messages')}")
