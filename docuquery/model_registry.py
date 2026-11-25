"""Discover local GGUF models, pick a sensible default, and remember the choice.

The registry powers two things:

* ``local_ai.py`` uses it to decide which model to load (explicit flag, saved
  choice, or an automatic pick based on installed RAM and the folders already
  on this laptop, including LM Studio's model library).
* The Profile page uses it to list switchable models and to save a new one.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
MIN_GGUF_MB = 100

LOGGER = logging.getLogger(__name__)


PRESETS: dict[str, dict[str, object]] = {
    "small": {
        "label": "Qwen2.5 0.5B Instruct",
        "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "approx_mb": 400,
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/"
               "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "fallback_url": "https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/"
                        "resolve/main/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf",
    },
    "default": {
        "label": "Qwen2.5 1.5B Instruct",
        "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "approx_mb": 1000,
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
               "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "fallback_url": "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/"
                        "resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
    },
    "large": {
        "label": "Qwen2.5 3B Instruct",
        "file": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "approx_mb": 2000,
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/"
               "qwen2.5-3b-instruct-q4_k_m.gguf",
        "fallback_url": "https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/"
                        "resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
    },
}


# ---------------------------------------------------------------------------
# Filesystem locations
# ---------------------------------------------------------------------------

def models_dir() -> Path:
    override = os.environ.get("MODELS_DIR", "").strip()
    return Path(override) if override else ROOT / "models"


def selection_file() -> Path:
    override = os.environ.get("MODEL_SELECTION_FILE", "").strip()
    return Path(override) if override else models_dir() / "selected.json"


def preset_path(preset: str) -> Path:
    return models_dir() / str(PRESETS[preset]["file"])


def _library_dirs() -> list[tuple[str, Path]]:
    """Folders where other local AI apps keep their GGUF downloads."""
    home = Path.home()
    candidates: list[tuple[str, Path]] = [("this app", models_dir())]
    if sys.platform.startswith("win"):
        candidates.append(("LM Studio", home / ".lmstudio" / "models"))
        candidates.append(("LM Studio", Path(os.environ.get("LOCALAPPDATA", home)) / "LM-Studio" / "models"))
    elif sys.platform == "darwin":
        candidates.append(("LM Studio", home / ".lmstudio" / "models"))
        candidates.append(("LM Studio", home / "Library" / "Application Support" / "LM Studio" / "models"))
    else:
        candidates.append(("LM Studio", home / ".lmstudio" / "models"))
        candidates.append(("LM Studio", home / ".cache" / "lm-studio" / "models"))
    candidates.append(("Bionic", home / ".bionic" / "models"))
    for extra in os.environ.get("EXTRA_MODEL_DIRS", "").split(os.pathsep):
        if extra.strip():
            candidates.append(("custom folder", Path(extra.strip())))
    seen: set[str] = set()
    unique: list[tuple[str, Path]] = []
    for source, path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append((source, path))
    return unique


def ollama_models_dir() -> Path:
    override = os.environ.get("OLLAMA_MODELS", "").strip()
    return Path(override) if override else Path.home() / ".ollama" / "models"


def scan_ollama_models(limit: int = 10) -> list[dict[str, object]]:
    """Ollama stores weights as plain GGUF blobs, so they can be loaded directly."""
    root = ollama_models_dir()
    manifests = root / "manifests"
    blobs = root / "blobs"
    if not manifests.is_dir() or not blobs.is_dir():
        return []
    found: list[dict[str, object]] = []
    try:
        manifest_files = sorted(manifests.rglob("*"))
    except OSError:
        return []
    for manifest in manifest_files:
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8", errors="ignore") or "{}")
        except (OSError, json.JSONDecodeError):
            continue
        tag = manifest.name
        name = manifest.parent.name
        for layer in data.get("layers", []):
            if not isinstance(layer, dict):
                continue
            if layer.get("mediaType") != "application/vnd.ollama.image.model":
                continue
            digest = str(layer.get("digest") or "").replace(":", "-")
            if not digest:
                continue
            blob = blobs / digest
            if not blob.is_file():
                continue
            try:
                size_mb = blob.stat().st_size // (1024 * 1024)
            except OSError:
                continue
            if size_mb < MIN_GGUF_MB:
                continue
            found.append({
                "id": f"file:{blob}",
                "kind": "file",
                "label": f"{name}:{tag} (Ollama)",
                "path": str(blob),
                "size_mb": size_mb,
                "source": "Ollama",
                "downloaded": True,
            })
            break
        if len(found) >= limit:
            break
    return found


def scan_models(limit: int = 20) -> list[dict[str, object]]:
    """Find GGUF files already present on this laptop."""
    found: list[dict[str, object]] = []
    ignored = {str(preset_path(name).resolve()) for name in PRESETS}
    for source, directory in _library_dirs():
        if not directory.is_dir():
            continue
        try:
            paths = sorted(directory.rglob("*.gguf"))
        except OSError:
            continue
        for path in paths:
            try:
                size_mb = path.stat().st_size // (1024 * 1024)
            except OSError:
                continue
            if size_mb < MIN_GGUF_MB or str(path.resolve()) in ignored:
                continue
            found.append({
                "id": f"file:{path}",
                "kind": "file",
                "label": path.stem,
                "path": str(path),
                "size_mb": size_mb,
                "source": source,
                "downloaded": True,
            })
            if len(found) >= limit:
                return found
    # Ollama keeps GGUF weights in a blob store; list them so people can reuse
    # models they already downloaded with another tool.
    known_paths = {str(item["path"]) for item in found}
    for extra in scan_ollama_models(limit=limit - len(found)):
        if extra["path"] not in known_paths:
            found.append(extra)
    return found


# ---------------------------------------------------------------------------
# In-app download of the built-in presets
# ---------------------------------------------------------------------------

_DOWNLOAD = {
    "id": None,
    "label": "",
    "state": "idle",     # idle | downloading | done | error
    "received": 0,
    "total": 0,
    "error": "",
}
_DOWNLOAD_LOCK = threading.Lock()
CHUNK_BYTES = 1024 * 1024


def download_status() -> dict[str, object]:
    with _DOWNLOAD_LOCK:
        snapshot = dict(_DOWNLOAD)
    total = int(snapshot.get("total") or 0)
    received = int(snapshot.get("received") or 0)
    snapshot["percent"] = round(received * 100 / total, 1) if total else None
    snapshot["received_mb"] = round(received / (1024 * 1024), 1)
    snapshot["total_mb"] = round(total / (1024 * 1024), 1) if total else None
    return snapshot


def _set_download(**changes: object) -> None:
    with _DOWNLOAD_LOCK:
        _DOWNLOAD.update(changes)


def download_preset(preset: str, opener=None) -> Path:
    """Fetch a preset GGUF into the models folder (called from a worker thread)."""
    if preset not in PRESETS:
        raise ValueError("Unknown model preset.")
    meta = PRESETS[preset]
    destination = preset_path(preset)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    urls = [str(meta["url"])] + ([str(meta["fallback_url"])] if meta.get("fallback_url") else [])
    open_url = opener or urllib.request.urlopen
    last_error: Exception | None = None
    for url in urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "DocuQuery/offline"})
            with open_url(request, timeout=60) as response:
                total = int(response.headers.get("Content-Length") or 0)
                _set_download(state="downloading", received=0, total=total, error="")
                received = 0
                with open(partial, "wb") as handle:
                    while True:
                        chunk = response.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        handle.write(chunk)
                        received += len(chunk)
                        _set_download(received=received)
            if partial.stat().st_size < MIN_GGUF_MB * 1024 * 1024:
                raise OSError("The downloaded file is smaller than expected.")
            os.replace(partial, destination)
            return destination
        except Exception as exc:  # try the fallback URL, then report
            last_error = exc
            try:
                partial.unlink()
            except OSError:
                pass
    LOGGER.debug("Preset download failed: %s", last_error)
    raise OSError(
        "Download failed — check your internet connection, then click the model again."
    )


def start_download(preset: str) -> dict[str, object]:
    """Begin downloading a preset in the background; safe to call twice."""
    if preset not in PRESETS:
        raise ValueError("Unknown model preset.")
    with _DOWNLOAD_LOCK:
        if _DOWNLOAD["state"] == "downloading":
            return download_status()
        _DOWNLOAD.update({
            "id": preset,
            "label": str(PRESETS[preset]["label"]),
            "state": "downloading",
            "received": 0,
            "total": int(PRESETS[preset]["approx_mb"]) * 1024 * 1024,
            "error": "",
        })

    def worker() -> None:
        try:
            download_preset(preset)
            write_selection("preset", preset, str(PRESETS[preset]["label"]))
            _set_download(state="done")
        except Exception as exc:
            _set_download(state="error", error=str(exc))

    threading.Thread(target=worker, name=f"download-{preset}", daemon=True).start()
    return download_status()


# ---------------------------------------------------------------------------
# Bringing in any other GGUF: a direct link, or the folder on disk
# ---------------------------------------------------------------------------

MIN_CUSTOM_MB = 1
SPACE_HEADROOM_MB = 250


def free_space_mb(path: Path | None = None) -> float:
    """Free megabytes where models are stored, so a download can be refused early."""
    target = path or models_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        return float(round(shutil.disk_usage(target).free / (1024 * 1024)))
    except OSError:
        return 0.0


def suggested_name(url: str, disposition: str = "") -> str:
    """Turn a download link into a safe file name inside the models folder."""
    name = ""
    if disposition:
        match = re.search(r"filename\*?=(?:UTF-8''|[\"'])?([^\";]+)", disposition, re.IGNORECASE)
        if match:
            name = unquote(match.group(1).strip())
    if not name:
        name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" ._")
    if not name.lower().endswith(".gguf"):
        name += ".gguf"
    if name == ".gguf":
        name = "model.gguf"
    return name[:96]


def check_url(url: str) -> str:
    """Only plain http(s) links to a .gguf file are accepted."""
    text = str(url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Paste a direct link that starts with http:// or https://.")
    return text


NOT_GGUF_SUFFIXES = (".safetensors", ".bin", ".pt", ".pth", ".onnx", ".h5", ".msgpack", ".pkl")


def huggingface_token() -> str:
    """Optional read token, so gated GGUF repositories can be downloaded too."""
    for name in ("HF_TOKEN", "HUGGINGFACE_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def reject_original_format(url: str) -> None:
    """Say plainly that safetensors/ONNX files are not usable by a CPU GGUF runner."""
    path = unquote(urlparse(url).path).lower()
    if path.endswith(NOT_GGUF_SUFFIXES):
        raise ValueError(
            "That is the original PyTorch/SafeTensors file, not a GGUF. DocuQuery needs a GGUF "
            "build of the same model — open the model page, look for a GGUF version "
            "(bartowski or lmstudio-community publish them) and copy the .gguf link from there."
        )


def gated_message(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    parts = parsed.path.strip("/").split("/")
    if (host.endswith("huggingface.co") or host.endswith("hf.co")) and len(parts) >= 2:
        repo = f"{parts[0]}/{parts[1]} is a gated model — "
    else:
        repo = "This link needs a signed-in licence acceptance — "
    return (
        f"{repo}Hugging Face asks for it before the file can be downloaded. "
        "Accept the licence on the model page, put HF_TOKEN=your_read_token in .env, then try "
        "again. A public GGUF version of the same model works without a token."
    )


def download_custom(url: str, opener=None, min_mb: int = MIN_CUSTOM_MB) -> Path:
    """Save any GGUF a person links to, straight into the models folder."""
    url = check_url(url)
    reject_original_format(url)
    destination_dir = models_dir()
    destination_dir.mkdir(parents=True, exist_ok=True)
    open_url = opener or urllib.request.urlopen
    host = (urlparse(url).hostname or "").lower()
    headers = {"User-Agent": "DocuQuery/offline"}
    token = huggingface_token()
    if token and (host.endswith("huggingface.co") or host.endswith("hf.co")):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        response = open_url(request, timeout=60)
    except urllib.error.HTTPError as exc:
        LOGGER.debug("Custom model link returned HTTP %s", exc.code)
        if exc.code in (401, 403):
            raise OSError(gated_message(url)) from exc
        if exc.code == 404:
            raise OSError(
                "That link was not found (404). Copy the link again from the model's Files tab."
            ) from exc
        raise OSError(
            "Hugging Face refused the download. Check the link, or accept the model's licence "
            "on its page first."
        ) from exc
    except Exception as exc:
        LOGGER.debug("Custom model link failed: %s", exc)
        raise OSError(
            "Could not reach that link — check your internet connection or the address."
        ) from exc

    with response:
        name = suggested_name(url, str(response.headers.get("Content-Disposition") or ""))
        destination = destination_dir / name
        total = int(response.headers.get("Content-Length") or 0)
        free = free_space_mb(destination_dir)
        if total and free and total / (1024 * 1024) > free - SPACE_HEADROOM_MB:
            _set_download(state="error", error=(
                f"Not enough disk space: this model needs about {round(total / (1024 * 1024))} MB "
                f"and {int(free)} MB is free. Free up space or pick a smaller model."))
            raise OSError(_DOWNLOAD["error"])

        partial = destination.with_suffix(destination.suffix + ".part")
        _set_download(state="downloading", received=0, total=total, error="")
        received = 0
        first = True
        try:
            with open(partial, "wb") as handle:
                while True:
                    chunk = response.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    if first:
                        first = False
                        if not chunk.startswith(b"GGUF"):
                            raise OSError(
                                "That link did not return a GGUF file. Open the model's "
                                "Files tab and copy the link of a .gguf file (a GGUF version "
                                "of the model, not the original SafeTensors weights)."
                            )
                    handle.write(chunk)
                    received += len(chunk)
                    _set_download(received=received)
            if received < min_mb * 1024 * 1024:
                raise OSError("The downloaded file looks too small to be a model.")
            os.replace(partial, destination)
        except Exception:
            try:
                partial.unlink()
            except OSError:
                pass
            raise
    return destination


def start_custom_download(url: str) -> dict[str, object]:
    """Download a linked GGUF in the background and make it the selected model."""
    check_url(url)
    reject_original_format(url)
    with _DOWNLOAD_LOCK:
        if _DOWNLOAD["state"] == "downloading":
            raise ValueError("A model is already downloading — wait for it to finish.")
        _DOWNLOAD.update({
            "id": "custom",
            "label": "Linked model",
            "state": "downloading",
            "received": 0,
            "total": 0,
            "error": "",
        })

    def worker() -> None:
        try:
            path = download_custom(url)
            label = _display_label(path.name)
            write_selection("file", str(path), label)
            _set_download(state="done", id="custom", label=label)
        except Exception as exc:
            _set_download(state="error", error=str(exc))

    threading.Thread(target=worker, name="download-custom", daemon=True).start()
    return download_status()


def reveal_models_dir() -> dict[str, object]:
    """Open the models folder so a .gguf can simply be dropped into it."""
    path = models_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False, timeout=10)
        else:
            subprocess.run(["xdg-open", str(path)], check=False, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.debug("Could not open the models folder: %s", exc)
        return {"ok": False, "path": str(path), "error": "Open the folder yourself: " + str(path)}
    return {"ok": True, "path": str(path)}


# ---------------------------------------------------------------------------
# Hardware recommendation
# ---------------------------------------------------------------------------

def total_ram_gb() -> float:
    try:
        if sys.platform.startswith("win"):
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("avail_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
                return round(status.total_phys / (1024 ** 3), 1)
        elif sys.platform == "darwin":
            output = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                    timeout=5, check=False).stdout.strip()
            return round(int(output) / (1024 ** 3), 1)
        else:
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        return round(int(line.split()[1]) / (1024 ** 2), 1)
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        pass
    return 0.0


def recommend_preset(ram_gb: float | None = None) -> str:
    ram = total_ram_gb() if ram_gb is None else ram_gb
    if ram <= 0:
        return "default"
    if ram >= 14:
        return "large"
    if ram >= 7:
        return "default"
    return "small"


# ---------------------------------------------------------------------------
# Options and saved selection
# ---------------------------------------------------------------------------

def options() -> list[dict[str, object]]:
    recommended = recommend_preset()
    entries: list[dict[str, object]] = []
    for name, meta in PRESETS.items():
        path = preset_path(name)
        entries.append({
            "id": f"preset:{name}",
            "kind": "preset",
            "value": name,
            "label": meta["label"],
            "size_mb": meta["approx_mb"],
            "source": "built-in",
            "downloaded": path.is_file(),
            "recommended": name == recommended,
        })
    entries.extend(scan_models())
    selection = read_selection()
    if selection and selection.get("kind") == "file":
        known = {entry["id"] for entry in entries}
        chosen = f"file:{selection['value']}"
        if chosen not in known and Path(str(selection["value"])).is_file():
            entries.append({
                "id": chosen,
                "kind": "file",
                "label": _display_label(selection.get("label") or selection["value"]),
                "path": str(selection["value"]),
                "size_mb": int(Path(str(selection["value"])).stat().st_size // (1024 * 1024)),
                "source": "selected",
                "downloaded": True,
            })
    return entries


def find_option(option_id: str) -> dict[str, object] | None:
    return next((entry for entry in options() if entry["id"] == option_id), None)


def read_selection() -> dict[str, object] | None:
    path = selection_file()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("kind") not in {"preset", "file"}:
        return None
    if not data.get("value"):
        return None
    return data


def write_selection(kind: str, value: str, label: str = "") -> dict[str, object]:
    if kind not in {"preset", "file"}:
        raise ValueError("Unsupported model selection.")
    if kind == "preset" and value not in PRESETS:
        raise ValueError("Unknown model preset.")
    if kind == "file" and not Path(value).is_file():
        raise ValueError("That model file no longer exists.")
    payload = {"kind": kind, "value": value, "label": label or value}
    path = selection_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def resolve_path(selection: dict[str, object] | None) -> Path | None:
    """Return the GGUF file for a saved selection, if it can be used."""
    if not selection:
        return None
    if selection["kind"] == "preset":
        return preset_path(str(selection["value"]))
    path = Path(str(selection["value"]))
    return path if path.is_file() else None


def selected_id(selection: dict[str, object] | None) -> str | None:
    if not selection:
        return None
    return f"{selection['kind']}:{selection['value']}"


def _display_label(value: object) -> str:
    """Turn a stored path/label into something readable in the model chip."""
    text = str(value or "").strip()
    if not text:
        return ""
    cleaned = text.replace("\\", "/").rstrip("/")
    name = cleaned.rsplit("/", 1)[-1] or text
    return name[:-5] if name.lower().endswith(".gguf") else name


def describe(config: dict[str, object] | None = None) -> dict[str, object]:
    """Everything the Profile page needs to render the model picker."""
    from .llm import model_status

    selection = read_selection()
    ram = total_ram_gb()
    status = model_status(config or {})
    managed = str((config or {}).get("MANAGED_MODEL", "")).lower() == "true"
    return {
        "ram_gb": ram,
        "models_dir": str(models_dir()),
        "free_space_mb": free_space_mb(),
        "recommended": recommend_preset(ram),
        "recommended_label": PRESETS[recommend_preset(ram)]["label"],
        "managed": managed,
        "selected_id": selected_id(selection),
        "selection_kind": selection["kind"] if selection else None,
        "current": {
            "available": status["available"],
            "backend": status["backend"],
            "label": status["label"],
            "model": _display_label(status["model"]),
        },
        "options": options(),
    }
