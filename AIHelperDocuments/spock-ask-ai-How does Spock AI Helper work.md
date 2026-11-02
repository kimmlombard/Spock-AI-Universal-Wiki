# Spock Ask AI — 20260829-094531

## You

How does Spock AI Helper work?  Why is it used?  When can it be accessed?  What kind of questions is it designed to answer?

## Computer

Based on the provided context, here is how the Spock AI Helper works, why it is used, when it can be accessed, and what it is designed to answer:

### 1. How does Spock AI Helper work?
The Spock AI Helper operates as a multi-component suite launched via `helper_main.py`:
* **Background Docs Server:** It starts a background documentation server (`DocsServer`) serving a pre-built site (from the `site/` directory) and automatically opens a web browser to the documentation URL (`helper_main`).
* **PyQt6 GUI:** It launches a desktop GUI window (`ChatAIHelperWindow`) using PyQt6 (`helper_main`, `ai_helper`).
* **LLM Integration:** It connects to a Chat LLM client (such as a configured provider or a local `llama-server`) (`helper_main`, `ai_helper`).
* **Search & Embeddings:** It utilizes hybrid search (`hybrid_search`) and embeddings validation (`embeddings_endpoint_ok`) from the `WarpCore.search` module, querying against the ship's computer database (`SHIP_COMPUTER_DB`) (`ai_helper`).

### 2. Why is it used?
It is used as an interactive knowledge base assistant ("Spock-UIEG-KnowledgeBase") to help users navigate documentation and query information. Specifically, it provides a shared Chat AI Helper GUI interface over the `AIHelperDocuments/` directory and integrates local documentation search with an LLM to assist users (`helper_main`, `spock_uieg`).

### 3. When can it be accessed?
It can be accessed by running the suite entry point (`helper_main.py`) or its entry alias (`spock_uieg.py`). However, it has specific prerequisites to function properly (`helper_main`):
* A Chat LLM must be reachable (either a configured provider or an active `llama-server`).
* The documentation site must be pre-built in the `site/` directory (built using `mkdocs build`).

### 4. What kind of questions is it designed to answer?
While the context does not list specific topics, it indicates that the system is designed to answer questions based on:
* The **Spock-UIEG-KnowledgeBase** (`spock_uieg`).
* Documents located in the **`AIHelperDocuments/`** directory (`helper_main`).
* Data stored in the **`SHIP_COMPUTER_DB`** database (`ai_helper`).

## You

How does the Spock-AI-Helper answer questions using the AI Chat (8081) functionality?

## Computer

Based on the provided codebase corpus, the **Spock-AI-Helper** is a standalone, lightweight PyQt6 application designed to run with zero external dependencies (no `WarpCore` or `spock_shell` imports). It answers user questions by retrieving local Markdown documentation, constructing a context-rich prompt, and executing an asynchronous HTTP request to a local `llama-server` running on port **8081**.

Here is the detailed architectural breakdown, component analysis, and step-by-step call flow of how this functionality is implemented.

---

### 1. Key Components & File-Level Roles

The chat functionality is split across three primary files in the `D:\Spock-AI-Helper\` directory:

*   **`D:\Spock-AI-Helper\main.py`**: The application entry point. It instantiates the `LLMClient`, verifies connectivity to the chat server on port `8081`, and launches the PyQt6 GUI.
*   **`D:\Spock-AI-Helper\ai_helper.py`**: Implements the user interface (`AIHelperDialog`), local document keyword-ranking (RAG-lite), prompt construction, and the background thread (`_ChatWorker`) that prevents the GUI from freezing during LLM generation.
*   **`D:\Spock-AI-Helper\llm_client.py`**: A pure standard-library HTTP client that formats and transmits OpenAI-compatible chat completion payloads to `http://localhost:8081/v1/chat/completions`.

---

### 2. Step-by-Step Call Flow

#### Step 1: Initialization & Health Check
When `D:\Spock-AI-Helper\main.py` is executed, it instantiates `LLMClient` and calls `is_available()` to verify that a chat model is running on port `8081`:

```python
# D:\Spock-AI-Helper\main.py
client = LLMClient()
if client.is_available():
    print("LLM connected on :8081")
else:
    print("Warning: LLM not reachable on :8081")
```

The `LLMClient` checks this by sending a `GET` request to the `/health` endpoint:
```python
# D:\Spock-AI-Helper\llm_client.py
class LLMClient:
    _base_url: str = "http://localhost:8081"
    _chat_path: str = "/v1/chat/completions"
    _health_path: str = "/health"

    def is_available(self) -> bool:
        """True if llama-server responds on :8081/health."""
        try:
            req = urllib.request.Request(self.health_url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False
```

---

#### Step 2: Local Context Retrieval (RAG-lite)
When a user submits a query in the GUI, the application performs a local keyword search over Markdown files located in `D:\Spock-AI-Helper\AIHelperDocuments\` to find relevant context. 

1. **Term Extraction**: `_extract_terms(query)` tokenizes the query and filters out common stop words.
2. **Scoring**: `score_markdown_files(query)` reads each `.md` file, counts occurrences of the extracted terms, applies small boosts for specific filenames (e.g., files containing `"background"` or ending in `"-helper.md"`), and returns the top 5 highest-scoring snippets.

---

#### Step 3: Prompt Construction
The retrieved snippets are assembled into a structured system prompt using `build_system_prompt(query)` in `D:\Spock-AI-Helper\ai_helper.py`:

```python
# D:\Spock-AI-Helper\ai_helper.py
def build_system_prompt(query: str) -> str:
    docs = score_markdown_files(query)
    ...
    context_parts = []
    for d in docs:
        context_parts.append(f"--- {d['title']} ---\n{d['snippet']}")
    context = "\n\n".join(context_parts)

    return (
        "You are Spock AI Helper, an expert on the Spock-Onboarding "
        "local AI workstation management suite. Answer the user's question "
        "using ONLY the context below. Be concise and helpful. "
        "If the context doesn't contain the answer, say so.\n\n"
        f"CONTEXT:\n{context}"
    )
```

---

#### Step 4: Background Thread Execution (`_ChatWorker`)
To keep the PyQt6 user interface responsive, the actual network request is offloaded to a background thread using `_ChatWorker` (a subclass of `QThread`):

```python
# D:\Spock-AI-Helper\ai_helper.py
class _ChatWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, client: LLMClient, messages: List[Dict[str, str]]):
        super().__init__()
        self._client = client
        self._messages = messages

    def run(self):
        try:
            # Executes the blocking HTTP request in the background
            result = self._client.chat(self._messages, temperature=0.5, max_tokens=2048)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
```

---

#### Step 5: HTTP Communication with `llama-server` (:8081)
Inside the worker thread, `LLMClient.chat` formats the payload and transmits it to the local server using Python's standard library `urllib.request`:

```python
# D:\Spock-AI-Helper\llm_client.py
def chat(
    self,
    messages: List[Dict[str, str]],
    model: str = "local",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    stream: bool = False,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }).encode("utf-8")

    req = urllib.request.Request(
        self.chat_url,  # http://localhost:8081/v1/chat/completions
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        ...
        raise RuntimeError(...)

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned empty choices")
    return choices[0].get("message", {}).get("content", "")
```

---

#### Step 6: GUI Update
Once the background thread completes:
1. If successful, the `finished` signal is emitted with the assistant's response string.
2. The `AIHelperDialog` receives the signal, appends the response to the chat transcript, updates the internal conversation history, and re-enables the input fields for the next question.

## You

At any time, does the Spock-AI-Helper call the OpenAI Compatible 8090 model?

## Computer

Based on the provided codebase corpus, **no, the Spock-AI-Helper does not call an OpenAI Compatible model on port 8090.** 

Here is the technical breakdown of the ports and endpoints used by the application:

1. **LLM Client Port (`8081`):** 
   As defined in `D:\Spock-AI-Helper\llm_client.py`, the unified LLM client targets `localhost:8081` (the `llama-server` chat endpoint) rather than `8090`:
   ```python
   class LLMClient:
       """Unified LLM client targeting localhost:8081 (llama-server chat endpoint)."""

       _base_url: str = "http://localhost:8081"
       _chat_path: str = "/v1/chat/completions"
       _health_path: str = "/health"
   ```

2. **Connectivity Checks (`8081`):**
   In `D:\Spock-AI-Helper\main.py`, the application explicitly verifies connectivity on port `8081` and instructs the user to start `llama-server` via companion suites:
   ```python
   # 2. Check LLM connectivity
   client = LLMClient()
   if client.is_available():
       print("LLM connected on :8081")
   else:
       print("Warning: LLM not reachable on :8081")
       print("Start llama-server via Spock-Onboarding or Spock-Navigation.")
   ```

3. **Documentation Server Port (`8000`):**
   The only other port used by the helper is port `8000`, which is reserved for serving the local static MkDocs site via `D:\Spock-AI-Helper\docs_server.py`.

There are no references to port `8090` or any model configurations pointing to `8090` anywhere in the codebase.
