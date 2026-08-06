"""Ollama environment detection + model recommendation (Settings page).

Inspects the host (RAM, NVIDIA VRAM, OLLAMA_* environment variables, a running
Ollama server) and recommends the best local model for the glossary workload —
short business-language definitions and JSON-mode classification, so the ladder
is general instruct models, not coder models. Pure logic (recommend) is
separated from probing (detection_report) so it can be unit-tested.

Adapted from Migration Copilot's llm/detect.py (PDI-Migration), which proved
the pattern; kept API-compatible where it matters (parse_nvidia_smi, recommend,
detection_report).
"""
import ctypes
import os
import platform
import subprocess
from typing import Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel

DEFAULT_OLLAMA_URL = "http://localhost:11434"
PROBE_TIMEOUT = 2.0

# Env vars worth surfacing in the settings UI.
OLLAMA_ENV_VARS = (
    "OLLAMA_HOST",
    "OLLAMA_MODELS",
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_NUM_PARALLEL",
    "OLLAMA_MAX_LOADED_MODELS",
    "OLLAMA_FLASH_ATTENTION",
    "OLLAMA_KV_CACHE_TYPE",
    "OLLAMA_SCHED_SPREAD",
)


class Recommendation(BaseModel):
    model: str
    reason: str
    env_suggestions: Dict[str, str] = {}


class OllamaStatus(BaseModel):
    running: bool
    base_url: str
    version: Optional[str] = None
    installed_models: List[str] = []


class DetectionReport(BaseModel):
    platform: str
    ram_gb: Optional[float]
    vram_gb: Optional[float]        # total across all GPUs
    gpu_name: Optional[str]         # e.g. "2× NVIDIA GeForce RTX 3060"
    gpu_count: int = 0
    env: Dict[str, str]
    ollama: OllamaStatus
    recommendation: Recommendation


def ollama_base_url(default: Optional[str] = None) -> str:
    """The Ollama URL to probe: the app's configured URL wins, else OLLAMA_HOST,
    else the default localhost:11434. OLLAMA_HOST is a *listen* address; 0.0.0.0
    means "all interfaces" and is not connectable — clients reach it via
    loopback. Default port if omitted."""
    if default:
        return str(default).rstrip("/")
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return DEFAULT_OLLAMA_URL
    if "://" not in host:
        host = "http://" + host
    host = host.replace("//0.0.0.0", "//127.0.0.1").rstrip("/")
    if host.count(":") < 2:
        host = host + ":11434"
    return host


def total_ram_gb() -> Optional[float]:
    try:
        if platform.system() == "Windows":
            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.dwLength = ctypes.sizeof(MemoryStatusEx)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return round(status.ullTotalPhys / 1024**3, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except Exception:
        return None


def parse_nvidia_smi(output: str) -> Tuple[Optional[str], Optional[float], int]:
    """(display_name, total_vram_gb, gpu_count) from nvidia-smi CSV output.
    Multiple GPUs aggregate VRAM — Ollama layer-splits models across them."""
    lines = [line for line in output.strip().splitlines() if line.strip()]
    if not lines:
        return None, None, 0
    names, total_mb = [], 0.0
    for line in lines:
        name, mem_mb = line.rsplit(",", 1)
        names.append(name.strip())
        total_mb += float(mem_mb)
    count = len(names)
    if count == 1:
        display = names[0]
    elif len(set(names)) == 1:
        display = "%d× %s" % (count, names[0])
    else:
        display = " + ".join(names)
    return display, round(total_mb / 1024, 1), count


def nvidia_gpu() -> Tuple[Optional[str], Optional[float], int]:
    """(display_name, total_vram_gb, gpu_count) via nvidia-smi; (None, None, 0)
    without an NVIDIA GPU."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None, None, 0
        return parse_nvidia_smi(out.stdout)
    except Exception:
        return None, None, 0


def probe_ollama(base_url: Optional[str] = None) -> OllamaStatus:
    base = ollama_base_url(base_url)
    status = OllamaStatus(running=False, base_url=base)
    try:
        with httpx.Client(base_url=base, timeout=PROBE_TIMEOUT) as client:
            status.version = client.get("/api/version").json().get("version")
            status.running = True
            tags = client.get("/api/tags").json()
            status.installed_models = sorted(m["name"] for m in tags.get("models", []))
    except Exception:
        pass
    return status


def recommend(ram_gb: Optional[float], vram_gb: Optional[float],
              gpu_count: int = 1) -> Recommendation:
    """Pick a general instruct model sized to the hardware.

    Glossary enrichment is short-prompt business language + JSON-mode
    classification, so quality scales with general instruct capability; the
    constraint is memory. Multi-GPU rigs aggregate VRAM (Ollama layer-splits
    across cards when OLLAMA_SCHED_SPREAD=1).
    """
    env = {
        "OLLAMA_KEEP_ALIVE": "30m",   # batched passes: keep the model warm between calls
        "OLLAMA_NUM_PARALLEL": "4",   # matches the app's default LLM_WORKERS=4
    }
    multi = gpu_count > 1
    if multi:
        env["OLLAMA_SCHED_SPREAD"] = "1"  # spread layers across all GPUs
    if vram_gb:
        env["OLLAMA_FLASH_ATTENTION"] = "1"
        if vram_gb >= 24:
            split_note = (
                " split across %d GPUs — best definition quality; llama3.1:8b on a "
                "single card is the faster alternative" % gpu_count if multi
                else " fully on GPU — best definition quality"
            )
            return Recommendation(
                model="qwen2.5:32b",
                reason="%s GB total VRAM fits the 32B instruct model%s." % (vram_gb, split_note),
                env_suggestions=env,
            )
        if vram_gb >= 12:
            return Recommendation(
                model="qwen2.5:14b",
                reason="%s GB VRAM fits the 14B instruct model on GPU with headroom for parallel workers." % vram_gb,
                env_suggestions=env,
            )
        if vram_gb >= 6:
            return Recommendation(
                model="llama3.1:8b",
                reason="%s GB VRAM fits the 8B model — strong quality/speed balance for definitions." % vram_gb,
                env_suggestions=env,
            )
        return Recommendation(
            model="llama3.2:3b",
            reason="%s GB VRAM is tight; the 3B model stays fully on GPU." % vram_gb,
            env_suggestions=env,
        )
    if ram_gb and ram_gb >= 32:
        return Recommendation(
            model="llama3.1:8b",
            reason="No NVIDIA GPU detected; %s GB RAM runs the 8B model on CPU (slower but accurate)." % ram_gb,
            env_suggestions=env,
        )
    if ram_gb and ram_gb >= 16:
        return Recommendation(
            model="llama3.2:3b",
            reason="No NVIDIA GPU detected; %s GB RAM suits the 3B model on CPU." % ram_gb,
            env_suggestions=env,
        )
    return Recommendation(
        model="llama3.2:1b",
        reason="Limited memory detected; the 1B model is the safe floor — expect reduced quality.",
        env_suggestions=env,
    )


def detection_report(base_url: Optional[str] = None) -> DetectionReport:
    """Full host report: hardware, OLLAMA_* env, server status and the model
    recommendation. `base_url` (the app's configured Ollama URL) wins over
    OLLAMA_HOST for the server probe."""
    ram = total_ram_gb()
    gpu_name, vram, gpu_count = nvidia_gpu()
    return DetectionReport(
        platform="%s %s" % (platform.system(), platform.release()),
        ram_gb=ram,
        vram_gb=vram,
        gpu_name=gpu_name,
        gpu_count=gpu_count,
        env={k: os.environ[k] for k in OLLAMA_ENV_VARS if os.environ.get(k)},
        ollama=probe_ollama(base_url),
        recommendation=recommend(ram, vram, gpu_count),
    )
