import os
import requests

from observability import langfuse

MCP_URL = os.getenv("MCP_URL")


def _build_base_request(method):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }


def _build_base_headers():
    return {
        "Accept": "application/json",
    }


def _create_llm_tool_definition(mcp_tool):
    return {
        "type": "function",
        "function": mcp_tool,
    }


def list_tools():
    with langfuse.start_as_current_observation(as_type="tool", name="list-tools") as tool:
        r = requests.post(
            f"{MCP_URL}",
            headers=_build_base_headers(),
            json=_build_base_request("tools/list"),
            timeout=5,
        )
        r.raise_for_status()
        result = [_create_llm_tool_definition(t) for t in r.json()["result"]["tools"]]
        tool.update(output=result)
        return result


def call_tool(name, arguments):
    with langfuse.start_as_current_observation(as_type="tool", name="call-tool") as tool:
        tool.update(input={"name": name, "arguments": arguments})
        payload = _build_base_request("tools/call")
        payload["params"] = {
            "name": name,
            "arguments": arguments,
        }
        r = requests.post(
            f"{MCP_URL}",
            headers=_build_base_headers(),
            json=payload,
            timeout=5,
        )
        r.raise_for_status()
        result = r.json()["result"]
        tool.update(output=result)
        return result
