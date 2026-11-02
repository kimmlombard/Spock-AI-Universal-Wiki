"""Acquire codebase knowledge — deterministic scan + seven docs/codebase templates.

Adapted from github/awesome-copilot ``acquire-codebase-knowledge`` (MIT).
v1 fills docs from scan evidence; narrative gaps stay as ``[TODO]``.
"""

from __future__ import annotations

from spock_codebase_knowledge.run import DOC_NAMES, acquire_codebase_knowledge

__all__ = ["DOC_NAMES", "acquire_codebase_knowledge"]
