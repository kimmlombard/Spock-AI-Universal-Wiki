# Spock Ask AI — 20260906-113350

## You

How does the Spock Appliction work?  What is "Ask AI"

## Computer

Based on the provided context:

"Ask AI" is an **in-app feature** that appears as part of a **center panel** within the "Engineering Deck" of the Spock Application. It is paired with a "Deep Dive" feature (Document: `ask_panel`).

The provided context does not contain enough information to explain how the entire Spock Application works. It only describes a specific component related to "Ask AI" and "Deep Dive."

## You

what is "Deep Dive" in the Ask AI panel?  How does it work?

## Computer

The "Deep Dive" functionality within the Spock-Onboarding system's "Ask AI" panel provides an advanced mode for querying the ship's computer corpus. It is designed for more comprehensive and in-depth analysis compared to a standard "Ask AI" query.

### What is "Deep Dive"?

As indicated by `D:\Spock-Onboarding\EngineeringDeck\ask_panel.py` [Doc 1], the "Ask AI" panel serves as an "In-app Ask AI + Deep Dive center panel for Engineering Deck." It offers two primary modes: "Ask" and "Deep Dive." The web UI counterpart, `D:\Spock-Onboarding\templates\webui\app.js` [Doc 3], explicitly shows UI elements (`modeAsk`, `modeDeep`) and a `setMode` function to switch between "ask" and "deep_dive" modes, confirming this distinction.

The "Deep Dive" mode is intended for scenarios requiring a more thorough and potentially multi-step retrieval-augmented generation (RAG) process over the filtered corpus.

### How it Works

The core logic for both "Ask" and "Deep Dive" modes resides within the `_AskWorker` class in `D:\Spock-Onboarding\EngineeringDeck\ask_panel.py` [Doc 1].

1.  **Mode Selection**:
    *   The `AskAiPanel` (or the web UI) allows the user to select between "Ask" and "Deep Dive" modes. This selection is passed to the `_AskWorker` as a boolean `deep` parameter.

2.  **Document Filtering**:
    *   Before any query, a filter clause is constructed using `deep_dive.build_documents_filter_clause`. This clause incorporates user-defined `path_filter`, `ext_filter` (include extensions), and `exclude_ext` (exclude extensions). These filters are also visible in the web UI (`pathFilter`, `langFilters`, `excludeFilters` in `D:\Spock-Onboarding\templates\webui\app.js` [Doc 3]).

3.  **Execution Flow**:

    *   **If `deep` is True (Deep Dive Mode)**:
        *   The `_AskWorker` calls `deep_dive.run_http_deep_dive`.
        *   This function is invoked with a comprehensive set of parameters:
            *   `question`: The user's query.
            *   `filter_clause`: The document filter.
            *   `history`: Chat history.
            *   `llm`: The Large Language Model instance.
            *   `embeddings_url`: URL for the embeddings service.
            *   `db_path`: Path to the `SHIP_COMPUTER_DB` (the corpus database).
            *   `hybrid_search_fn`: A function for hybrid search (likely used internally by `run_http_deep_dive` for initial retrieval).
            *   `n_ctx`: The LLM's context window size (e.g., 32768 tokens).
            *   `max_out_tokens`: Maximum tokens for the LLM's output (e.g., 2048 tokens).
            *   `ask_ai_provider`: The AI provider being used.
            *   `chat_url`: URL for a chat service.
        *   The `run_http_deep_dive` function returns an `answer` and a list of `sources`. This suggests a more sophisticated RAG pipeline, potentially involving multiple retrieval steps, summarization, or iterative querying of the LLM with retrieved context.

    *   **If `deep` is False (Ask Mode)**:
        *   The `_AskWorker` first performs a `hybrid_search_fn` on the `SHIP_COMPUTER_DB` using the `question`, `embeddings_url`, and `filter_clause`. It retrieves `top_k=5` results.
        *   It then constructs a context (`ctx`) by concatenating the `title`, `path`, and `content_snippet` (or `snippet`) from these search results.
        *   Finally, it calls `self.llm.ask_with_context(self.question, ctx, history=[])` to generate an answer using the retrieved snippets as direct context for the LLM.

In summary, "Deep Dive" mode leverages a dedicated `run_http_deep_dive` function, implying a more advanced and configurable RAG process that can handle larger contexts and potentially more complex interactions with the LLM and embedding services. The standard "Ask" mode, in contrast, performs a simpler hybrid search to gather snippets and then uses those snippets as direct context for a single LLM query.
