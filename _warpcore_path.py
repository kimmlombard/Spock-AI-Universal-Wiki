"""Migration shim: make WarpCore importable from the monolith's modules.

The V2 refactor moves core logic into WarpCore. Until the station split is
complete, modules in this tree need WarpCore on sys.path. This file prefers
the local WarpCore package, then falls back to the sibling spock_refactored.
"""

import os
import sys


def ensure() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    local = here
    if os.path.isdir(os.path.join(local, "WarpCore")):
        if local not in sys.path:
            sys.path.insert(0, local)
        return
    candidate = os.path.abspath(os.path.join(here, "..", "spock_refactored"))
    if os.path.isdir(os.path.join(candidate, "WarpCore")) and candidate not in sys.path:
        sys.path.insert(0, candidate)
