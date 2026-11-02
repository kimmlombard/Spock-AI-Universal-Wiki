# Spock Ask AI — 20260831-130541

## You

Please give a detailed breakdown of Spock-Navigation-Station / 4 Configure Spock AI . Describe all options, and usage.

## Computer

Based on the provided codebase corpus, here is a detailed technical breakdown of **Step 4: Configure Spock AI** within the **Spock-Navigation-Station** suite.

---

### 1. Architectural Overview & Integration

Step 4, **Configure Spock AI**, is a consolidated, tabbed configuration panel designed to manage all LLM chat providers, RAG (Retrieval-Augmented Generation) settings, and MCP (Model Context Protocol) adapters in one place. 

* **Step Builder File**: `D:\Spock-Onboarding\NavigationStation\steps\configure.py`
* **UI Implementation File**: `D:\Spock-Onboarding\spock_shell\configure_ai.py`
* **Backend Configuration & LLM Client**: `D:\Spock-Onboarding\spock_shell\bridge_host.py`
* **Database Storage**: Settings are persisted to the SQLite database located at `SHIP_COMPUTER_DB` (`ship_computer.db`) via `WarpCore.settings_store`.

#### Integration Flow
In `NavigationStation/app.py`, the step is instantiated via `build_configure_step`:
```python
def build_configure_step(
    theme: Dict[str, str],
    config: Dict[str, Any],
    mcp_host: Any,
    on_profile_applied: Optional[Callable[[dict], None]] = None,
    on_rag_start: Optional[Callable[[], None]] = None,
    on_rag_stop: Optional[Callable[[], None]] = None,
    save_config: Optional[Callable[[], None]] = None,
) -> ConfigureAiPanel:
    return ConfigureAiPanel(
        theme,
        config,
        save_config or (lambda: None),
        db_path=SHIP_COMPUTER_DB,
        mcp_host=mcp_host,
        on_rag_start=on_rag_start,
        on_rag_stop=on_rag_stop,
        on_profile_applied=on_profile_applied,
    )
```
This panel replaces the scattered connection modals and one-off "test" buttons that previously existed across the legacy codebase.

---

### 2. Shared Tab Behavior (`_ConnectorTab`)

Every provider tab inherits from the base class `_ConnectorTab` in `spock_shell/configure_ai.py`. This ensures a uniform user experience across different backends:

* **Hint Text**: Displayed at the top of each tab to guide the user on provider-specific quirks (e.g., VRAM limits, context budgets).
* **Form Layout**: Standardized input fields for hostnames, ports, model IDs, and credentials.
* **Test Connection Button**: Triggers an asynchronous probe to verify if the endpoint is reachable and responding correctly.
* **Save & Use Button**: Persists the tab's settings to the configuration dictionary, writes them to `ship_computer.db`, and updates the global `ask_ai_provider` key to point to this active provider.
* **Color-Coded Status Label**:
  * **Green (`#4caf50`)**: Connection successful / Settings saved.
  * **Red (`#f44336`)**: Connection failed / Error details.
  * **Yellow/Orange (`#FFC107`)**: Testing connection / Busy.

---

### 3. Detailed Breakdown of Configuration Options

The `ConfigureAiPanel` contains tabs for each supported LLM provider, the RAG API, and the MCP host.

#### A. LM Studio Tab (`LmStudioTab`)
Designed to connect to a local instance of LM Studio running its OpenAI-compatible server.
* **Host**: The hostname or IP address of the LM Studio server (default: `localhost`).
* **Port**: The port number (default: `1234`).
* **Model ID**: The specific model identifier. If left blank, Spock defaults to whatever model LM Studio currently has loaded.
* **Load Context**: A spin box ranging from `512` to `262,144` (default: `32,768`). This setting is sent to LM Studio on load to override its multi-GPU clamp of `8,192`. *Tooltip warning: Use 32,768–65,536 on RTX 6000; avoid 262,144 unless VRAM is completely free.*
* **API Key (Optional)**: Password-masked field for secured LM Studio instances.

#### B. llama-server Tab
Configures connection details for the local `llama-server` instances spawned or attached during **Step 3: Launch**.
* **Host**: Typically `localhost` or `127.0.0.1`.
* **Port**: Defaults to `:8081` for chat completions (while `:8080` is reserved for embeddings).
* **Usage**: This is the default out-of-the-box provider for headless or local-only setups.

#### C. Ollama Tab
Configures connection details for a local or remote Ollama daemon.
* **Host**: Default is `localhost`.
* **Port**: Default is `11434`.
* **Model ID**: The exact model tag (e.g., `llama3`, `mistral`).

#### D. OpenAI-Compatible Tab
Allows connection to any standard OpenAI-compliant API gateway (e.g., self-hosted vLLM, LiteLLM, or commercial endpoints like OpenAI/Groq).
* **Base URL**: The target API endpoint (e.g., `https://api.openai.com/v1`).
* **API Key**: Secured token input.
* **Model ID**: Target model string.
* **Context Length (`n_ctx`)**: Default is `131,072`.
* **Max Tokens**: Default is `8,192`.

#### E. Embedding / RAG Tab
Manages the local Spock RAG API gateway, which coordinates vector search over the codebase.
* **RAG Host/Port**: Configures the local RAG API server (default: `127.0.0.1:8090`).
* **Embedding Profile**: Selects the active embedding model and its corresponding `/embeddings` endpoint (typically hosted on `llama-server` at port `8080`).
* **Start/Stop Controls**: Allows the user to spin up or shut down the background RAG API server (`_start_rag_api.py`).

#### F. MCP Tab
Configures the Spock Model Context Protocol adapter, allowing LLMs to execute local tools (such as searching the database, reading logs, or checking system health).
* **Transport**: Choice between `stdio` (for IDEs like Cursor/OpenCode) or `streamable-http` (for web-based clients).
* **HTTP Host/Port**: Default is `127.0.0.1:8765`.
* **CORS Settings**: Automatically configured to allow cross-origin requests from the local llama.cpp WebUI (typically running on `:8082`).

---

### 4. Usage & Workflow

```
[User Selects Step 4]
       │
       ▼
[ConfigureAiPanel Displays Tabs]
 ├── LM Studio
 ├── Ollama
 ├── llama-server
 ├── OpenAI-compatible
 ├── Embedding / RAG
 └── MCP
       │
       ├─► [User Edits Fields] ──► [Click "Test Connection"] ──► [Sends HTTP Probe]
       │                                                               │
       │                                                        (Green/Red Status)
       │
       └─► [Click "Save & Use"]
                 │
                 ▼
         [1. Persists to ship_computer.db]
         [2. Pins 'ask_ai_provider' to selected tab]
         [3. Re-configures global LLMClient class settings]
```

1. **Testing Connections**: Before saving, users click **Test connection**. The backend performs a lightweight HTTP request (e.g., querying `/v1/models` or `/health`) to ensure the target server is online.
2. **Saving Settings**: Clicking **Save & Use** triggers `apply_provider_config(cfg)` in `spock_shell/bridge_host.py`. This pushes the UI values into the class-level settings of `LLMClient`:
   ```python
   LLMClient.configure_lm_studio(host, port, model)
   LLMClient.configure_llama_server(host, port)
   # ... etc.
   ```
3. **Profile Integration**: Once configured, these settings can be saved as a named profile in the `spock_profile` table of `ship_computer.db` (via `spock_shell/profiles.py`). This allows users to quickly swap between different hardware profiles (e.g., "RTX-6000-Local-Llama", "Cloud-OpenAI-Fallback") without re-entering hostnames, ports, and API keys.

You

List, Define and give default values for each of the 7 configuration tabs in Spock-Navigation-Station / 4 Configure Spock AI

## Computer

Based on the codebase corpus, the **Configure Spock AI** step (Step 4 in the `Spock-Navigation-Station` app, built via `D:\Spock-Onboarding\NavigationStation\steps\configure.py`) is powered by the unified `ConfigureAiPanel` class defined in `D:\Spock-Onboarding\spock_shell\configure_ai.py`.

This panel consolidates all chat, RAG, and MCP backends into **7 configuration tabs**. Each tab manages its own settings, provides a "Test connection" probe, and saves its state to the `Spock_Console` table in `ship_computer.db` via `WarpCore.settings_store`.

Below is the list, definition, and default values for each of the 7 configuration tabs, sourced from `D:\Spock-Onboarding\WarpCore\config_defaults.py` and `D:\Spock-Onboarding\WarpCore\service_endpoints.py`.

* * *

### 1. LM Studio Tab

* **Definition**: Configures chat completions from a locally running LM Studio OpenAI-compatible server. It allows overriding LM Studio's multi-GPU context clamp.
* **Default Values**:
  * **Host** (`lm_studio_host`): `"localhost"`
  * **Port** (`lm_studio_port`): `1234`
  * **Model ID** (`lm_studio_model`): `""` *(blank defaults to whatever model LM Studio currently has loaded)*
  * **Load Context** (`lm_studio_context_length`): `32768` *(context length sent to LM Studio on load)*
  * **API Key** (`lm_studio_key`): `""` *(optional)*

### 2. Ollama Tab

* **Definition**: Configures chat completions from a local Ollama API instance.
* **Default Values**:
  * **Host** (`ollama_host`): `"localhost"`
  * **Port** (`ollama_port`): `11434`
  * **Model ID** (`ollama_model`): `""`

### 3. llama-server Tab

* **Definition**: Configures chat completions and context budgets for local `llama-server` instances spawned by the suite's process manager.
* **Default Values**:
  * **Host** (`llama_host`): `"localhost"`
  * **Chat Port** (`llama_port`): `8081` *(or `DEFAULT_CHAT_PORT`)*
  * **Embed Port** (`embed_port`): `8080` *(or `DEFAULT_EMBED_PORT`)*
  * **Docs Port** (`docs_port`): `8000` *(or `DEFAULT_DOCS_PORT`)*
  * **Embed Context** (`embed_n_ctx`): `8192`
  * **Chat Context** (`chat_n_ctx`): `8192`
  * **Chat Max Tokens** (`chat_max_tokens`): `2048`

### 4. OpenAI-compatible Tab

* **Definition**: Configures chat completions from any standard OpenAI-compatible cloud or local endpoint (e.g., OpenAI, Groq, OpenRouter, or Vertex Gemini via Application Default Credentials).
* **Default Values**:
  * **Base URL** (`openai_compat_base_url`): `""`
  * **API Key** (`openai_compat_api_key`): `""`
  * **Model ID** (`openai_compat_model`): `""`
  * **Context Length** (`openai_compat_n_ctx`): `131072`
  * **Max Tokens** (`openai_compat_max_tokens`): `13107`

### 5. Embedding Profile Tab

* **Definition**: Configures the local embedding model parameters used to vectorize documents for the RAG pipeline.
* **Default Values**:
  * **Embeddings URL** (`embeddings_url`): `"http://localhost:8080/embeddings"`
  * **Embeddings Dimension** (`embeddings_dim`): `4096`
  * **Truncate Chars** (`truncate_chars`): `1500`
  * **Batch Chunk** (`batch_chunk`): `32`
  * **Batch Workers** (`batch_workers`): `8`
  * **Llama Batch** (`llama_batch`): `512`
  * **Llama Ubatch** (`llama_ubatch`): `512`
  * **Model Path** (`model_path`): `""`
  * **Model ID** (`model_id`): `""`
  * **Probe on Apply** (`probe_on_apply`): `True`

### 6. RAG API Tab

* **Definition**: Configures the local Spock OpenAI-compatible RAG API gateway server, which serves as the bridge between the chat client and the vectorized knowledge base.
* **Default Values**:
  * **Enabled** (`enabled`): `False`
  * **Host** (`host`): `"127.0.0.1"`
  * **Port** (`port`): `8090` *(or `DEFAULT_RAG_PORT`)*
  * **API Key** (`api_key`): `""`

### 7. MCP (Model Context Protocol) & WebUI Tab

* **Definition**: Configures the Spock MCP adapter (which exposes system tools like `spock_health`, `spock_status`, and `spock_search_kb` to LLM clients) and the proxy settings for the llama.cpp WebUI.
* **Default Values**:
  * **Transport** (`transport`): `"streamable-http"` *(options: `"stdio"`, `"streamable-http"`, `"sse"`)*
  * **HTTP Host** (`http_host`): `"127.0.0.1"`
  * **HTTP Port** (`http_port`): `8765` *(or `DEFAULT_MCP_PORT`)*
  * **Llama Server Path** (`llama_server_path`): *Dynamically resolved path to the local `llama-server` executable*
  * **WebUI Host** (`webui_host`): `"127.0.0.1"`
  * **WebUI Port** (`webui_port`): `8082` *(or `DEFAULT_MCP_WEBUI_PORT`)*
  * **Adapter Autostart** (`adapter_autostart`): `False`
  * **WebUI Autostart** (`webui_autostart`): `False`