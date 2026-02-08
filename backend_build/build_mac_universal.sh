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

HOST_ARCH="$(uname -m || true)"
echo "[backend_build] host_arch: ${HOST_ARCH}"

echo "[backend_build] === arm64 backend ==="
ensure_venv "${PYTHON_ARM64}" "${VENV_ARM64}"
build_arch "darwin-arm64" "${VENV_ARM64}"

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

  # Build x64 (force x86_64 python execution)
  mkdir -p "${OUTPUT_ROOT}/darwin-x64" "${WORK_ROOT}/darwin-x64"
  echo "[backend_build] build darwin-x64 -> ${OUTPUT_ROOT}/darwin-x64"
  arch -x86_64 "${VENV_X64}/bin/python" -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath "${OUTPUT_ROOT}/darwin-x64" \
    --workpath "${WORK_ROOT}/darwin-x64" \
    "${SPEC_FILE}"
else
  echo "[backend_build] host is not arm64; skipping darwin-x64 build."
fi

echo "[backend_build] done."

