# Spock Ask AI — 20260831-130214

## You

Please give a detailed breakdown of Spock-Navigation-Station / 1 Hardware . Describe all options, and usage.

## Computer

Based on the retrieved codebase corpus, here is a detailed technical breakdown of the **Spock-Navigation-Station**'s first step: **1 Hardware**.

---

### 1. Architectural Overview & Call Flow

The **1 Hardware** step is the foundational phase of the Spock onboarding and model configuration pipeline. Its primary purpose is to inventory the host machine's physical resources (CPU, RAM, and NVIDIA GPUs) and write these specifications to a shared state object. This state is then used by downstream steps to filter Hugging Face models, calculate context window allocations, and configure GPU offloading.

#### Call Flow:
1. **Initialization**:
   * When `spock_navigation.py` is executed, it instantiates `NavigationStationWindow` (defined in `D:\Spock-Onboarding\NavigationStation\app.py`), which inherits from `SuiteShellWindow`.
   * During initialization, a shared state object `self.state = ModelSelectorState()` is created.
2. **Step Building**:
   * In `_build_steps()`, the application calls `build_hardware_step(self.theme, self.state)` from `D:\Spock-Onboarding\NavigationStation\steps\hardware.py`.
   * This helper instantiates a `HardwareScanPanel` (from `model_selector_panels.py`) and wraps it in a standard `QWidget`.
3. **Triggering the Scan**:
   * When the user clicks **"1 Hardware"** in the left navigation panel, `_show_hardware()` is invoked.
   * If a scan has not yet run during this session (`not self._hw_scanned_once`), a single-shot timer immediately triggers the scan:
     ```python
     QTimer.singleShot(0, panel._start_scan)
     ```
   * **Fallback Trigger**: If the user bypasses Step 1 and goes straight to **"2 HF Models"**, `_show_models()` checks if `self.state.hardware_specs` is empty. If empty, it automatically kicks off the hardware scan in the background to prevent downstream failures.

---

### 2. Core Scanning Engine (`spock_scanner_core.py`)

The actual hardware assessment logic is driven by `D:\Spock-Onboarding\spock_scanner_core.py`. It gathers system metrics using a mix of standard libraries, optional third-party packages (`psutil`, `pynvml`), and platform-specific shell commands.

#### A. CPU Detection
* **Function**: `get_cpu_info()`
* **Metrics Gathered**: Physical core count, logical core count, and processor architecture/model name.
* **Implementation**: Uses `psutil.cpu_count(logical=False)` and `psutil.cpu_count(logical=True)` with a fallback to standard platform libraries if `psutil` is missing.

#### B. System RAM Detection
* **Function**: `get_ram_gb()`
* **Metrics Gathered**: Total physical system memory in Gigabytes.
* **Implementation**:
  * **Windows**: Executes `wmic computersystem get TotalPhysicalMemory` via `subprocess`.
  * **Linux**: Parses `/proc/meminfo` looking for `MemTotal`.
  * **macOS**: Executes `sysctl hw.memsize`.
  * **Fallback**: Defaults to `4.0 GB` if all probes fail.

#### C. GPU & VRAM Detection
* **Function**: `get_gpu_info()`
* **Metrics Gathered**: GPU model name and total VRAM (in MB/GB).
* **Implementation**:
  * First attempts to query NVIDIA GPUs directly using `nvidia-smi` via a subprocess call:
    ```bash
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    ```
  * If `nvidia-smi` fails or returns weak/non-NVIDIA results, it falls back to the local `llmfit` bridge (`_gpus_from_llmfit()`), which queries system info via `spock_shell.llmfit_bridge`.

---

### 3. Heuristics & Resource Planning

Once the hardware scan completes, the system runs heuristics to determine how to safely run local LLMs (specifically `llama-server` instances) on the detected hardware.

#### Context Window Recommendation (`recommend_n_ctx`)
The system calculates the recommended context size (`-c` / `n_ctx`) based on available VRAM, model size, and the model's role (embedding vs. chat):
* **Embedding Role (`embed`)**:
  * Embedding models prioritize batch processing over massive context windows.
  * If VRAM $\ge$ 4GB, context is set to at least `1024`.
  * If VRAM $\ge$ 8GB, context is set to at least `2048` to ensure that large text chunks (e.g., Spock's default `truncate_chars ≈ 1500`) fit without truncation.
* **Chat Role (`chat`)**:
  * Calculates VRAM headroom after subtracting the model weights and any sibling models (e.g., if an embedding model is sharing the same GPU).
  * Iterates through a context ladder (`CTX_LADDER` from `model_pick_policy.py`) to find the maximum context size whose KV cache fits within the remaining VRAM headroom.

---

### 4. UI Options & Usage

The **1 Hardware** panel provides a clean interface for the operator to review and manage their system profile:

1. **Scan Hardware (Manual Trigger)**:
   * Although the scan runs automatically on first view, a manual "Scan" button allows the user to re-run the diagnostic (useful if external GPU enclosures are connected or drivers are reloaded).
2. **Hardware Specifications Display**:
   * Displays a structured summary of the detected CPU, RAM, and GPU devices.
   * Highlights VRAM limits, which are critical for determining whether a model can be fully offloaded to the GPU.
3. **Downstream Integration**:
   * **Unlocking Step 2 (HF Models)**: Once `scan_complete` is emitted, the Hugging Face query buttons (`query_btn` and `query_embed_btn`) are enabled. This prevents users from searching for models that their hardware cannot run.
   * **Configuring Step 3 (Launch)**: The scanned GPU list is propagated to the `LaunchPanel` via `launch._populate_gpus()`. This allows users to select which specific GPU to target and dynamically calculates the recommended GPU layers (`-ngl`) to offload.
