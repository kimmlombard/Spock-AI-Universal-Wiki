# Evidence pack — Google / Gemma / Gemini (Best New Resource)

Companion to [gemma4-developer-agent-paper-writeup.md](gemma4-developer-agent-paper-writeup.md).

## Live links

| Artifact | URL |
|----------|-----|
| Repo | https://github.com/kimmlombard/Spock-AI-Universal-Wiki |
| Docs | https://kimmlombard.github.io/Spock-AI-Universal-Wiki/ |
| Gallery | https://kimmlombard.github.io/Spock-AI-Universal-Wiki/gallery/ |

## Gallery citations (file names under `gallery/docs/images/`)

- `spock-hf-chat-models-list.jpg` — Google chat models on HF Filter Chat  
- `spock-navigation-station-gemma-quantizations.jpg` — Gemma GGUF quants  
- `spock-model-selection-panel.jpg` — embeddinggemma GGUF on disk  
- `spock-google-search-view.jpg` / `spock-navigation-station-google-search.jpg` — Google Search  
- `spock-navigation-station-ai-chat.jpg` — Gemini pane  
- `spock-mcp-adapter-settings-panel.jpg` / `spock-mcp-reference-panel.jpg` — MCP  
- `spock-embedding-profile-rag-api-panel.jpg` — embedding / RAG API  
- `spock-ask-ai-deep-dive-panel*.jpg` / `spock-ask-ai-chat-panel.jpg` — Ask / Deep Dive  

## Reproduce notes

1. Provider tab: add `google` (or clear filter for ALL).  
2. Prefer Gemma local GGUF if VRAM allows; document Gemma 2/3 if Gemma 4 weights are not loaded on this host.  
3. Gemini / Vertex: configure locally only; never commit `app_config.json` / `.env`.  
4. After Pages is public, click through docs ↔ gallery nav links.

## Word-count gate

```powershell
(Get-Content docs\kaggle\gemma4-developer-agent-paper-writeup.md -Raw).Split([char[]]@(' ','`t','`n','`r'), 'RemoveEmptyEntries').Count
```

Target ≤3000; draft aims ~2800.
