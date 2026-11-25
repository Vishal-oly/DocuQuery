#!/usr/bin/env python3
"""Start DocuQuery with a fully local model, downloading it on first run.

Usage:
    python local_ai.py                  # auto-pick a model for this laptop
    python local_ai.py --list-models    # show presets and models found on disk
    python local_ai.py --model small    # 0.5B (fastest) | default 1.5B | large 3B
    python local_ai.py --model-path "C:\\path\\model.gguf"
    python local_ai.py --gpu            # Vulkan build, uses the graphics card
    python local_ai.py --download-only  # prepare files, then exit
    python local_ai.py --no-model       # run the web app without a model

Model choice order: command line, saved choice (Profile page), then a model
picked automatically from the laptop's RAM and the GGUF files it already has
(LM Studio's library is included). While the app runs, choosing another model
on the Profile page swaps it without restarting the web app.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import platform
import runpy
import socket
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docuquery import model_registry as registry  # noqa: E402

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime" / "llama"
MODEL_DIR = ROOT / "models"
PRESETS = registry.PRESETS
DEFAULT_PRESET = "default"
LLAMA_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases"
PINNED_TAG = "b12651"
DEFAULT_PORT = 8080
MIN_MODEL_BYTES = 100 * 1024 * 1024

_child: subprocess.Popen | None = None
_app: subprocess.Popen | None = None


def say(message: str = "") -> None:
    print(message, flush=True)


def _get_json(url: str, timeout: int = 20):
    request = Request(url, headers={"User-Agent": "DocuQuery-setup", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URLs
        return json.load(response)


def download(url: str, dest: Path, label: str) -> None:
    """Download ``url`` to ``dest`` atomically, printing coarse progress."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    request = Request(url, headers={"User-Agent": "DocuQuery-setup"})
    total = 0
    with urlopen(request, timeout=60) as response, part.open("wb") as handle:  # noqa: S310
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        next_mark = 10
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if total >= (1 << 20):
                percent = done * 100 // total
                if percent >= next_mark:
                    say(f"   {label}: {percent}% ({done // (1 << 20)} MB of {total // (1 << 20)} MB)")
                    next_mark = percent - percent % 10 + 10
    if total and part.stat().st_size != total:
        part.unlink(missing_ok=True)
        raise OSError(f"{label} download was incomplete; please run again.")
    part.replace(dest)


# ---------------------------------------------------------------------------
# llama.cpp runtime
# ---------------------------------------------------------------------------

def _arch() -> str:
    machine = (os.environ.get("PROCESSOR_ARCHITECTURE") or platform.machine()).lower()
    return "arm64" if machine in {"arm64", "aarch64"} else "x64"


def runtime_asset_name(tag: str, gpu: bool = False) -> str | None:
    arch = _arch()
    if sys.platform.startswith("win"):
        flavour = "vulkan" if gpu else "cpu"
        return f"llama-{tag}-bin-win-{flavour}-{arch}.zip"
    if sys.platform == "darwin":
        return f"llama-{tag}-bin-macos-{arch}.tar.gz"
    if sys.platform.startswith("linux"):
        flavour = "vulkan-" if gpu else ""
        return f"llama-{tag}-bin-ubuntu-{flavour}{arch}.tar.gz"
    return None


def find_server_exe(root: Path | None = None) -> Path | None:
    root = root or RUNTIME_DIR
    for name in ("llama-server.exe", "llama-server"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    if root.is_dir():
        for candidate in sorted(root.rglob("llama-server*")):
            if candidate.is_file() and candidate.suffix in {"", ".exe"}:
                return candidate
    return None


def _safe_target(target: Path, name: str) -> Path | None:
    destination = (target / name).resolve()
    if destination != target and target not in destination.parents:
        return None
    return destination


def extract_runtime(archive: Path, target: Path | None = None) -> int:
    """Extract a llama.cpp archive, ignoring entries that would escape ``target``."""
    target = target or RUNTIME_DIR
    target.mkdir(parents=True, exist_ok=True)
    resolved = target.resolve()
    written = 0
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                destination = _safe_target(resolved, info.filename)
                if destination is None:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, destination.open("wb") as out:
                    out.write(source.read())
                written += 1
        return written
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if not member.isfile():
                continue
            destination = _safe_target(resolved, member.name)
            if destination is None:
                continue
            source = bundle.extractfile(member)
            if source is None:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source, destination.open("wb") as out:
                out.write(source.read())
            written += 1
    return written


def latest_runtime_source(gpu: bool = False) -> tuple[str, str]:
    """Return (tag, download url) for the newest matching llama.cpp build."""
    override = os.environ.get("LOCAL_AI_RUNTIME_URL", "").strip()
    if override:
        return "custom", override
    try:
        for release in _get_json(f"{LLAMA_API}?per_page=5"):
            tag = release.get("tag_name", "")
            wanted = runtime_asset_name(tag, gpu)
            if not wanted:
                return tag, ""
            for asset in release.get("assets", []):
                if asset.get("name") == wanted:
                    return tag, asset["browser_download_url"]
    except (URLError, OSError, ValueError, KeyError):
        pass
    tag = PINNED_TAG
    name = runtime_asset_name(tag, gpu)
    if not name:
        return tag, ""
    return tag, f"https://github.com/ggml-org/llama.cpp/releases/download/{tag}/{name}"


def ensure_runtime(gpu: bool = False) -> Path | None:
    existing = find_server_exe()
    if existing:
        return existing
    tag, url = latest_runtime_source(gpu)
    if not url:
        say("This platform has no prebuilt llama.cpp build in the automatic setup.")
        say("Use LM Studio or Ollama instead, or install llama.cpp yourself.")
        return None
    say(f"Downloading the llama.cpp runtime ({tag}, about 25 MB) ...")
    suffix = ".zip" if sys.platform.startswith("win") else ".tar.gz"
    archive = RUNTIME_DIR.parent / f"llama-{tag}{suffix}"
    download(url, archive, "runtime")
    count = extract_runtime(archive)
    archive.unlink(missing_ok=True)
    say(f"   runtime ready ({count} files)")
    return find_server_exe()


# ---------------------------------------------------------------------------
# Model files
# ---------------------------------------------------------------------------

def model_ready(path: Path | None = None) -> bool:
    path = path or registry.preset_path(DEFAULT_PRESET)
    if str(path).lower().endswith(".part"):
        return False  # a download still in progress is never a usable model
    if not path.is_file() or path.stat().st_size < MIN_MODEL_BYTES:
        return False
    with path.open("rb") as handle:
        return handle.read(4) == b"GGUF"


def preset_info(preset: str) -> dict[str, object]:
    return PRESETS.get(preset, PRESETS[DEFAULT_PRESET])


def preset_path(preset: str) -> Path:
    return registry.preset_path(preset if preset in PRESETS else DEFAULT_PRESET)


def configured_model_urls(preset: str = DEFAULT_PRESET) -> tuple[str, ...]:
    override = os.environ.get("LOCAL_AI_MODEL_URL", "").strip()
    if override:
        return (override,)
    meta = preset_info(preset)
    return (str(meta["url"]), str(meta["fallback_url"]))


def ensure_model(preset: str = DEFAULT_PRESET) -> Path:
    target = preset_path(preset)
    if model_ready(target):
        say(f"Using the model already downloaded: {target.name}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    label = preset_info(preset)["label"]
    last_error: Exception | None = None
    for url in configured_model_urls(preset):
        try:
            say(f"Downloading {label} (one time only) ...")
            download(url, target, "model")
            if model_ready(target):
                say(f"   model ready: {target}")
                return target
            target.unlink(missing_ok=True)
            last_error = OSError("downloaded file was not a GGUF model")
        except (URLError, OSError) as exc:
            last_error = exc
            say(f"   that mirror failed ({exc}); trying another source if available")
    raise OSError(f"Could not download the model. Last error: {last_error}")


def ready_selection_path(selection: dict[str, object] | None,
                         current: Path | None = None) -> Path | None:
    """The GGUF for a saved choice, but only if it is already on this computer.

    Nothing here downloads: the app's model menu is the only place a model is
    fetched, so starting DocuQuery can never begin a surprise 2 GB download.
    """
    if not selection:
        return None
    if selection.get("kind") == "preset":
        path = preset_path(str(selection.get("value") or ""))
    else:
        value = str(selection.get("value") or "").strip()
        path = Path(value) if value else None
    if path is None or not model_ready(path):
        return None
    if current is not None and path == current:
        return None
    return path


def resolve_choice(choice: dict[str, object] | None, *, allow_download: bool = True) -> Path | None:
    """Turn a saved/CLI choice into a usable GGUF path."""
    if not choice:
        return None
    if choice["kind"] == "preset":
        preset = str(choice["value"])
        path = preset_path(preset)
        if model_ready(path):
            return path
        return ensure_model(preset) if allow_download else None
    path = Path(str(choice["value"]))
    return path if model_ready(path) else None


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def free_port(preferred: int = DEFAULT_PORT) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise OSError("No free local port found for the model server.")


def server_responds(port: int, timeout: float = 1.0) -> bool:
    try:
        _get_json(f"http://127.0.0.1:{port}/v1/models", timeout=timeout)
        return True
    except (URLError, OSError, ValueError):
        return False


def server_command(exe: Path, model: Path, port: int, *, gpu: bool = False,
                   threads: int | None = None, context: int = 6144) -> list[str]:
    threads = threads or max(2, (os.cpu_count() or 4) - 1)
    command = [
        str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
        "-c", str(context), "-t", str(threads),
    ]
    if gpu:
        command += ["-ngl", "99"]
    return command


def start_server(exe: Path, model: Path, port: int, *, gpu: bool = False) -> subprocess.Popen:
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = (log_dir / "local-ai.log").open("w", encoding="utf-8", errors="replace")
    command = server_command(
        exe, model, port, gpu=gpu,
        threads=int(os.environ["LOCAL_AI_THREADS"]) if os.environ.get("LOCAL_AI_THREADS") else None,
        context=int(os.environ.get("LOCAL_AI_CONTEXT", "6144")),
    )
    say("Starting the local model server ...")
    process = subprocess.Popen(  # noqa: S603 - local binary we just downloaded
        command, cwd=str(exe.parent), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
    )
    global _child
    _child = process
    return process


def wait_for_server(port: int, process: subprocess.Popen, timeout: int = 240) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        if server_responds(port):
            return True
        time.sleep(1)
    return False


def _stop(process: subprocess.Popen | None) -> None:
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def stop_server() -> None:
    _stop(_app)
    _stop(_child)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def backend_config() -> dict[str, object]:
    from docuquery.llm import model_status

    return model_status({
        "OLLAMA_ENABLED": os.environ.get("OLLAMA_ENABLED", "true").lower() == "true",
        "OLLAMA_PORT": int(os.environ.get("OLLAMA_PORT", "11434")),
        "OLLAMA_MODEL": os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b").strip(),
        "LLM_BACKEND": os.environ.get("LLM_BACKEND", "auto").strip().lower(),
        "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1").strip(),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL", "").strip(),
    })


def write_env_file(port: int) -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        return
    env_path.write_text(
        "# Written by local_ai.py on first run.\n"
        "LLM_BACKEND=openai\n"
        f"OPENAI_BASE_URL=http://127.0.0.1:{port}/v1\n"
        "OPENAI_MODEL=\n",
        encoding="utf-8",
    )


def launch_app() -> None:
    say("")
    say(f"DocuQuery starting at http://127.0.0.1:{os.environ.get('PORT', '5000')}")
    say("Keep this window open. Press Ctrl+C to stop the app.")
    say("")
    sys.argv = ["run.py"]
    runpy.run_path(str(ROOT / "run.py"), run_name="__main__")


def choose_model(args) -> tuple[dict[str, object] | None, str]:
    """Resolve the model to load and describe where that decision came from."""
    if getattr(args, "model_path", None):
        return {"kind": "file", "value": str(Path(args.model_path).expanduser())}, "command line"
    if getattr(args, "model", None):
        return {"kind": "preset", "value": args.model}, "command line"
    preset = os.environ.get("LOCAL_AI_PRESET", "").strip()
    if preset in PRESETS:
        return {"kind": "preset", "value": preset}, "LOCAL_AI_PRESET"
    saved = registry.read_selection()
    if saved:
        return saved, "your saved choice"
    preset = registry.recommend_preset()
    return {"kind": "preset", "value": preset}, "automatic pick"


def describe_model(choice: dict[str, object] | None, path: Path | None) -> str:
    if choice and choice["kind"] == "preset":
        return str(preset_info(str(choice["value"]))["label"])
    return path.stem if path else "unknown model"


def list_models() -> int:
    ram = registry.total_ram_gb()
    say(f"Detected memory: {ram or 'unknown'} GB")
    say(f"Recommended for this laptop: {PRESETS[registry.recommend_preset(ram)]['label']}")
    say("")
    for entry in registry.options():
        mark = "downloaded" if entry["downloaded"] else "not downloaded"
        source = entry["source"]
        say(f"  {entry['label']}")
        say(f"      {entry['size_mb']} MB · {mark} · {source} · id: {entry['id']}")
    return 0


def supervise(port: int, exe: Path, choice: dict[str, object] | None,
              path: Path | None, gpu: bool) -> int:
    """Run the web app and start or swap the model whenever one is available.

    ``path`` may be ``None``: DocuQuery then opens with citation-only answers and
    picks up the model by itself as soon as a download from the app finishes.
    """
    server = None
    if path is not None:
        server = start_server(exe, path, port, gpu=gpu)
        if not wait_for_server(port, server):
            say("The model server did not start; see logs/local-ai.log")
            return 1
        say(f"Model ready: {describe_model(choice, path)} on http://127.0.0.1:{port}/v1")
        say("Switch models any time from the Profile page in the app.")
    else:
        say("No model loaded yet — waiting for one to be downloaded in the app.")

    os.environ["DOCUQUERY_MANAGED_MODEL"] = "true"
    os.environ["MODELS_DIR"] = str(registry.models_dir())
    global _app
    _app = subprocess.Popen([sys.executable, str(ROOT / "run.py")])  # noqa: S603
    say("")
    say(f"DocuQuery starting at http://127.0.0.1:{os.environ.get('PORT', '5000')}")
    say("Keep this window open. Press Ctrl+C to stop the app.")
    say("")

    try:
        while _app.poll() is None:
            time.sleep(2)
            wanted = registry.read_selection()
            new_path = ready_selection_path(wanted, path)
            if new_path is None:
                continue
            say("")
            say(("Starting " if server is None else "Switching to ")
                + f"{describe_model(wanted, new_path)} ...")
            _stop(server)
            server, path, choice = start_server(exe, new_path, port, gpu=gpu), new_path, wanted
            if wait_for_server(port, server):
                say(f"Now using {describe_model(choice, path)}")
            else:
                say("The new model did not start; see logs/local-ai.log")
    except KeyboardInterrupt:
        pass
    finally:
        stop_server()
    return _app.returncode or 0


def prepare(port: int, choice: dict[str, object] | None, gpu: bool = False,
            allow_download: bool = False) -> tuple[Path, Path | None] | None:
    """Return (runtime, model). The model is None when nothing is on disk yet."""
    exe = ensure_runtime(gpu)
    if not exe:
        return None
    return exe, resolve_choice(choice, allow_download=allow_download)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DocuQuery with a local model.")
    parser.add_argument("--download-only", action="store_true",
                        help="download the runtime and model, then exit")
    parser.add_argument("--no-model", action="store_true",
                        help="skip model setup and start the app in preview mode")
    parser.add_argument("--list-models", action="store_true",
                        help="show the models available on this laptop")
    parser.add_argument("--model", choices=sorted(PRESETS),
                        help="small = 0.5B (fastest), default = 1.5B, large = 3B")
    parser.add_argument("--model-path", help="run a GGUF file already on this computer")
    parser.add_argument("--gpu", action="store_true",
                        help="use the Vulkan build so the GPU accelerates answers")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LOCAL_AI_PORT", DEFAULT_PORT)),
                        help="port for the local model server (default 8080)")
    args = parser.parse_args()

    if args.list_models:
        return list_models()

    atexit.register(stop_server)

    if args.no_model:
        launch_app()
        return 0

    choice, origin = choose_model(args)
    status = backend_config()
    if status["available"] and not args.model and not args.model_path:
        say(f"Using the model server already running: {status['label']} ({status['model']})")
        say("Start this app with --model or --model-path to run a model from here instead.")
        launch_app()
        return 0

    port = free_port(args.port)
    if args.download_only:
        prepared = prepare(port, choice, args.gpu, allow_download=True)
        return 0 if prepared else 1

    # Only an explicit request (--model / --model-path / LOCAL_AI_PRESET) may
    # download. A plain start.bat never fetches gigabytes on its own.
    explicit = bool(args.model or args.model_path or os.environ.get("LOCAL_AI_PRESET", "").strip())
    prepared = prepare(port, choice, args.gpu, allow_download=explicit)
    if not prepared:
        say("")
        say("Continuing without a model: uploads, extraction and citation previews still work.")
        say("Start LM Studio/Ollama and run this again to get generated summaries.")
        launch_app()
        return 0

    exe, path = prepared
    if path is None:
        say("")
        say("No model is downloaded yet, so DocuQuery starts without one.")
        say("In the app open Profile -> AI model and download any model there.")
        say("It starts answering on its own as soon as the download finishes.")
        say("")
        if choice and choice.get("kind") == "preset":
            say(f"Suggested for this laptop: {preset_info(str(choice['value']))['label']}")
    else:
        say(f"Model selected by {origin}: {describe_model(choice, path)}")
    os.environ["LLM_BACKEND"] = "openai"
    os.environ["OPENAI_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
    os.environ["OPENAI_MODEL"] = ""
    write_env_file(port)
    return supervise(port, exe, choice, path, args.gpu)


if __name__ == "__main__":
    raise SystemExit(main())
