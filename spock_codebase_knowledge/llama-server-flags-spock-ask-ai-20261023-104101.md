# Spock Ask AI — 20261023-104101

## You

please explain each of the flags in this command

C:\DEV\llamaccp\llama-server.exe -m C:\Users\<user_name>\.cache\huggingface\hub\models--unsloth--Qwen3.6-27B-GGUF\snapshots\Qwen3.6-27B-IQ4_XS.gguf --host 127.0.0.1 --port 8081 -c 16384 -ngl 99 --split-mode layer --tensor-split 0.45,0.55 --flash-attn on -ctk q4_0 -ctv q4_0 -b 2048 -ub 1024 --grp-attn-n 4

## Computer

Could not reach LLM provider.
No chat provider reachable. Open Configure Spock AI and connect to LM Studio / Ollama / llamaccp (use the chat port, not embeddings).

## You

please explain each of the flags in this command

C:\DEV\llamaccp\llama-server.exe -m C:\Users\<user_name>\.cache\huggingface\hub\models--unsloth--Qwen3.6-27B-GGUF\snapshots\Qwen3.6-27B-IQ4_XS.gguf --host 127.0.0.1 --port 8081 -c 16384 -ngl 99 --split-mode layer --tensor-split 0.45,0.55 --flash-attn on -ctk q4_0 -ctv q4_0 -b 2048 -ub 1024 --grp-attn-n 4

## Computer

Based on the provided corpus, specifically `D:\Spock-Universal-AI-Wiki\spock_onboarding\llama_process.py` (Doc 6) and `D:\Spock-Universal-AI-Wiki\model_pick_policy.py` (Doc 5), here is the technical breakdown of the flags in the provided `llama-server.exe` command.

This command configures a **multi-GPU, quantized Qwen3.6-27B** model for chat inference, optimized for a system with two GPUs (implied by the tensor split).

### 1. Model & Execution Context
*   **`-m C:\Users\<user_name>\.cache\huggingface\hub\models--unsloth--Qwen3.6-27B-GGUF\snapshots\Qwen3.6-27B-IQ4_XS.gguf`**
    *   **Function:** Specifies the path to the GGUF model file.
    *   **Context:** The model is `Qwen3.6-27B` quantized to `IQ4_XS` (a high-efficiency 4-bit quantization). Note that `model_pick_policy.py` (Doc 5) lists `Qwen/Qwen3-27B-GGUF` in its catalog, but this command uses an `unsloth` variant, likely for improved performance or specific quantization benefits not present in the default catalog.
*   **`--host 127.0.0.1`**
    *   **Function:** Binds the server to the loopback interface only.
    *   **Context:** `llama_process.py` (Doc 6) defaults to `0.0.0.0` in `build_server_argv`, but this command explicitly restricts access to localhost, enhancing security for local-only Spock AI interactions.
*   **`--port 8081`**
    *   **Function:** Sets the HTTP API port.
    *   **Context:** This matches the `DEFAULT_CHAT_PORT` defined in `WarpCore.service_endpoints` (referenced in Doc 6) and the `chat.port` in `spock_ready_last.json` (Doc 4).

### 2. Context & GPU Offloading
*   **`-c 16384`**
    *   **Function:** Sets the context window size to 16,384 tokens.
    *   **Context:** `model_pick_policy.py` (Doc 5) defines a `CTX_LADDER` including `16384`. This is a balanced choice for RAG (Retrieval-Augmented Generation) tasks, allowing sufficient room for retrieved documents plus the user query, without excessive VRAM overhead for KV cache.
*   **`-ngl 99`**
    *   **Function:** Offloads 99 layers to the GPU(s).
    *   **Context:** For a 27B model, this effectively offloads the entire model to the GPU(s), leaving only the final output layer on the CPU (if applicable) or ensuring full GPU utilization. This is critical for performance.
*   **`--split-mode layer`**
    *   **Function:** Defines how the model is split across multiple GPUs. `layer` means layers are distributed sequentially across devices.
    *   **Context:** Required when using `--tensor-split`. It ensures that the model weights are partitioned by layer rather than by tensor dimension, which is generally more efficient for llama.cpp's multi-GPU implementation.
*   **`--tensor-split 0.45,0.55`**
    *   **Function:** Distributes the model weights across two GPUs.
    *   **Context:** GPU 0 gets 45% of the weights, and GPU 1 gets 55%. This suggests an asymmetric GPU setup (e.g., one 24GB card and one 12GB card, or similar VRAM disparity). The sum is 1.0, indicating exactly two devices are used.

### 3. Quantization & Attention Optimization
*   **`--flash-attn on`**
    *   **Function:** Enables Flash Attention.
    *   **Context:** This optimization reduces the memory footprint and increases speed for attention calculations, particularly beneficial for large context windows (`-c 16384`). It requires GPU support (CUDA/Vulkan).
*   **`-ctk q4_0`**
    *   **Function:** Sets the computation type for the key (K) cache to `q4_0` (4-bit integer).
    *   **Context:** Reduces VRAM usage for the KV cache. Since the model itself is `IQ4_XS`, using `q4_0` for the cache maintains consistency and minimizes precision loss while saving memory.
*   **`-ctv q4_0`**
    *   **Function:** Sets the computation type for the value (V) cache to `q4_0`.
    *   **Context:** Similar to `-ctk`, this optimizes the value cache for VRAM efficiency.

### 4. Batch Processing & Grouped Attention
*   **`-b 2048`**
    *   **Function:** Sets the main batch size to 2048.
    *   **Context:** This is the maximum number of tokens processed in a single forward pass. A larger batch size improves throughput for long prompts or multiple concurrent requests. `llama_process.py` (Doc 6) defaults to `512`, so this is a significant increase, likely tuned for the 27B model's capacity.
*   **`-ub 1024`**
    *   **Function:** Sets the upload batch size to 1024.
    *   **Context:** This controls the number of tokens processed during the prompt ingestion phase (prefill). A smaller value than `-b` can help manage memory spikes during initial prompt loading.
*   **`--grp-attn-n 4`**
    *   **Function:** Enables Grouped Query Attention (GQA) with a group size of 4.
    *   **Context:** Qwen3 models use GQA. This flag explicitly sets the number of heads per group. It optimizes memory bandwidth usage by sharing keys among multiple query heads. This is a model-specific architectural feature, not just a runtime optimization.

### Summary of Architecture Implications
This command represents a **high-performance, multi-GPU configuration** for the Spock AI system:
1.  **Model:** Qwen3.6-27B (large, capable model).
2.  **Hardware:** Two GPUs with asymmetric VRAM (45/55 split).
3.  **Optimization:** Flash Attention, GQA, and quantized KV cache (`q4_0`) are used to maximize throughput and minimize VRAM pressure.
4.  **Context:** 16k tokens, suitable for complex RAG queries.
5.  **Batching:** Aggressive batching (`-b 2048`) suggests the system is tuned for high throughput, possibly handling multiple concurrent requests or very long prompts efficiently.

This configuration aligns with the `model_pick_policy.py` (Doc 5) goal of "spending remaining VRAM on the largest *safe* chat context," leveraging multi-GPU capabilities to run a 27B model that would otherwise not fit on a single consumer GPU.
