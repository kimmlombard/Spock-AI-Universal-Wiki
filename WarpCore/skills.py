"""Typed skill contracts for the wiki agent (methods-as-skills).

Each Skills method returns a SkillResult with structured evidence
(counts, affected paths, error summaries) instead of raw tracebacks.
Payloads arriving from agent_queue are validated against per-skill
shapes before dispatch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, TypedDict

SkillName = Literal[
    "onboarding",
    "maintenance",
    "backup",
    "update_index",
    "reference_review",
    "acquire_codebase_knowledge",
]

# --- Per-skill payload shapes (agent_queue -> Skills) ----------------------


class OnboardingPayload(TypedDict, total=False):
    path: str
    paths: List[str]
    reprocess: bool


class MaintenancePayload(TypedDict):
    pass


class BackupPayload(TypedDict):
    pass


class UpdateIndexPayload(TypedDict):
    pass


class ReferenceReviewPayload(TypedDict):
    url: str
    role: str


class AcquireCodebaseKnowledgePayload(TypedDict, total=False):
    root_path: str
    focus: str
    output_rel: str
    ingest: bool


SkillPayload = Dict[str, Any]

_SKILL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "onboarding": {
        "required": [],
        "types": {"path": str, "paths": list, "reprocess": bool},
        "defaults": {},
    },
    "maintenance": {"required": [], "types": {}, "defaults": {}},
    "backup": {"required": [], "types": {}, "defaults": {}},
    "update_index": {"required": [], "types": {}, "defaults": {}},
    "reference_review": {
        "required": ["url"],
        "types": {"url": str, "role": str},
        "defaults": {"role": "kirk"},
    },
    "acquire_codebase_knowledge": {
        "required": ["root_path"],
        "types": {
            "root_path": str,
            "focus": str,
            "output_rel": str,
            "ingest": bool,
        },
        "defaults": {
            "focus": "",
            "output_rel": "docs/codebase",
            "ingest": True,
        },
    },
}


@dataclass
class SkillResult:
    """Structured outcome of a skill run, persisted to logs / agent_queue."""

    ok: bool
    evidence: str = ""
    log_lines: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "evidence": self.evidence, "log_lines": self.log_lines}

    @classmethod
    def from_json(cls, raw: str) -> "SkillResult":
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return cls(
                    ok=bool(data.get("ok", False)),
                    evidence=str(data.get("evidence") or ""),
                    log_lines=[str(x) for x in (data.get("log_lines") or [])],
                )
        except (TypeError, ValueError):
            pass
        return cls(ok=False, evidence=raw[:500])


def validate_payload(skill: str, payload: dict) -> SkillPayload:
    """Validate and normalize a payload for a named skill.

    Raises ValueError on unknown skill or missing/wrong-typed required keys.
    Applies per-skill defaults and strips unknown keys.
    """
    schema = _SKILL_SCHEMAS.get(skill)
    if schema is None:
        raise ValueError(f"Unknown skill: {skill!r}")
    payload = dict(payload or {})
    for key, default in schema["defaults"].items():
        payload.setdefault(key, default)
    for key in schema["required"]:
        if key not in payload:
            raise ValueError(f"Skill {skill!r} requires payload key {key!r}")
    if skill == "onboarding":
        path = payload.get("path")
        paths = payload.get("paths")
        if not path and not paths:
            raise ValueError("Skill 'onboarding' requires payload key 'path' or 'paths'")
    for key, vtype in schema["types"].items():
        if key in payload and payload[key] is not None and not isinstance(payload[key], vtype):
            raise ValueError(
                f"Skill {skill!r} payload key {key!r} must be {vtype.__name__}, "
                f"got {type(payload[key]).__name__}"
            )
    return payload


def parse_payload_json(payload_json: str) -> dict:
    """Safely decode agent_queue.payload_json; JSON errors become empty dict."""
    try:
        data = json.loads(payload_json or "{}")
    except (TypeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}
