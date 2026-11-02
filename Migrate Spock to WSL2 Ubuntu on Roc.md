Migrate Spock to WSL2 Ubuntu on Roc
===================================

Verdict: WSL2, not dual-boot
----------------------------

**Run Ubuntu under WSL2 on this rig.** Keep Windows 11 as the host OS.

|                    |                                                              |                                               |
| ------------------ | ------------------------------------------------------------ | --------------------------------------------- |
| Factor             | WSL2 (chosen)                                                | Dual-boot Ubuntu                              |
| Parallel work      | Windows Spock stays up while you port                        | Reboot to switch; Windows suite offline       |
| Dual RTX 3060 CUDA | Supported via current Game Ready/Studio driver + CUDA in WSL | Native, slightly less virtualization overhead |
| New 1TB drive      | Hold WSL VHDX + GGUFs + HF cache                             | Needs partitions, bootloader, recovery risk   |
| PyQt6 GUI          | WSLg on Windows 11 Pro (you are on build 26200)              | Native X11/Wayland                            |
| Public-repo goal   | Matches `launch/unix` pack beside Windows core               | Overkill for “make core run + pytest”         |

Reserve dual-boot only if WSLg or WSL-CUDA proves inadequate after a real smoke (multi-GPU llama-server + SuiteShell). Do not start there.

Current host facts: Windows 11 Pro, Ryzen 7 5800X, 64 GB RAM, **2× RTX 3060**, two ~1 TB NVMe SSDs in use, **WSL not installed yet**. The extra 1 TB HDD is not visible yet — install/format it first.
    flowchart LR
      subgraph winHost [Windows 11 Roc]
        WinSpock[Spock-AI-Universal-Wiki Windows]
        NVdriver[NVIDIA Windows driver]
        NewHDD[New 1TB drive E:]
      end
      subgraph wsl2 [WSL2 Ubuntu]
        LaunchUnix[launch/unix]
        Core[Spock core pytest GUI]
        Llama[llama-server Linux CUDA]
      end
      NVdriver --> Llama
      NewHDD --> wsl2
      WinSpock -.->|keep working| winHost
      LaunchUnix --> Core
      Core --> Llama
Phase 0 — Hardware and disk layout
----------------------------------

1. Install the 1 TB HDD; confirm it appears in Disk Management.

2. Initialize GPT; create one **NTFS** volume (e.g. `E:`). Do not dual-boot-partition this disk.

3. Create folders:
   
   * `E:\WSL\` — Ubuntu distro VHDX (via `wsl --import`)
   
   * `E:\Spock\models\` — GGUFs (shared or Linux-primary)
   
   * `E:\Spock\cache\` — Hugging Face / llama caches

4. Leave Windows Spock at `[D:\Spock-AI-Universal-Wiki](D:\Spock-AI-Universal-Wiki)` unchanged as the reference Windows tree.

Phase 1 — Install WSL2 + Ubuntu on the new drive
------------------------------------------------

1. Admin PowerShell: `wsl --install --no-distribution` then reboot if prompted; install **Ubuntu 24.04 LTS** from Store or `wsl --install -d Ubuntu-24.04`.

2. Immediately move the distro off the system SSD onto `E:`:
   
   * `wsl --shutdown`
   
   * `wsl --export Ubuntu-24.04 E:\WSL\ubuntu.tar`
   
   * `wsl --unregister Ubuntu-24.04`
   
   * `wsl --import Ubuntu-24.04 E:\WSL\Ubuntu E:\WSL\ubuntu.tar --version 2`
   
   * Set default user (`ubuntu.exe config --default-user …` or `/etc/wsl.conf` + `passwd`)

3. `%UserProfile%\.wslconfig` (host): raise memory (e.g. 32 GB), processors (e.g. 12), `networkingMode=mirrored` if you need easy localhost to Windows llama — start with defaults, tune later.

4. Verify GPU passthrough inside Ubuntu: `nvidia-smi` lists **both** 3060s (Windows NVIDIA driver must be current; no separate Windows “CUDA Toolkit” required for basic WSL GPU).

Phase 2 — Ubuntu CUDA + Linux llama-server
------------------------------------------

1. In WSL: install build essentials, `python3.12-venv`, `git`, `curl`.

2. Install NVIDIA’s **CUDA toolkit for WSL-Ubuntu** per current NVIDIA WSL docs (match driver-supported CUDA 12.x).

3. Obtain **Linux** `llama-server` with CUDA (prebuilt `bin-ubuntu-cuda*` from llama.cpp releases, or build). Do **not** use `[spock_onboarding/runtime.py](D:\Spock-AI-Universal-Wiki\spock_onboarding\runtime.py)` Windows zip path (`download_llama_server_windows` / `bin-win-cuda-*`).

4. Smoke: `./llama-server -h`; short embed/chat on one GPU; then `--tensor-split` / dual-GPU flags matching your Windows host recipe.

5. Point models at `E:\Spock\models` via `/mnt/e/Spock/models` **or** copy hot GGUFs into `~/spock/models` on the Linux VHDX for faster I/O (HDD vs reading through `/mnt`).

Phase 3 — Spock tree inside Linux filesystem
--------------------------------------------

1. Clone/copy `[D:\Spock-AI-Universal-Wiki](D:\Spock-AI-Universal-Wiki)` into WSL home, e.g. `~/src/Spock-AI-Universal-Wiki` (ext4 on `E:\WSL\Ubuntu`). Avoid long-term running pytest off `/mnt/d/...` (slow + file-watch quirks).

2. Create `.venv` with `python3 -m venv .venv`; install `requirements-ui.txt` then expand toward `requirements-full.txt` / `requirements-dev.txt` as tests need.

3. Add **minimal** `launch/unix` (secondary to Bringup Menu, but enough to start):
   
   * `scripts/spock.sh` → `.venv/bin/python -m` / `main.py`
   
   * env: `LLAMA_SERVER_PATH`, `SPOCK_*` ports, HF cache under `/mnt/e/Spock/cache` or `~/spock/cache`

4. Implement the **platform seam** in core (same monorepo):
   
   * `venv_python()` → `bin/python`
   
   * no `CREATE_NEW_CONSOLE` / `taskkill` / WinJob — process-group or explicit stop-all
   
   * llama binary name `llama-server` (no `.exe`)

5. Config: Linux `app_config` / env examples with `/home/...` paths; do not reuse Windows `C:\DEV\llamaccp` defaults.

Phase 4 — GUI and service smoke (before full pytest)
----------------------------------------------------

1. WSLg: `python main.py` / SuiteShell opens a window from Ubuntu.

2. Start embed `:8080` + chat `:8081` with Linux llama-server; hit `/health` from WSL curl.

3. MCP HTTP `:8765` + CORS check from any WebUI you run (Windows or WSL).

4. Confirm orphan behavior on quit (Unix stand-in for `[spock_shell/win_job.py](D:\Spock-AI-Universal-Wiki\spock_shell\win_job.py)`).

Phase 5 — Full unit testing under Ubuntu
----------------------------------------

1. `pip install -r requirements-dev.txt` (pytest).

2. Run `pytest tests -q` inside WSL; fix OS-assumption failures (path fixtures, `.exe`, `Scripts/python.exe`, PowerShell-only tests).

3. Mark or skip tests that truly require Windows bringup/bootstrap; keep core coverage green on Linux.

4. Re-run the same suite on Windows afterward so the monorepo stays dual-healthy.

Phase 6 — Optional hardening (after green)
------------------------------------------

* Document `launch/unix` in README (“Experimental: WSL2/Ubuntu”).

* CI later: GitHub Actions `ubuntu-latest` pytest (CPU-only) + Windows pytest.

* Dual-boot still not required unless you hit a hard WSL GPU/GUI ceiling.

What not to do on day one
-------------------------

* Do not wipe Windows or install Ubuntu bare-metal on the new HDD first.

* Do not unregister WSL without an `E:\WSL` export/backup.

* Do not expect `[bootstrap.ps1](D:\Spock-AI-Universal-Wiki\bootstrap.ps1)` / Bringup steps 1–2 to work in Ubuntu — that is the deferred OS-tailored launch work.

* Do not share one SQLite `ship_computer.db` across Windows and WSL concurrently (corruption risk); use separate DB paths or copy-on-demand.

Success criteria
----------------

* Both GPUs visible in WSL `nvidia-smi`

* Linux `llama-server` serves embed+chat with your GGUFs

* Spock SuiteShell launches via WSLg from `~/src/Spock-AI-Universal-Wiki`

* `pytest tests -q` green (or documented skips only for Windows-only launchers)

* Windows tree at `D:\Spock-AI-Universal-Wiki` still runs
