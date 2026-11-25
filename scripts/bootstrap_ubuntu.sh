#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."

profile=core
install_system=false
init=false
while (($#)); do
    case "$1" in
        --profile)
            profile=${2:?Expected core or zephyr}
            shift ;;
        --install-system-deps) install_system=true ;;
        --init) init=true ;;
        --help|-h)
            printf '%s\n' \
                'Usage: bash scripts/bootstrap_ubuntu.sh [--profile core|zephyr] [--install-system-deps] [--init]' \
                'Default: check dependencies only. --init creates a project-owned venv and verifies pinned inputs.' \
                '--install-system-deps uses sudo for Ubuntu apt packages. ROS is configured separately.'
            exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
    shift
done
case "$profile" in core|zephyr) ;; *) printf 'Unknown profile: %s\n' "$profile" >&2; exit 2 ;; esac
if ((EUID == 0)); then
    printf '%s\n' 'Run as your normal Ubuntu user. The system-install flag invokes sudo itself.' >&2
    exit 2
fi

packages=(ca-certificates curl git gcc g++ cmake ninja-build python3 python3-venv python3-tk
    gcc-arm-none-eabi binutils-arm-none-eabi qemu-system-arm gdb-multiarch)
if [[ "$profile" == zephyr ]]; then
    packages+=(device-tree-compiler)
fi
if "$install_system"; then
    . /etc/os-release
    if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 ]]; then
        printf '%s\n' 'Automatic apt installation supports Ubuntu 24.04 only.' >&2
        exit 2
    fi
    printf '%s\n' '+ sudo apt-get update'
    sudo apt-get update
    printf '+ sudo apt-get install --assume-yes --no-install-recommends'; printf ' %q' "${packages[@]}"; printf '\n'
    sudo apt-get install --assume-yes --no-install-recommends "${packages[@]}"
fi

if ! "$init"; then
    exec /usr/bin/python3 scripts/vel.py doctor --profile "$profile"
fi
if [[ "$(uname -m)" != x86_64 ]] || ! /usr/bin/python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3,12))'; then
    printf '%s\n' 'The project Python locks target Ubuntu x86_64 with system Python 3.12.' >&2
    exit 2
fi

venv="$PWD/build/venvs/$profile"
log_dir="$PWD/build/bootstrap"
mkdir -p -- "$log_dir"
log=$(mktemp "$log_dir/$profile.XXXXXX.log")
printf 'Bootstrap log: %s\n' "$log"
trap 'rc=$?; printf "Bootstrap failed (exit %s). See %s. Check doctor and docs/installation.md.\n" "$rc" "$log" >&2' ERR
(
    unset PYTHONPATH PYTHONHOME VEL_PYTHON_PACKAGES
    /usr/bin/python3 -m venv "$venv"
    py="$venv/bin/python"
    site=$("$py" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
    if [[ "$profile" == zephyr ]]; then
        "$py" -m pip --disable-pip-version-check --timeout 30 install --require-hashes -r zephyr/requirements-build-lock.txt
        "$py" -m pip --disable-pip-version-check --timeout 30 install --require-hashes --no-build-isolation -r zephyr/requirements-lock.txt
        env PATH="$venv/bin:$PATH" VEL_PYTHON_PACKAGES="$site" "$py" scripts/setup_stage4.py --install
    else
        "$py" -m pip --disable-pip-version-check --timeout 30 install --require-hashes -r host/modbus_master/requirements.txt
    fi
    "$py" -m pip check
    printf 'export PATH=%q:$PATH\nexport VEL_PYTHON_PACKAGES=%q\n' "$venv/bin" "$site" > "$venv/vel-env.sh"
    env PATH="$venv/bin:$PATH" VEL_PYTHON_PACKAGES="$site" "$py" scripts/vel.py doctor --profile "$profile"
) 2>&1 | tee -- "$log"
printf 'Activate the project toolset with: source %q\n' "$venv/vel-env.sh"
