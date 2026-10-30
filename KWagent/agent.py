"""Interactive CLI agent that queries a Fabric ontology via its MCP endpoint.

Uses agent-framework's Foundry chat client and the Fabric ontology endpoint
surfaced as a local MCP streamable-HTTP tool.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Optional

from dotenv import load_dotenv

from azure.identity.aio import AzureCliCredential
from httpx import AsyncClient

from agent_framework import MCPStreamableHTTPTool, AgentSession
from agent_framework.foundry import FoundryChatClient


FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

SYSTEM_PROMPT = (
    "You are an assistant that answers questions about a Microsoft Fabric "
    "ontology. Always use the Fabric ontology MCP tools to discover the "
    "schema (classes, properties, relationships) and to query the data "
    "before answering. Cite the entities and properties you used. If a "
    "question is ambiguous, ask a brief clarifying question."
)


async def _normalize_notification_responses(response) -> None:
    # The Fabric ontology MCP server replies with a body like
    # {"id": "...", "jsonrpc": "2.0"} (missing result/error), which violates
    # JSON-RPC and crashes the MCP client's pydantic validation. Patch any
    # such body to include an empty `result` so it parses as a valid
    # JSONRPCResponse. The client is robust to extra/empty fields.
    if response.status_code != 200:
        return
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return
    body = await response.aread()
    try:
        obj = json.loads(body)
    except Exception:
        return
    if not isinstance(obj, dict):
        return
    if "method" in obj or "result" in obj or "error" in obj:
        return
    if "id" not in obj:
        return
    obj["result"] = {}
    new_body = json.dumps(obj).encode("utf-8")
    response._content = new_body
    if "content-length" in response.headers:
        response.headers["content-length"] = str(len(new_body))


async def _get_fabric_token(credential: AzureCliCredential) -> str:
    token = await credential.get_token(FABRIC_SCOPE)
    return token.token


async def run() -> None:
    load_dotenv()

    project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
    model_deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    mcp_url = os.environ["FABRIC_ONTOLOGY_MCP_URL"]
    tenant_id: Optional[str] = os.environ.get("AZURE_TENANT_ID") or None

    cred_kwargs = {"tenant_id": tenant_id} if tenant_id else {}

    # One credential is reused for both Foundry and Fabric scopes.
    # Requires `az login` (run once interactively).
    async with AzureCliCredential(**cred_kwargs) as credential:
        fabric_token = (await credential.get_token(FABRIC_SCOPE)).token

        # Bake the bearer token into an httpx client so it's sent on the
        # initial MCP `initialize` handshake (header_provider only fires on
        # tool calls, not on connect).
        async with AsyncClient(
            headers={"Authorization": f"Bearer {fabric_token}"},
            follow_redirects=True,
            timeout=60.0,
            event_hooks={"response": [_normalize_notification_responses]},
        ) as http_client:
            async with MCPStreamableHTTPTool(
                name="fabric_ontology",
                url=mcp_url,
                http_client=http_client,
            ) as ontology_tool:
                chat_client = FoundryChatClient(
                    project_endpoint=project_endpoint,
                    model=model_deployment,
                    credential=credential,
                )
                agent = chat_client.as_agent(
                    name="fabric-ontology-agent",
                    instructions=SYSTEM_PROMPT,
                    tools=[ontology_tool],
                )

                print("Fabric Ontology Agent. Type 'exit' to quit.\n")

                thread = AgentSession()

                while True:
                    try:
                        question = input("KW Agent> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        break

                    if question.lower() in {"exit", "quit"}:
                        break
                    if not question:
                        continue

                    try:
                        result = await agent.run(question, session=thread)
                    except Exception as ex:  # noqa: BLE001
                        print(f"[error] {ex}", file=sys.stderr)
                        continue

                    print(f"\nagent> {result}\n")


if __name__ == "__main__":
    asyncio.run(run())
