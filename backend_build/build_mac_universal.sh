#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OUTPUT_ROOT="${REPO_ROOT}/desktop_app/backend_dist"
WORK_ROOT="${SCRIPT_DIR}/.pyi_work"

SPEC_FILE="${SCRIPT_DIR}/pyinstaller_backend.spec"

mkdir -p "${OUTPUT_ROOT}" "${WORK_ROOT}"

echo "[backend_build] repo_root: ${REPO_ROOT}"
echo "[backend_build] output_root: ${OUTPUT_ROOT}"

PYTHON_ARM64="python3"
VENV_ARM64="${SCRIPT_DIR}/.venv_arm64"

ensure_venv() {
  local py="$1"
  local venv_dir="$2"
  if [ ! -d "${venv_dir}" ]; then
    echo "[backend_build] create venv: ${venv_dir}"
    ${py} -m venv "${venv_dir}"
  fi
  "${venv_dir}/bin/python" -m pip install --upgrade pip wheel setuptools >/dev/null
  "${venv_dir}/bin/python" -m pip install -r "${REPO_ROOT}/requirements.txt" >/dev/null
  "${venv_dir}/bin/python" -m pip install pyinstaller >/dev/null
}

purge_playwright_local_browsers_in_venv() {
  # If Playwright browsers were previously installed into the playwright package directory
  # (PLAYWRIGHT_BROWSERS_PATH=0), PyInstaller will try to process/codesign those bundles and
  # the build can fail. Always purge that directory before running PyInstaller.
  local arch_label="$1"
  local venv_dir="$2"
  local py="${venv_dir}/bin/python"

  echo "[backend_build] purge playwright .local-browsers in venv (${arch_label})"
  if ! "${py}" -c "import playwright" >/dev/null 2>&1; then
    echo "[backend_build] Playwright not installed; skip purge."
    return 0
  fi

  "${py}" - <<'PY'
import shutil
from pathlib import Path
import playwright

pkg = Path(playwright.__file__).resolve().parent
target = pkg / "driver" / "package" / ".local-browsers"
try:
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
        print(f"[backend_build] purged: {target}")
    else:
        print(f"[backend_build] no local browsers dir: {target}")
except Exception as e:
    print(f"[backend_build] purge failed: {e}")
PY
}

install_playwright_chromium() {
  # Bundle Playwright browsers for offline packaged app.
  #
  # IMPORTANT:
  # Do NOT download browsers into playwright's package directory (i.e. avoid
  # PLAYWRIGHT_BROWSERS_PATH=0 during build), otherwise PyInstaller will pick up
  # `.local-browsers` inside site-packages and try to ad-hoc codesign Chromium
  # app bundles during COLLECT, which can fail (bundle format / nested frameworks).
  #
  # Instead, download browsers into a build-local directory, then copy them into
  # the PyInstaller bundle AFTER PyInstaller completes.
  local arch_label="$1"
  local venv_dir="$2"

  echo "[backend_build] install Playwright Chromium (${arch_label})"
  # Best-effort: if Playwright isn't installed, skip (crawl4ai optional).
  if ! "${venv_dir}/bin/python" -c "import playwright" >/dev/null 2>&1; then
    echo "[backend_build] Playwright not installed in venv; skip browser download."
    return 0
  fi

  # NOTE: this can be large and may take time; respects HTTP_PROXY/HTTPS_PROXY/ALL_PROXY from env.
  local dl_dir="${WORK_ROOT}/playwright-browsers/${arch_label}"
  mkdir -p "${dl_dir}"
  PLAYWRIGHT_BROWSERS_PATH="${dl_dir}" "${venv_dir}/bin/python" -m playwright install chromium
}

ensure_packaged_playwright_browsers() {
  # After PyInstaller, copy downloaded Playwright browsers into bundle.
  # Source is build-local directory (see install_playwright_chromium()).
  local arch_label="$1"
  local venv_dir="$2"
  local bundle_root="$3"
  local src_dir="${WORK_ROOT}/playwright-browsers/${arch_label}"

  python3 - <<'PY' "${arch_label}" "${src_dir}" "${bundle_root}"
import shutil
from pathlib import Path
import sys
from typing import Optional

arch_label, src_dir, bundle_root = sys.argv[1], sys.argv[2], sys.argv[3]
src_dir = Path(src_dir)
bundle_root = Path(bundle_root)
dst_root = bundle_root

def is_nonempty_dir(p: Path) -> bool:
    try:
        return p.exists() and p.is_dir() and any(p.iterdir())
    except Exception:
        return False

src = src_dir.resolve()
if not is_nonempty_dir(src):
    print(f"[backend_build] ({arch_label}) no downloaded playwright browsers at {src}; skip")
    raise SystemExit(0)

# Ensure target directory exists in bundle
target = (dst_root / "_internal" / "playwright" / "driver" / "package" / ".local-browsers")
target.parent.mkdir(parents=True, exist_ok=True)

if target.exists():
    # If empty, replace
    try:
        shutil.rmtree(target)
    except Exception:
        pass

print(f"[backend_build] ({arch_label}) copying playwright browsers into bundle...")
shutil.copytree(src, target)
print(f"[backend_build] ({arch_label}) copied -> {target}")
PY
}

build_arch() {
  local arch_label="$1"       # darwin-arm64 | darwin-x64
  local venv_dir="$2"
  local dist_dir="${OUTPUT_ROOT}/${arch_label}"
  local work_dir="${WORK_ROOT}/${arch_label}"

  mkdir -p "${dist_dir}" "${work_dir}"
  echo "[backend_build] build ${arch_label} -> ${dist_dir}"

  "${venv_dir}/bin/python" -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath "${dist_dir}" \
    --workpath "${work_dir}" \
    "${SPEC_FILE}"
}

normalize_info_plists() {
  # @electron/universal parses every Info.plist as XML (utf8). Some embedded Python frameworks
  # ship binary plists which break parsing. Convert all Info.plist under the built bundle to XML.
  local root_dir="$1"
  if [ ! -d "${root_dir}" ]; then
    return 0
  fi
  if [ ! -x "/usr/bin/plutil" ]; then
    return 0
  fi
  python3 - <<'PY' "${root_dir}"
import os, sys, subprocess
root = sys.argv[1]
paths = []
for base, _dirs, files in os.walk(root):
    for f in files:
        if f == "Info.plist":
            paths.append(os.path.join(base, f))
for p in paths:
    try:
        subprocess.run(["/usr/bin/plutil", "-convert", "xml1", p], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
print(f"[backend_build] normalized Info.plist -> {len(paths)} file(s)")
PY
}

ensure_litellm_tokenizers_init() {
  # LiteLLM uses importlib.resources on `litellm.litellm_core_utils.tokenizers` which is
  # an implicit namespace package (no __init__.py). In PyInstaller, namespace package
  # resource discovery can fail on mac x64. Create an explicit package marker.
  local bundle_root="$1"
  if [ ! -d "${bundle_root}" ]; then
    return 0
  fi
  python3 - <<'PY' "${bundle_root}"
from pathlib import Path
import sys
root = Path(sys.argv[1])
target = root / "_internal" / "litellm" / "litellm_core_utils" / "tokenizers" / "__init__.py"
try:
    if target.parent.exists():
        target.write_text("# added for PyInstaller namespace package compatibility\n", encoding="utf-8")
        print(f"[backend_build] wrote {target}")
except Exception:
    pass
PY
}

sanitize_bundled_llm_config() {
  # Ensure the backend bundle does NOT ship any real API key.
  # We overwrite _internal/config/run_env_config/llm_config.yaml with a sanitized copy
  # of llm_config.example.yaml (blank all api_key fields).
  local bundle_root="$1"
  if [ ! -d "${bundle_root}" ]; then
    return 0
  fi
  python3 - <<'PY' "${bundle_root}"
from pathlib import Path
import re, sys
root = Path(sys.argv[1])
cfg_dir = root / "_internal" / "config" / "run_env_config"
example = cfg_dir / "llm_config.example.yaml"
target = cfg_dir / "llm_config.yaml"
try:
    if not cfg_dir.exists():
        print("[backend_build] sanitize llm_config: config dir missing, skip")
        raise SystemExit(0)
    if example.exists():
        txt = example.read_text(encoding="utf-8", errors="ignore")
    else:
        # fallback: minimal safe template
        txt = "\\n".join([
            "temperature: 0",
            "max_tokens: 0",
            "max_context_window: 200000",
            "base_url: \"\"",
            "api_key: \"\"",
            "models:",
            "- openai/google/gemini-3-flash-preview",
            "multimodal: false",
            "compressor_multimodal: false",
            "",
        ])
    txt = re.sub(r'^(\\s*api_key\\s*:\\s*).*$' , r'\\1\"\"', txt, flags=re.M)
    target.write_text(txt, encoding="utf-8")
    print(f"[backend_build] sanitized {target}")
except Exception as e:
    print(f"[backend_build] sanitize llm_config failed: {e}")
PY
}

HOST_ARCH="$(uname -m || true)"
echo "[backend_build] host_arch: ${HOST_ARCH}"

echo "[backend_build] === arm64 backend ==="
ensure_venv "${PYTHON_ARM64}" "${VENV_ARM64}"
purge_playwright_local_browsers_in_venv "darwin-arm64" "${VENV_ARM64}"
install_playwright_chromium "darwin-arm64" "${VENV_ARM64}"
build_arch "darwin-arm64" "${VENV_ARM64}"
normalize_info_plists "${OUTPUT_ROOT}/darwin-arm64/mlav3-backend"
ensure_litellm_tokenizers_init "${OUTPUT_ROOT}/darwin-arm64/mlav3-backend"
sanitize_bundled_llm_config "${OUTPUT_ROOT}/darwin-arm64/mlav3-backend"
ensure_packaged_playwright_browsers "darwin-arm64" "${VENV_ARM64}" "${OUTPUT_ROOT}/darwin-arm64/mlav3-backend"

if [ "${HOST_ARCH}" = "arm64" ]; then
  echo "[backend_build] === x64 backend (Rosetta) ==="
  if ! arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
    echo "[backend_build] ERROR: Rosetta not available. Install it first:"
    echo "  softwareupdate --install-rosetta --agree-to-license"
    exit 2
  fi

  # IMPORTANT:
  # - Do NOT rely on `python3` in PATH; on Apple Silicon it may be arm64-only (e.g. conda).
  # - Prefer the system /usr/bin/python3 under Rosetta for bootstrapping.
  PYTHON_X64="arch -x86_64 /usr/bin/python3"
  VENV_X64="${SCRIPT_DIR}/.venv_x64"

  # Recreate venv if it exists but isn't runnable under x86_64
  if [ -d "${VENV_X64}" ]; then
    if ! arch -x86_64 "${VENV_X64}/bin/python" -c "import platform; print(platform.machine())" >/dev/null 2>&1; then
      echo "[backend_build] existing venv_x64 is not usable under x86_64; recreating..."
      rm -rf "${VENV_X64}"
    fi
  fi

  if [ ! -d "${VENV_X64}" ]; then
    echo "[backend_build] create x64 venv: ${VENV_X64}"
    ${PYTHON_X64} -m venv "${VENV_X64}"
  fi

  arch -x86_64 "${VENV_X64}/bin/python" -m pip install --upgrade pip wheel setuptools >/dev/null
  arch -x86_64 "${VENV_X64}/bin/python" -m pip install -r "${REPO_ROOT}/requirements.txt" >/dev/null
  arch -x86_64 "${VENV_X64}/bin/python" -m pip install pyinstaller >/dev/null
  # Download Playwright Chromium into driver-local .local-browsers for offline use.
  if arch -x86_64 "${VENV_X64}/bin/python" -c "import playwright" >/dev/null 2>&1; then
    # Purge any legacy `.local-browsers` inside site-packages first (avoid PyInstaller codesign failures).
    echo "[backend_build] purge playwright .local-browsers in venv (darwin-x64)"
    arch -x86_64 "${VENV_X64}/bin/python" - <<'PY'
import shutil
from pathlib import Path
import playwright

pkg = Path(playwright.__file__).resolve().parent
target = pkg / "driver" / "package" / ".local-browsers"
try:
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
        print(f"[backend_build] purged: {target}")
    else:
        print(f"[backend_build] no local browsers dir: {target}")
except Exception as e:
    print(f"[backend_build] purge failed: {e}")
PY

    echo "[backend_build] install Playwright Chromium (darwin-x64)"
    DL_DIR="${WORK_ROOT}/playwright-browsers/darwin-x64"
    mkdir -p "${DL_DIR}"
    PLAYWRIGHT_BROWSERS_PATH="${DL_DIR}" arch -x86_64 "${VENV_X64}/bin/python" -m playwright install chromium
  else
    echo "[backend_build] Playwright not installed in venv_x64; skip browser download."
  fi

  # Build x64 (force x86_64 python execution)
  mkdir -p "${OUTPUT_ROOT}/darwin-x64" "${WORK_ROOT}/darwin-x64"
  echo "[backend_build] build darwin-x64 -> ${OUTPUT_ROOT}/darwin-x64"
  arch -x86_64 "${VENV_X64}/bin/python" -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath "${OUTPUT_ROOT}/darwin-x64" \
    --workpath "${WORK_ROOT}/darwin-x64" \
    "${SPEC_FILE}"
  normalize_info_plists "${OUTPUT_ROOT}/darwin-x64/mlav3-backend"
  ensure_litellm_tokenizers_init "${OUTPUT_ROOT}/darwin-x64/mlav3-backend"
  sanitize_bundled_llm_config "${OUTPUT_ROOT}/darwin-x64/mlav3-backend"
  ensure_packaged_playwright_browsers "darwin-x64" "${VENV_X64}" "${OUTPUT_ROOT}/darwin-x64/mlav3-backend"
else
  echo "[backend_build] host is not arm64; skipping darwin-x64 build."
fi

echo "[backend_build] done."

