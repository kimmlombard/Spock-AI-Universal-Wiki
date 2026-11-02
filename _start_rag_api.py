"""Start the Spock OpenAI-compatible RAG API + browser Web UI.

Uses the same Ask AI provider settings as the UI (including Vertex Gemini via ADC).
Web UI: http://HOST:PORT/
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import _warpcore_path

_warpcore_path.ensure()

from deep_dive import (
    build_documents_filter_clause,
    packing_opts_for_llm,
    packing_opts_from_config,
    run_http_deep_dive,
)
from WarpCore.config_defaults import merge_embedding_profile
from rag_api_server import RagApiServer
from spock_rag_adapter.bridge_host import make_llm_client
from WarpCore.search import hybrid_search, set_embeddings_url
from spock_rag_adapter.embedding_corpus import guarded_hybrid_search

CONFIG_FILE = os.path.join(ROOT, "app_config.json")
DB_PATH = os.path.join(ROOT, "ship_computer.db")
PID_FILE = os.path.join(ROOT, "_rag_api_pid.txt")


def load_cfg() -> dict:
    try:
        import _warpcore_path

        _warpcore_path.ensure()
        from WarpCore import settings_store

        return settings_store.load_app_config(DB_PATH)
    except Exception:
        pass
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    cfg = load_cfg()
    profile = merge_embedding_profile(cfg.get("embedding_profile"))
    rag = cfg.get("rag_api") or {}
    emb_url = profile.get(
        "embeddings_url", "http://localhost:8080/embeddings"
    )

    set_embeddings_url(emb_url)

    preferred = cfg.get("ask_ai_provider") or "llama-server"
    search = guarded_hybrid_search(hybrid_search)
    llm = make_llm_client(cfg)

    def build_filter(
        path_contains: str,
        extension: str = "",
        exclude_generated: bool = True,
    ) -> str:
        return build_documents_filter_clause(
            path_contains or "",
            extension or "",
            exclude_generated=bool(exclude_generated),
        )

    def deep_dive(
        question: str = "",
        filter_clause: str = "",
        history=None,
        llm_client=None,
        embeddings_url: str = "",
        db_path: str = "",
        **kwargs,
    ):
        client = kwargs.get("llm") or llm_client or llm
        try:
            opts = packing_opts_for_llm(cfg, client)
        except Exception:
            opts = packing_opts_from_config(cfg)
        return run_http_deep_dive(
            question=question,
            filter_clause=filter_clause or "",
            history=history or [],
            llm=client,
            embeddings_url=embeddings_url or emb_url,
            db_path=db_path or DB_PATH,
            hybrid_search_fn=search,
            n_ctx=int(opts["n_ctx"]),
            max_out_tokens=int(opts["max_out_tokens"]),
            ask_ai_provider=str(opts["ask_ai_provider"]),
            chat_url=str(opts["chat_url"]),
        )

    host = rag.get("host", "127.0.0.1")
    port = int(rag.get("port", 8090))
    api_key = rag.get("api_key", "")

    server = RagApiServer(
        host=host,
        port=port,
        db_path=DB_PATH,
        api_key=api_key,
        get_embeddings_url=lambda: emb_url,
        get_llm_client=lambda: llm,
        hybrid_search_fn=search,
        build_filter_fn=build_filter,
        deep_dive_fn=deep_dive,
    )
    try:
        server.start()
    except OSError as e:
        print(json.dumps({"status": "error", "error": str(e)}), flush=True)
        raise SystemExit(1) from e

    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

    try:
        cfg.setdefault("rag_api", {})["enabled"] = True
        try:
            import _warpcore_path

            _warpcore_path.ensure()
            from WarpCore import settings_store

            settings_store.set(DB_PATH, "app.rag_api", cfg["rag_api"], by="rag_api")
        except Exception:
            pass
    except OSError:
        pass

    print(
        json.dumps(
            {
                "status": "running",
                "base_url": server.base_url,
                "web_url": server.web_url,
                "embeddings_url": emb_url,
                "llm_provider": llm.active_provider,
                "llm_available": llm.is_available,
                "ask_ai_provider": preferred,
                "model": llm.model,
            },
            indent=2,
        ),
        flush=True,
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
