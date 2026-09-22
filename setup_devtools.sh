##########################################################################################
# Based on: 
#   https://github.com/davidheineman/beaker_image/blob/main/Dockerfile
#   https://github.com/davidheineman/fairdev/blob/main/setup_devtools.sh
# 
# missing tools from Ai2:
    # ffmpeg, protobuf-compiler, libsentencepiece-dev, libsqlite3-dev, libssl-dev, iproute2, net-tools, iputils-ping, software-properties-common, openssh-server, weka, psmisc, rename
    # cowsay, figlet, lolcat, neofetch
    # CUDA tooling
    # Docker tooling
    # AWS / GCP tooling
##########################################################################################

set -euo pipefail

export PIXI_HOME="${PIXI_HOME:-$HOME/.pixi}"
LOCAL_BIN="$HOME/.local/bin"

# If $HOME is on a small NFS quota, point the package cache at scratch instead:
#   export PIXI_CACHE_DIR=/scratch/$USER/pixi-cache
export PATH="$PIXI_HOME/bin:$LOCAL_BIN:$HOME/.cargo/bin:$PATH"

log() { printf '\033[1;36m[devtools]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[devtools]\033[0m %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

# -------------
# pixi
# -------------
if ! have pixi; then
    log "Installing pixi into $PIXI_HOME"
    curl -fsSL https://pixi.sh/install.sh | sh
else
    log "pixi already installed: $(command -v pixi)"
fi

PIXI_PKGS=(
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
    tokei
    tree
    uv
    zoxide
    zstd
)

log "Installing ${#PIXI_PKGS[@]} tools via pixi global"
if ! pixi global install --channel conda-forge "${PIXI_PKGS[@]}"; then
    # one unsolvable package fails the whole batch, so retry individually.
    warn "Batch install failed; retrying one package at a time"
    for pkg in "${PIXI_PKGS[@]}"; do
        pixi global install --channel conda-forge "$pkg" || warn "pixi global install $pkg failed"
    done
fi

# The resulting manifest is the portable record of this tool set. Copy it to a
# new cluster and `pixi global sync` reproduces everything above:
log "Manifest: $PIXI_HOME/manifests/pixi-global.toml"

# -------------
# rustup -> ~/.cargo
# -------------
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

# -------------
# uv
# -------------
if have uv; then
    log "Installing Python CLIs via uv tool"
    # Re-installing is a no-op when up to date.
    for tool in pre-commit ruff ipython; do
        uv tool install --quiet "$tool" >/dev/null 2>&1 || warn "uv tool install $tool failed"
    done
else
    warn "uv not found; skipping Python CLIs"
fi

# -------------
# summary
# -------------
log "Done. New tools available in this shell after: hash -r"
log "Quick check:"
hash -r 2>/dev/null || true
for c in "${PIXI_PKGS[@]}"; do
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
