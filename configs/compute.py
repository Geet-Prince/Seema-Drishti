"""Shared compute-backend auto-switch for IBVAP.

Detects the best inference backend at runtime so the same codebase runs fast on
both Apple Silicon (MacBook M5) and NVIDIA discrete GPUs (TensorRT/CUDA):

  NVIDIA GPU + CUDA torch  -> TensorRT .engine (FP16) if available/built,
                             else CUDA FP16 with torch.compile fallback.
  NVIDIA GPU, CPU-only torch -> CPU + clear upgrade hint (TensorRT needs the
                             CUDA-enabled torch build, not torch+cpu).
  Apple Silicon (Darwin)    -> CPU for YOLO (PyTorch MPS is not thread-safe and
                             aborts sustained video inference), CoreML for ONNX.
  Anything else             -> CPU.

Environment overrides (all optional):
  IBVAP_DEVICE=cpu|cuda|mps        Force a torch device (cuda == cuda:0).
  IBVAP_IMGSZ=640                  YOLO inference image size (480 = faster).
  IBVAP_TRT_ENGINE=<path>          TensorRT engine location.
  IBVAP_TORCH_THREADS=4            Cap CPU thread usage for inference.
  IBVAP_NO_TRT_EXPORT=1            Never try to (re)build a TensorRT engine.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess

logger = logging.getLogger(__name__)


# ── GPU presence probes ───────────────────────────────────────────────────

def nvidia_gpu_present() -> tuple[bool, str]:
    """Return (present, gpu_name) for NVIDIA hardware.

    Uses torch.cuda first, then nvidia-smi, then pynvml, so an NVIDIA card is
    still detected when the installed torch build is CPU-only (the common
    reason for unexpectedly low FPS on NVIDIA laptops).
    """
    # 1. Functional CUDA via torch.
    try:
        import torch

        if torch.cuda.is_available():
            try:
                name = torch.cuda.get_device_name(0)
            except Exception:
                name = "NVIDIA GPU"
            return True, name
    except Exception:
        pass

    # 2. nvidia-smi binary (works even with torch+cpu installed).
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run(
                [smi, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if out.returncode == 0 and out.stdout.strip():
                return True, out.stdout.strip().splitlines()[0].strip()
            return True, "NVIDIA GPU"
        except Exception:
            return True, "NVIDIA GPU"

    # 3. NVML bindings (pynvml / nvidia-ml-py), if installed.
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass
        return True, name
    except Exception:
        pass

    return False, ""


def torch_cuda_working() -> bool:
    """True only when the installed torch can actually run CUDA kernels."""
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


# ── Main resolver ─────────────────────────────────────────────────────────

def detect_compute() -> dict:
    """Pick the best compute backend for this host.

    Returns dict with keys:
      device      torch device string: "cuda:0" | "mps" | "cpu"
      backend     "cuda" | "mps" | "cpu"  (TensorRT is layered on top of cuda)
      use_half    True only for real CUDA (FP16 is slower/broken on CPU/MPS)
      use_trt     True when a TensorRT engine may be attempted (NVIDIA,
                  non-Darwin, CUDA torch working)
      gpu_name    NVIDIA card name or "" when none detected
      torch_cuda  torch.cuda.is_available()
      note        human-readable explanation / upgrade hint
    """
    forced = os.environ.get("IBVAP_DEVICE", "").strip().lower()
    if forced in ("cpu", "cuda", "cuda:0", "mps"):
        device = "cuda:0" if forced == "cuda" else forced
        return {
            "device": device,
            "backend": "cuda" if device.startswith("cuda") else device,
            "use_half": device.startswith("cuda") and torch_cuda_working(),
            "use_trt": device.startswith("cuda")
            and torch_cuda_working()
            and platform.system() != "Darwin",
            "gpu_name": "",
            "torch_cuda": torch_cuda_working(),
            "note": f"device forced via IBVAP_DEVICE={forced}",
        }

    cuda_ok = torch_cuda_working()
    if cuda_ok and platform.system() != "Darwin":
        try:
            import torch

            gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            gpu_name = "NVIDIA GPU"
        return {
            "device": "cuda:0",
            "backend": "cuda",
            "use_half": True,
            "use_trt": True,
            "gpu_name": gpu_name,
            "torch_cuda": True,
            "note": f"NVIDIA CUDA active ({gpu_name})",
        }

    nvidia, gpu_name = nvidia_gpu_present()
    if nvidia and not cuda_ok:
        # The classic trap: RTX card present but `pip install torch` gave the
        # CPU-only wheel, so everything silently runs on CPU.
        return {
            "device": "cpu",
            "backend": "cpu",
            "use_half": False,
            "use_trt": False,
            "gpu_name": gpu_name,
            "torch_cuda": False,
            "note": (
                f"{gpu_name} detected but installed torch is CPU-only; "
                "running on CPU. For GPU speed: "
                "pip install torch --index-url "
                "https://download.pytorch.org/whl/cu121 "
                "(then TensorRT export becomes available)."
            ),
        }

    # NOTE: PyTorch MPS is NOT thread-safe and aborts sustained YOLO video
    # inference on macOS (command-buffer assertion). Force CPU on Darwin for
    # stability; set IBVAP_DEVICE=mps to opt back in at your own risk.
    if platform.system() == "Darwin":
        return {
            "device": "cpu",
            "backend": "cpu",
            "use_half": False,
            "use_trt": False,
            "gpu_name": "",
            "torch_cuda": False,
            "note": "macOS: CPU forced for YOLO stability (MPS aborts); "
            "CoreML still used for ONNX/face models",
        }

    try:
        import torch

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return {
                "device": "mps",
                "backend": "mps",
                "use_half": False,
                "use_trt": False,
                "gpu_name": "",
                "torch_cuda": False,
                "note": "Apple Silicon GPU via MPS (non-Darwin host)",
            }
    except Exception:
        pass

    return {
        "device": "cpu",
        "backend": "cpu",
        "use_half": False,
        "use_trt": False,
        "gpu_name": "",
        "torch_cuda": False,
        "note": "no accelerated backend found; using CPU",
    }


def resolve_yolo_settings(config_device: str | None = None) -> dict:
    """Resolve {device, half, imgsz} for Ultralytics YOLO calls.

    config_device "auto"/None/"" -> auto-detect. Explicit values are honored
    except half is still gated on working CUDA (FP16 on CPU/MPS hurts).
    """
    cfg = (config_device or "auto").strip().lower()
    if cfg in ("", "auto"):
        info = detect_compute()
        device, half = info["device"], info["use_half"]
    else:
        device = "cuda:0" if cfg == "cuda" else cfg
        half = device.startswith("cuda") and torch_cuda_working()
    try:
        imgsz = int(os.environ.get("IBVAP_IMGSZ", "640"))
    except ValueError:
        imgsz = 640
    if imgsz not in (320, 416, 480, 640, 800, 960, 1280):
        imgsz = 640
    return {"device": device, "half": half, "imgsz": imgsz}


def resolve_onnx_providers() -> tuple[list[str], int]:
    """Ordered ONNX Runtime providers filtered to what is actually available.

    Prefers TensorRT -> CUDA -> CoreML -> CPU. Returns (providers, ctx_id)
    where ctx_id is 0 for CUDA-backed execution, else -1.
    """
    try:
        import onnxruntime as ort

        available = set(ort.get_available_providers())
    except Exception:
        return ["CPUExecutionProvider"], -1
    preferred = [
        "TensorRTExecutionProvider",
        "CUDAExecutionProvider",
        "CoreMLExecutionProvider",
        "CPUExecutionProvider",
    ]
    providers = [p for p in preferred if p in available]
    if not providers:
        providers = ["CPUExecutionProvider"]
    ctx_id = 0 if providers[0] in (
        "TensorRTExecutionProvider",
        "CUDAExecutionProvider",
    ) else -1
    return providers, ctx_id


def apply_torch_thread_limits() -> None:
    """Cap CPU thread usage so decode/render threads don't starve inference.

    Same bounds work on M5 (efficiency cores) and NVIDIA hosts. Tune via
    IBVAP_TORCH_THREADS (default 4).
    """
    try:
        import torch

        n = int(os.environ.get("IBVAP_TORCH_THREADS", "4"))
        if n >= 1:
            torch.set_num_threads(n)
            torch.set_num_interop_threads(1)
    except Exception:
        pass


def ensure_trt_engine(pt_path: str, engine_path: str | None = None,
                      imgsz: int = 640) -> str:
    """Return the best YOLO weight file to load (TensorRT-aware).

    - Engine exists and TRT is usable -> engine path.
    - Engine exists but unusable (wrong GPU / no CUDA torch) -> .pt fallback.
    - No engine but CUDA torch works -> try one-time export, fall back to .pt
      on any failure. Never raises.
    """
    import pathlib

    default_engine = (
        pathlib.Path(engine_path)
        if engine_path
        else pathlib.Path(pt_path).with_suffix(".engine")
    )
    info = detect_compute()
    if default_engine.exists():
        if info["use_trt"]:
            logger.info("TensorRT engine found: %s", default_engine)
            return str(default_engine)
        logger.info(
            "TensorRT engine at %s not usable here (%s); using %s",
            default_engine, info["note"], pt_path,
        )
        return pt_path
    if not info["use_trt"] or os.environ.get("IBVAP_NO_TRT_EXPORT") == "1":
        return pt_path
    try:
        from ultralytics import YOLO

        logger.info(
            "Exporting TensorRT FP16 engine from %s (one-time, ~1-3 min)...",
            pt_path,
        )
        exported = YOLO(pt_path).export(
            format="engine", half=True, dynamic=True, batch=4,
            imgsz=imgsz, workspace=2,
        )
        # export() returns the engine path; move it to the expected location.
        try:
            import shutil as _shutil

            if str(exported) != str(default_engine):
                _shutil.move(str(exported), str(default_engine))
        except Exception:
            pass
        if default_engine.exists():
            logger.info("TensorRT engine ready: %s", default_engine)
            return str(default_engine)
        if exported and pathlib.Path(str(exported)).exists():
            return str(exported)
    except Exception as exc:
        logger.warning("TensorRT export failed (%s); using %s", exc, pt_path)
    return pt_path


def engine_report(engine_path: str, pt_path: str = "") -> dict:
    """Inspect a TensorRT engine file without needing a GPU.

    Returns {exists, size_mb, looks_valid, header, usable_here, note}.
    A full load test still needs CUDA torch + TensorRT installed.
    """
    import pathlib

    p = pathlib.Path(engine_path)
    report: dict = {
        "path": str(engine_path),
        "exists": p.exists(),
        "size_mb": 0.0,
        "looks_valid": False,
        "header": "",
        "usable_here": False,
        "note": "",
    }
    if not p.exists():
        report["note"] = "engine file not found"
        return report
    try:
        report["size_mb"] = round(p.stat().st_size / (1024 * 1024), 1)
        with open(p, "rb") as f:
            head = f.read(4096)  # metadata header only; file can be 100s of MB
        # Ultralytics-exported engines embed a JSON metadata header.
        try:
            text = head.decode("utf-8", "replace")
            start = text.find("{")
            if start != -1:
                import json as _json

                decoder = _json.JSONDecoder()
                meta, _ = decoder.raw_decode(text[start:])
                report["header"] = str(meta.get("description", ""))[:120]
                report["looks_valid"] = True
            else:
                report["looks_valid"] = len(head) > 0
        except Exception:
            report["looks_valid"] = len(head) > 0
    except Exception as exc:
        report["note"] = f"could not read file: {exc}"
        return report
    info = detect_compute()
    report["usable_here"] = bool(info["use_trt"])
    if info["use_trt"]:
        report["note"] = ("valid engine file; CUDA torch present — "
                          "pipeline will load it (or rebuild if the "
                          "GPU rejects it).")
    else:
        report["note"] = ("file looks OK but cannot be used here yet: "
                          + info["note"])
    return report


if __name__ == "__main__":
    import json as _json

    _info = detect_compute()
    print("=== Compute backend ===")
    print(_json.dumps(_info, indent=1))
    print("=== ONNX providers ===")
    print(resolve_onnx_providers())
    print("=== YOLO settings ===")
    print(resolve_yolo_settings(os.environ.get("IBVAP_DEVICE") or "auto"))
    import sys as _sys

    _eng = os.environ.get("IBVAP_TRT_ENGINE", "yolov8s.engine")
    if len(_sys.argv) > 1:
        _eng = _sys.argv[1]
    print("=== TensorRT engine ===")
    print(_json.dumps(engine_report(_eng), indent=1))
