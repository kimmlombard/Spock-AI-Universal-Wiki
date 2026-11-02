"""Shared ModelSelectorState for Navigation / Science stations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ModelSelectorState:
    hardware_specs: Dict[str, Any] = field(default_factory=dict)
    hardware_report: str = ""
    model_data: List[Dict[str, Any]] = field(default_factory=list)
    close_data: List[Dict[str, Any]] = field(default_factory=list)
    selected_hf_model_id: str = ""
    selected_gguf_path: str = ""
    gpu_list: List[Dict[str, Any]] = field(default_factory=list)
    info_card_text: str = ""
    status_message: str = "STATUS: STANDBY"
    ship_status_report: str = ""
    upgrade_report: str = ""
    gpu_details_report: str = ""
    llamaccp_config_report: str = ""
    # One probe per session: the station scans at launch and every panel reads
    # the result from here. Only SCAN HARDWARE re-probes.
    hardware_probed_at: str = ""
    hardware_probe_error: str = ""
