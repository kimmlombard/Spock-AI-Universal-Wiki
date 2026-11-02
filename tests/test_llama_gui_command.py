"""Llama GUI View Command parsing and the Launch-button port decision."""

import tempfile
from pathlib import Path

from spock_shell.llama_gui_command import (
    action_for_listener,
    flag_value,
    parse_llama_gui_command,
    parse_port,
    saved_argv,
    save_saved_text,
    split_llama_gui_command,
    with_resolved_binary,
)

CHAT = (
    "llama-server.exe -c 64000 -b 2048 -ub 512 --load-mode auto -cram 8192 "
    "--poll 50 -ngl auto -mg 0 -fa auto -kvo --no-repack --op-offload -fit on "
    "-fitt 1024 -fitc 64000 --mmproj-offload --temp 0.8 --top-k 40 --top-p 0.95 "
    "--min-p 0.05 --repeat-last-n 64 -rea auto --jinja --kv-unified "
    "--host 127.0.0.1 --port 8081 -np -1 -cb --cache-prompt --cache-idle-slots "
    "--slots -to 3600 --metrics --webui -sps 0.1 -lv 3 --log-colors auto --warmup "
    "-m C:\\Users\\<user_name>\\.lmstudio\\models/lmstudio-community/Qwen3.5-9B-GGUF/"
    "Qwen3.5-9B-Q4_K_M.gguf"
)


def test_chat_example_keeps_port_context_and_model():
    argv = parse_llama_gui_command(CHAT)
    model = flag_value(argv, ("-m", "--model"))
    assert parse_port(argv, 0) == 8081
    assert flag_value(argv, ("-c", "--ctx-size")) == "64000"
    assert model.endswith("Qwen3.5-9B-Q4_K_M.gguf")
    assert model.startswith("C:\\Users\\")


def test_quoted_path_with_spaces_round_trips():
    line = 'llama-server.exe -m "C:\\Models\\My Model\\chat.gguf" --port 8081'
    argv = split_llama_gui_command(line)
    assert argv == [
        "llama-server.exe",
        "-m",
        "C:\\Models\\My Model\\chat.gguf",
        "--port",
        "8081",
    ]


def test_argv0_is_replaced_with_the_resolved_binary():
    argv = with_resolved_binary(
        parse_llama_gui_command(CHAT), r"tools\llama-server\llama-server.exe"
    )
    assert argv[0] == r"tools\llama-server\llama-server.exe"
    assert argv[1] == "-c"


def test_empty_saved_command_does_not_override():
    db = str(Path(tempfile.mkdtemp()) / "ship_computer.db")
    assert saved_argv(db, "chat", r"tools\llama-server\llama-server.exe") is None


def test_embed_command_is_not_returned_for_chat():
    db = str(Path(tempfile.mkdtemp()) / "ship_computer.db")
    save_saved_text(
        db,
        "embedding",
        "llama-server.exe -m C:\\models\\embed.gguf --port 8080 --embeddings",
    )
    binary = r"tools\llama-server\llama-server.exe"
    assert saved_argv(db, "chat", binary) is None
    embed = saved_argv(db, "embedding", binary)
    assert embed is not None
    assert embed[0] == binary
    assert "--embeddings" in embed


def test_launch_button_leaves_a_foreign_listener_and_does_not_start():
    import spock_shell.llama_gui_command as commands
    from model_selector.launch_panel import LaunchPanel

    class Manager:
        def __init__(self):
            self.started = False
            self._instances = {}

        def launch_saved_llama_gui(self, role):
            self.started = True
            return True

        def _terminate_pid_tree(self, pid):
            raise AssertionError(f"foreign listener {pid} was killed")

    class Panel:
        def __init__(self):
            self.manager = Manager()
            self.messages = []

        def _report_llama_gui(self, message):
            self.messages.append(message)

    panel = Panel()
    original = commands.assess_port
    commands.assess_port = lambda port: {
        "action": "refuse",
        "pid": 44,
        "name": "LM Studio.exe",
        "message": (
            "Port 8081 is in use by LM Studio.exe. "
            "That is not llama-server, so it was left running."
        ),
    }
    try:
        LaunchPanel._launch_llama_gui(panel, "chat", 8081)
    finally:
        commands.assess_port = original
    assert panel.manager.started is False
    assert panel.messages
    assert "left running" in panel.messages[0]


def test_foreign_listener_is_refused_and_llama_server_is_killed():
    assert action_for_listener(None) == "free"
    assert (
        action_for_listener(
            {"pid": 9, "name": "LM Studio.exe", "is_llama_server": False}
        )
        == "refuse"
    )
    assert (
        action_for_listener(
            {"pid": 4, "name": "llama-server.exe", "is_llama_server": True}
        )
        == "kill"
    )
