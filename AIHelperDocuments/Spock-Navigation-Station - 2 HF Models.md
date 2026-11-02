# Spock Ask AI — 20260831-125200

## You

Please give a detailed breakdown of Spock-Navigation-Station / 2 HF Models . Describe all options, and usage.

## Computer

The **"2 HF Models"** step in the **Spock-Navigation-Station** (implemented via the `ModelsPanel` class) serves as the central control deck for discovering, filtering, scanning, and downloading GGUF models. It bridges the gap between the hardware scanned in Step 1 and the server deployment in Step 3.

Below is a detailed technical breakdown of its options, underlying architecture, and usage workflows.

---

### 1. Architectural Overview & State Integration
The `ModelsPanel` is defined in `D:\Spock-Onboarding\model_selector_panels.py` and instantiated inside the main window of the Navigation Station (`D:\Spock-Onboarding\NavigationStation\app.py`). 

It relies on a shared, reactive state object:
* **State Class**: `ModelSelectorState` (defined in `model_selector_panels.py`).
* **Key State Fields Modified**:
  * `state.selected_hf_model_id`: The Hugging Face repository ID chosen by the user (e.g., `Qwen/Qwen3-8B-GGUF`).
  * `state.selected_gguf_path`: The absolute local path to a scanned GGUF file.
  * `state.model_data`: List of dictionaries containing metadata of models returned from Hugging Face Hub queries.

---

### 2. UI Options & Interactive Components

The panel is divided into three primary functional zones: **Hugging Face Hub Queries**, **Local GGUF Directory Scanning**, and the **Model Results Table**.

#### A. Hugging Face Hub Queries
To prevent UI lockups, queries are offloaded to a background thread (`HfQueryWorker`).
* **Query Chat/LLM Models (`query_btn`)**: Queries the Hugging Face Hub for text generation/chat GGUF models.
* **Query Embedding Models (`query_embed_btn`)**: Queries the Hugging Face Hub specifically for embedding models (e.g., `Qwen/Qwen3-Embedding-0.6B-GGUF`).
* **Hardware Dependency**: These buttons are disabled by default. They are only enabled (`_enable_hf_query_buttons()`) once `state.hardware_specs` is populated. If a user navigates directly to Step 2 without running Step 1, the application automatically triggers a background hardware scan:
  ```python
  # NavigationStation/app.py
  if not self.state.hardware_specs:
      hw = self._steps.get("hardware")
      panel = getattr(hw, "_panel", None) if hw else None
      if panel is not None:
          self._hw_scanned_once = True
          QTimer.singleShot(0, panel._start_scan)
  ```

#### B. Local GGUF Directory Scanning
Instead of downloading new models, users can scan existing local directories. The dropdown options are resolved via `get_model_directory_options()` in `D:\Spock-Onboarding\model_selector_core.py`:
* **All Sources**: Scans all known directories simultaneously.
* **Spock Models**: The application's internal model directory (`D:\Spock-Onboarding\models`).
* **LM Studio**: `~/.lmstudio/models`
* **Ollama**: `~/.ollama/models`
* **llamaccp**: The directory containing `llama-server.exe` (configured via `LLAMA_SERVER_PATH` or `config.json`).
* **LLM Fit**: `~/.local/share/llmfit/models` (or Windows equivalent).
* **HuggingFace Hub Cache**: `~/.cache/huggingface/hub`

#### C. The Model Results Table
Displays the discovered models (either from HF Hub or local scans).
* **Sorting**: Uses a custom `_SortableTableItem` (inheriting from `QTableWidgetItem`) to allow users to sort columns (such as file size in GB) numerically rather than alphabetically.
* **Selection**: Selecting a row updates the active state and enables action buttons.

---

### 3. Core Workflows & Usage

#### Workflow A: Querying and Downloading from Hugging Face
1. **Trigger Query**: The user clicks "Query HF Hub" or "Query Embed Models".
2. **Filtering**: The `HfQueryWorker` calls `query_hf_models(specs)` or `query_hf_embedding_models(specs)`. This logic filters models based on the scanned VRAM and RAM limits to prevent users from downloading models that will cause Out-Of-Memory (OOM) errors.
3. **Select Quantization**: When a repository is selected, the downloader resolves the best quantization file (preferring `Q4_K_M`, `Q5_K_M`, or `Q8_0` based on VRAM headroom).
4. **Download**:
   * The download is handled by `download_repo_gguf` (defined in `D:\Spock-Onboarding\spock_onboarding\pick.py`).
   * It uses the `huggingface_hub` library (`hf_hub_download` and `list_repo_files`).
   * **Authentication**: It automatically attempts to load a Hugging Face token via `get_hf_token()` (which checks `ship_computer.db` or `config.json`). If no token is found, it falls back to an anonymous download.

#### Workflow B: Inspecting Model Cards
1. **Request Info**: Double-clicking a model or clicking "View Info" fires the `request_show_info` signal.
2. **Transition**: The Navigation Station transitions the center stack to the `ModelInfoPanel` (`self._steps["model_info"]`).
3. **Fetch**: The panel calls `fetch_model_card(model_id)` to download and render the markdown README/Model Card directly inside the UI (using `QWebEngineView` if available, or falling back to a formatted `QTextEdit`).

#### Workflow C: Registering a Local GGUF
1. **Select Source**: The user selects a directory (e.g., "LM Studio") from the dropdown.
2. **Scan**: Clicking "Scan" invokes `scan_gguf_models_from_directory(selected_dir)`.
3. **Parse**: The system walks the directory tree, identifies files ending in `.gguf` (excluding multimodal projection files like `mmproj`), calculates their size in GB, and populates the table.
4. **Select**: Clicking a local GGUF binds its absolute path to `state.selected_gguf_path`, making it immediately available for launch in Step 3.
