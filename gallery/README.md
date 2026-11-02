# Spock Screenshots Gallery

GitHub-friendly JPEG gallery generated from ShareX captures in `../assets/` (source of truth — never renamed in place).

## Generate / refresh

1. Load a vision-capable model in **LM Studio** (port **1234**).
2. From the repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prescan-screenshots.ps1
```

Optional: `-Force` to recaption everything, `-Limit 3` to smoke-test.

Outputs:

- `docs/images/<slug>.jpg` — resized JPEG (max width 1280; must live under `docs/` for MkDocs)
- `manifest.json` — original PNG → slug / caption map
- `docs/index.md`, `docs/captions.md` — MkDocs pages

## Preview locally

MkDocs must run with `gallery` as the cwd (so it picks up this folder’s `mkdocs.yml`). JPEGs live under **`docs/images/`** (MkDocs only publishes files inside `docs_dir`).

```powershell
cd D:\Spock-AI-Universal-Wiki\gallery
# whichever mkdocs you have installed (user/site or after: pip install -r ..\requirements-docs.txt)
mkdocs serve -a 127.0.0.1:8001
```

Open http://127.0.0.1:8001/ (port **8001** so it does not collide with the main Spock docs on **8000**).

## GitHub / Pages

Commit `docs/images/`, `manifest.json`, and `docs/*.md` (not raw `../assets/*.png`). CI builds this folder’s `mkdocs.yml` into `/gallery/` on:

https://kimmlombard.github.io/Spock-AI-Universal-Wiki/gallery/

Main docs: https://kimmlombard.github.io/Spock-AI-Universal-Wiki/
