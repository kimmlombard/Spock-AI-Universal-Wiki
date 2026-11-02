# Spock Ask AI — Deep Dive

## Conversation

### You

[Deep Dive] using the Spock python app, can I access mcp 'tools' from here?

### Computer

Yes, you can access the Spock MCP (Model Context Protocol) tools. Depending on your use case, you can access them **directly in-process via Python** or **externally via the MCP server adapter**.

Here is a technical breakdown of how to access these tools using both methods.

---

### Method 1: Accessing Tools Directly In-Process (Python Code)
If you are writing Python code within the Spock application suite, you do not need to run a background server process to use the tools. You can dynamically load the MCP module and invoke the underlying functions directly. 

This approach is actively used by the **Engineering Deck** in `D:\Spock-Onboarding\EngineeringDeck\ship_computer_health.py` to run diagnostics without PyQt6 GUI overhead.

#### How it works:
Because the tools are registered using `fastmcp`, they are wrapped as `FunctionTool` objects. To call them, you access their underlying Python function via the `.fn` attribute.

Here is the implementation pattern from `ship_computer_health.py`:

```python
import importlib.util
import sys
from pathlib import Path
from typing import Any

# 1. Resolve the path to the MCP server script
ROOT = Path(r"D:\Spock-Onboarding")
mcp_script_path = ROOT / "scripts" / "mcp_spock_server.py"

def load_mcp_tools():
    """Dynamically load the MCP server module without requiring a package install."""
    spec = importlib.util.spec_from_file_location("mcp_spock_server_tools", mcp_script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {mcp_script_path}")
    
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mcp_spock_server_tools"] = mod
    spec.loader.exec_module(mod)
    return mod

def call_mcp_tool(tool_name: str, **kwargs: Any) -> Any:
    """Invoke an MCP tool function directly."""
    mod = load_mcp_tools()
    tool = getattr(mod, tool_name, None)
    if tool is None:
        raise AttributeError(f"MCP tool not found: {tool_name}")
    
    # FastMCP wraps functions; extract the raw callable via '.fn'
    fn = getattr(tool, "fn", None)
    if callable(fn):
        return fn(**kwargs) if kwargs else fn()
    if callable(tool):
        return tool(**kwargs) if kwargs else tool()
    raise TypeError(f"Tool {tool_name} is not callable")

# Example: Call the spock_health tool directly
health_data = call_mcp_tool("spock_health")
print(health_data)
```

---

### Method 2: Accessing Tools Externally (MCP Server)
If you want an external LLM client (like **Cursor**, **OpenCode**, or **llama.cpp WebUI**) to access these tools, you can run the MCP adapter as a background process. 

The server is defined in `D:\Spock-Onboarding\scripts\mcp_spock_server.py` and supports three transports (configured via the `SPOCK_MCP_TRANSPORT` environment variable):

1. **`stdio` (Default):** Used by IDEs like Cursor. The IDE spawns the Python process directly.
2. **`streamable-http`:** Exposes a WebUI-compatible endpoint (usually at `http://127.0.0.1:8765/mcp`).
3. **`sse`:** Legacy Server-Sent Events endpoint.

#### 1. Connecting via Cursor / OpenCode (`stdio`)
Add the following configuration to your global `mcp.json` file (usually located in `%APPDATA%\Cursor\User\globalStorage\moose.geometry-reader\mcp.json` or similar IDE config paths):

```json
{
  "mcpServers": {
    "spock": {
      "command": "D:/Spock-Onboarding/.venv/Scripts/python.exe",
      "args": [
        "-u",
        "D:/Spock-Onboarding/scripts/mcp_spock_server.py"
      ]
    }
  }
}
```

#### 2. Connecting via llama.cpp WebUI (`streamable-http`)
1. Start the HTTP adapter from the Spock UI (**Navigation Station** -> **Configure Spock AI** -> **MCP** tab) or run it standalone using `D:\Spock-Onboarding\spock_mcp_adapter\__main__.py`.
2. In the llama.cpp WebUI, add the server URL:
   ```text
   http://127.0.0.1:8765/mcp
   ```

