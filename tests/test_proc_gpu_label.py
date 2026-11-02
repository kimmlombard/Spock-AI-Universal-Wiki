"""GPU label helpers for Live Monitor PID column."""

from spock_onboarding.llama_process import (
    format_pid_gpu,
    gpu_label_from_cvd_and_cmdline,
)


def test_gpu_label_single_cvd():
    assert gpu_label_from_cvd_and_cmdline("0") == "GPU 0"
    assert gpu_label_from_cvd_and_cmdline("1") == "GPU 1"


def test_gpu_label_multi_cvd():
    assert gpu_label_from_cvd_and_cmdline("0,1") == "GPU 0+1"


def test_gpu_label_tensor_split():
    assert gpu_label_from_cvd_and_cmdline("", tensor_split="0.5,0.5") == "multi-GPU"


def test_gpu_label_main_gpu():
    assert gpu_label_from_cvd_and_cmdline("", main_gpu="1") == "GPU 1"


def test_format_pid_gpu():
    assert format_pid_gpu(42) == "pid 42"
    assert format_pid_gpu(42, "GPU 0") == "pid 42 on GPU 0"
    assert format_pid_gpu(7, "0") == "pid 7 on GPU 0"
    assert format_pid_gpu(9, "RTX 3060") == "pid 9 on RTX 3060"
    assert format_pid_gpu(3, "multi-GPU") == "pid 3 on multi-GPU"
