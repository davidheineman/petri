##########################################################################################
# Based on: https://github.com/davidheineman/beaker_image/blob/main/Dockerfile

# missing tools from Ai2:
    # ffmpeg, protobuf-compiler, libsentencepiece-dev, libsqlite3-dev, libssl-dev, iproute2, net-tools, iputils-ping, software-properties-common, openssh-server, weka, psmisc, rename
    # cowsay, figlet, lolcat, neofetch
    # CUDA tooling
    # Docker tooling
    # AWS / GCP tooling
##########################################################################################

set -euo pipefail

DEVTOOLS_ENV="${DEVTOOLS_ENV:-devtools}"
LOCAL_BIN="$HOME/.local/bin"

# Tools we refuse to shadow (system versions take precedence)
SHADOW_DENY=(
    conda
    curl
    g++
    gcc
    git
    gzip
    ld
    make
    mamba
    node
    npm
    npx
    pip
    pip3
    pytest
    python
    python3
    tar
    unzip
    wget
)

log() { printf '\033[1;36m[devtools]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[devtools]\033[0m %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 1. conda env with the bulk of the tools
# ---------------------------------------------------------------------------
if ! have conda; then
    warn "conda not found on PATH; aborting (this host should have /opt/conda)."
    exit 1
fi

# Load conda's shell functions so `conda activate` works inside this script.
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

CONDA_PKGS=(
    bat
    btop
    cmake
    duf
    dust
    eza
    fd-find
    fzf
    gh
    git-lfs
    htop
    hyperfine
    jq
    ncdu
    ninja
    nvtop
    ollama
    pkg-config
    procs
    rclone
    ripgrep
    rsync
    s5cmd
    sd
    sl
    smem
    socat
    starship
    # tmux # only system tmux works
    tokei
    tree
    zoxide
    zstd
)

if ! conda env list | awk '{print $1}' | grep -qx "$DEVTOOLS_ENV"; then
    log "Creating conda env: $DEVTOOLS_ENV"
    conda create -y -n "$DEVTOOLS_ENV" --no-default-packages -c conda-forge --override-channels "${CONDA_PKGS[@]}"
else
    log "Updating conda env: $DEVTOOLS_ENV"
    conda install -y -n "$DEVTOOLS_ENV" -c conda-forge --override-channels "${CONDA_PKGS[@]}"
fi

DEVTOOLS_PREFIX="$(conda env list | awk -v n="$DEVTOOLS_ENV" '$1==n {print $NF}')"
log "devtools env prefix: $DEVTOOLS_PREFIX"

# ---------------------------------------------------------------------------
# 2. rustup → cargo/rustc into ~/.cargo
# ---------------------------------------------------------------------------
if ! have cargo; then
    log "Installing rustup (cargo, rustc)"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --default-toolchain stable --profile minimal --no-modify-path
else
    log "rustup already installed; updating stable toolchain"
    "$HOME/.cargo/bin/rustup" update stable >/dev/null
fi

# Symlink cargo/rustc/rustup into ~/.local/bin so they're on PATH without sourcing env.cargo
mkdir -p "$LOCAL_BIN"
for b in cargo rustc rustup rustdoc; do
    [ -x "$HOME/.cargo/bin/$b" ] && ln -sfn "$HOME/.cargo/bin/$b" "$LOCAL_BIN/$b"
done

# ---------------------------------------------------------------------------
# 3. uv-installed Python CLIs (uv is already in ~/.local/bin)
# ---------------------------------------------------------------------------
if have uv; then
    log "Installing Python CLIs via uv tool"
    # Re-installing is a no-op when up to date.
    for tool in pre-commit ruff ipython; do
        uv tool install --quiet "$tool" >/dev/null 2>&1 || warn "uv tool install $tool failed"
    done
else
    warn "uv not found; skipping Python CLIs"
fi

# ---------------------------------------------------------------------------
# 4. Symlink farm: expose devtools env binaries through ~/.local/bin
#    (~/.local/bin is already on PATH ahead of /usr/bin and /opt/conda/bin)
# ---------------------------------------------------------------------------
log "Linking devtools binaries → $LOCAL_BIN"
shadow_set=" ${SHADOW_DENY[*]} "
linked=0
skipped=0
for src in "$DEVTOOLS_PREFIX/bin/"*; do
    name="$(basename "$src")"
    # Skip anything in the deny-list, and skip non-binaries (python entry points etc.)
    if [[ "$shadow_set" == *" $name "* ]]; then
        skipped=$((skipped+1))
        continue
    fi
    # Only link real executables, not directories
    [ -x "$src" ] && [ ! -d "$src" ] || continue
    ln -sfn "$src" "$LOCAL_BIN/$name"
    linked=$((linked+1))
done
log "Linked $linked binaries (skipped $skipped to avoid shadowing core tools)."

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
log "Done. New tools available in this shell after: hash -r"
log "Quick check:"
hash -r 2>/dev/null || true
for c in "${CONDA_PKGS[@]}"; do
    case "$c" in
        ripgrep) c=rg ;;
        fd-find) c=fd ;;
    esac
    if have "$c"; then
        printf '  \033[1;32m✓\033[0m %-10s %s\n' "$c" "$(command -v "$c")"
    else
        printf '  \033[1;31m✗\033[0m %-10s missing\n' "$c"
    fi
done

# ---------------------------------------------------------------------------
# 6. Additional config options
# ---------------------------------------------------------------------------

# use libmamba for conda package resolution
conda config --set solver libmamba
