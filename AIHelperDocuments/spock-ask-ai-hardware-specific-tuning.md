# Spock Ask AI — 20260906-192459

## You

how does spock bringup menu work?

## Computer

The **Spock Bringup Menu** is a lightweight graphical user interface (GUI) that serves as an onboarding tool for the Spock system. It is designed to guide users through the initial setup and configuration process. Here's how it works based on the provided context:

### Key Components:
1. **Entry Point**:
   - The script `__main__.py` in the `spock_bringup_menu` directory is the entry point. It calls the `main()` function, which initializes the application.

2. **Application Initialization**:
   - The `main()` function imports and initializes the `BringupMenuWindow` class from the `spock_bringup_menu.app` module.
   - It then creates an instance of `BringupMenuWindow` and displays it using `win.show()`.

3. **Application Execution**:
   - The `create_app` function from `spock_shell.qt_app` is used to create a Qt application instance.
   - The application is configured with a name ("Spock Bringup Menu") and the window is displayed.

4. **Dependencies**:
   - The script includes a path adjustment (`_HERE`) to ensure the necessary modules are accessible.
   - It imports `_warpcore_path` to ensure the correct path is set up for the WarpCore library.

### Workflow:
- The user runs the script, which launches the Spock Bringup Menu GUI.
- The GUI provides a user-friendly interface to guide users through the onboarding process, possibly interacting with the Spock system's configuration or setup.

### Notes:
- The Bringup Menu is described as a "lite onboarding GUI," indicating it is a simplified version compared to full-fledged onboarding tools.
- The application is built using Qt, which is a cross-platform GUI framework, allowing it to run on different operating systems.

### Summary:
The Spock Bringup Menu works by launching a Qt application that displays a GUI window for onboarding, guiding users through the initial setup of the Spock system. It is a lightweight, user-friendly interface that integrates with the Spock system's configuration and setup process.

## You

what is the host / recipe?  how is it used? what are the benefits?

## Computer

### **Host / Recipe Overview**

The **host / recipe** is a database table in the `WarpCore` module of the Spock Onboarding system, designed to store and manage **machine capability configurations** for Launch defaults. It is used to define how the system should allocate resources (such as GPUs and RAM) based on the hardware configuration of the machine.

---

### **Key Features of the Host / Recipe**

| Field | Description |
|-------|-------------|
| `id` | Unique identifier for each recipe entry. |
| `version` | Version number of the recipe. |
| `created_at` | Timestamp when the recipe was created. |
| `created_by` | The entity or process that created the recipe. |
| `reason` | A description of the recipe's purpose or reason for creation. |
| `hardware_json` | A JSON object containing hardware details (e.g., RAM, GPUs). |
| `recipe_json` | A JSON object defining the resource allocation strategy (e.g., GPU policy, context sizes). |
| `is_current` | A flag indicating whether the recipe is the current default configuration. |

---

### **How the Host / Recipe is Used**

1. **Resource Allocation**:
   - The `recipe_json` defines how resources (like GPUs and memory) are allocated across different roles (e.g., chat, embedding).
   - The `hardware_json` provides the actual hardware configuration of the machine.

2. **Policy Enforcement**:
   - The `gpu_policy` field determines how GPUs are used:
     - `GPU_POLICY_SPLIT`: Distribute tasks across multiple GPUs.
     - `GPU_POLICY_SINGLE`: Use a single GPU for both roles.
     - `GPU_POLICY_PIN`: Assign specific GPUs to specific roles.

3. **Default Configuration**:
   - The `host_recipe` table is used to set default resource allocations for the system, which are applied when the system starts or when a new profile is loaded.

4. **Dynamic Adjustment**:
   - The `propose_recipe` function dynamically generates a recipe based on the hardware snapshot, ensuring optimal resource usage.

---

### **Benefits of the Host / Recipe**

1. **Consistency**:
   - Ensures that the system uses consistent resource allocation strategies across different machines and environments.

2. **Flexibility**:
   - Allows for dynamic adjustment of resource policies based on hardware capabilities.

3. **Preservation**:
   - The `host_recipe` table is preserved during system resets, ensuring that the default configuration is not lost.

4. **Automation**:
   - Reduces manual configuration by automating the generation of resource allocation strategies.

---

### **Usage Context**

- **`host_recipe.py`** is the primary file that manages the `host_recipe` table and provides the `propose_recipe` function.
- **`app.py`** (e.g., `spock_bringup_menu/app.py`) uses the `host_recipe` to set default resource allocations during the onboarding process.

---

### **Example Use Case**

When the system starts, it calls `propose_recipe()` to generate a default resource allocation based on the hardware snapshot. This determines:
- How many GPUs are available.
- The maximum VRAM available.
- The appropriate GPU policy (e.g., `GPU_POLICY_SPLIT` for dual GPUs with ≤12GB VRAM).
- Default context sizes for chat and embedding.

This ensures that the system uses the most efficient resource allocation strategy based on the machine's hardware.

---

### **Summary**

The **host / recipe** is a critical component of the Spock Onboarding system, enabling the system to dynamically allocate resources based on hardware capabilities. It ensures consistency, flexibility, and automation in resource management, which is essential for efficient and effective operation in a complex environment.

## You

What hardware specific tuning does spock have? how can we use the LLM Model Selection / Model Profile / Host - Recipe and timing history to optimize local hosted LLM Ask AI and Deep Dive requests?

## Computer

### Hardware-Specific Tuning in Spock

Spock, the ship's AI system, incorporates hardware-specific tuning to optimize performance and resource usage. This tuning is primarily guided by the `model_pick_policy.py` file, which outlines a policy for selecting and managing LLM models based on hardware constraints and performance characteristics.

#### Key Hardware-Specific Tuning Elements

1. **VRAM Management**:
   - **Policy**: The policy prioritizes using existing embedding dimensions when the database already contains vectors. It also allocates VRAM to the largest "safe" chat context, avoiding larger parameter counts beyond ~8–14B instruct.
   - **Implementation**: The `usable_vram_gb` function calculates usable VRAM based on the total VRAM and a fraction (`_VRAM_USABLE_FRAC`), ensuring that the system does not exceed the available VRAM.

2. **Quantization**:
   - **Policy**: The system prefers `q8_0` quantization for embedding models and `q4_k_m` for chat models. This balance between speed and quality is crucial for performance.
   - **Implementation**: The `quant_bytes_per_param` function determines the byte size of the quantized model based on the parameter count and quantization scheme.

3. **Context Size**:
   - **Policy**: The `estimate_kv_cache_gb` function calculates the expected KV cache size based on the number of context tokens and parameter count. This helps in managing memory usage efficiently.
   - **Implementation**: The system ensures that the KV cache size does not exceed the available memory, optimizing for both speed and quality.

4. **Model Selection**:
   - **Policy**: The `model_pick_policy.py` file includes a catalog of supported models, with a focus on models that are well-supported and efficient for the given hardware.
   - **Implementation**: The system uses a combination of model quality, speed, and VRAM constraints to select the most appropriate model for each task.

### Utilizing LLM Model Selection and Host-Recipe

To optimize local hosted LLM Ask AI and Deep Dive requests, the following strategies can be employed:

1. **Model Profile**:
   - **Usage**: The `model_pick_policy.py` file provides a model profile that includes parameters such as `params_b`, `dim`, `native_ctx`, and `yarn_ctx`. These parameters are crucial for determining the model's suitability for the task.
   - **Optimization**: By leveraging the model profile, the system can quickly assess which models are best suited for the current task, ensuring optimal performance.

2. **Host-Recipe**:
   - **Usage**: The `host_recipe.py` file defines the host-specific configurations, including VRAM allocation, quantization settings, and context size limits.
   - **Optimization**: The host-recipe ensures that the model is configured to use the available hardware resources efficiently, balancing speed and quality.

3. **Timing History**:
   - **Usage**: The `ask_timing_store.py` file tracks the timing of previous requests, providing insights into performance bottlenecks and resource usage patterns.
   - **Optimization**: By analyzing the timing history, the system can identify areas for improvement, such as optimizing context size or adjusting quantization settings.

### Example Use Cases

- **Embedding Models**: The system uses the `Qwen/Qwen3-Embedding-8B-GGUF` model for embedding tasks, leveraging its high quality and speed while managing VRAM usage.
- **Chat Models**: The `Qwen/Qwen3-32B-GGUF` model is preferred for chat tasks due to its high speed and quality, while the `Phi-4-GGUF` model is used for smaller contexts where speed is critical.

### Conclusion

Spock's hardware-specific tuning ensures that the system efficiently utilizes available resources, balancing speed and quality. By leveraging the model selection, host-recipe, and timing history, the system can be optimized for local hosted LLM Ask AI and Deep Dive requests, providing a robust and efficient solution for the ship's AI needs.
