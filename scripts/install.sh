#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Decepticon — One-line installer
#
# Usage:
#   curl -fsSL https://decepticon.red/install | bash
#
# Environment variables:
#   VERSION              — Install a specific version (default: latest)
#   DECEPTICON_HOME      — Install directory (default: ~/.decepticon)
#   SKIP_PULL            — Skip Docker image pull (default: false)
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Constants ─────────────────────────────────────────────────────
REPO="PurpleAILAB/Decepticon"
BRANCH="${BRANCH:-main}"
RAW_BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[0;2m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────
info()    { echo -e "${DIM}$*${NC}"; }
success() { echo -e "${GREEN}$*${NC}"; }
warn()    { echo -e "${YELLOW}$*${NC}"; }
error()   { echo -e "${RED}$*${NC}" >&2; }
bold()    { echo -e "${BOLD}$*${NC}"; }

# ── Pre-flight checks ────────────────────────────────────────────
preflight() {
    # curl
    if ! command -v curl >/dev/null 2>&1; then
        error "Error: curl is required but not installed."
        exit 1
    fi

    # Docker
    if ! command -v docker >/dev/null 2>&1; then
        error "Error: Docker is required but not installed."
        echo -e "${DIM}Install Docker: ${NC}https://docs.docker.com/get-docker/"
        exit 1
    fi

    # Docker daemon
    if ! docker info >/dev/null 2>&1; then
        error "Error: Docker daemon is not running."
        echo -e "${DIM}Start Docker and re-run the installer.${NC}"
        exit 1
    fi

    # Docker Compose v2
    if ! docker compose version >/dev/null 2>&1; then
        error "Error: Docker Compose v2 is required."
        echo -e "${DIM}Docker Compose is included with Docker Desktop.${NC}"
        echo -e "${DIM}For Linux: ${NC}https://docs.docker.com/compose/install/linux/"
        exit 1
    fi
}

# ── Version resolution ───────────────────────────────────────────
resolve_version() {
    if [[ -n "${VERSION:-}" ]]; then
        DECEPTICON_VERSION="$VERSION"
        return
    fi

    info "Fetching latest version..."
    local latest
    latest=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" \
        | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')

    if [[ -z "$latest" ]]; then
        # No releases yet — use branch
        DECEPTICON_VERSION="latest"
        info "No releases found, using latest from $BRANCH branch."
    else
        DECEPTICON_VERSION="$latest"
        # Pin config downloads to the release tag (not the moving main branch)
        RAW_BASE="https://raw.githubusercontent.com/$REPO/v$DECEPTICON_VERSION"
    fi
}

# ── Download files ────────────────────────────────────────────────
download_files() {
    local install_dir="$1"

    info "Downloading configuration files..."

    # docker-compose.yml (always overwrite — this is infrastructure, not user config)
    curl -fsSL "$RAW_BASE/docker-compose.yml" -o "$install_dir/docker-compose.yml"

    # .env (only if not exists — never overwrite user's API keys)
    if [[ ! -f "$install_dir/.env" ]]; then
        curl -fsSL "$RAW_BASE/.env.example" -o "$install_dir/.env"
        # Inject the actual install path (Docker Compose can't expand ~)
        echo "DECEPTICON_HOME=$install_dir" >> "$install_dir/.env"
        info "Created .env from template. You'll need to add your API keys."
    else
        # Ensure DECEPTICON_HOME is set in existing .env (upgrade path)
        if ! grep -q "^DECEPTICON_HOME=" "$install_dir/.env" 2>/dev/null; then
            echo "DECEPTICON_HOME=$install_dir" >> "$install_dir/.env"
        fi
        info ".env already exists, preserving your configuration."
    fi

    # LiteLLM config
    mkdir -p "$install_dir/config"
    curl -fsSL "$RAW_BASE/config/litellm.yaml" -o "$install_dir/config/litellm.yaml"

    # Workspace directory (bind-mounted into containers)
    mkdir -p "$install_dir/workspace"

    # Version marker
    echo "$DECEPTICON_VERSION" > "$install_dir/.version"
}

# ── Download launcher binary ─────────────────────────────────────
create_launcher() {
    local bin_dir="$1"
    local install_dir="$2"

    mkdir -p "$bin_dir"

    # Detect OS and architecture
    local os arch
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m)
    case "$arch" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64" ;;
        arm64)   arch="arm64" ;;
        *)
            error "Unsupported architecture: $arch"
            exit 1
            ;;
    esac

    local binary_name="decepticon-${os}-${arch}"
    local download_url

    if [[ "$DECEPTICON_VERSION" == "latest" ]]; then
        info "Downloading launcher script (no release binary available)..."
        curl -fsSL "$RAW_BASE/scripts/launcher.sh" -o "$bin_dir/decepticon"
    else
        download_url="https://github.com/$REPO/releases/download/v${DECEPTICON_VERSION}/${binary_name}"
        info "Downloading launcher binary ($binary_name)..."
        if ! curl -fsSL "$download_url" -o "$bin_dir/decepticon" 2>/dev/null; then
            warn "Binary not available, falling back to launcher script..."
            curl -fsSL "$RAW_BASE/scripts/launcher.sh" -o "$bin_dir/decepticon"
        fi
    fi

    chmod 755 "$bin_dir/decepticon"
}

# ── Detect stale `decepticon` in PATH ─────────────────────────────
# A previous install via `npm link`, manual symlink, or alternate package
# manager can leave a `decepticon` executable elsewhere on PATH. That stale
# entry will shadow our launcher and produce confusing errors (e.g. node
# MODULE_NOT_FOUND). Surface the conflict so the user can clean it up.
detect_stale_launcher() {
    local bin_dir="$1"
    local found=()
    local seen=":"
    local IFS=':'
    for d in $PATH; do
        [[ -z "$d" ]] && continue
        # Dedupe — PATH often lists the same dir twice (.bashrc + .profile etc.)
        case "$seen" in *":$d:"*) continue;; esac
        seen="$seen$d:"
        if [[ -e "$d/decepticon" && "$d" != "$bin_dir" ]]; then
            found+=("$d/decepticon")
        fi
    done

    if [[ ${#found[@]} -gt 0 ]]; then
        echo ""
        warn "Found other 'decepticon' executable(s) on PATH:"
        for f in "${found[@]}"; do
            echo "  $f"
        done
        warn "These may shadow the launcher just installed at $bin_dir/decepticon."
        echo -e "${DIM}Remove them, then run 'hash -r' or restart your shell.${NC}"
    fi
}

# ── PATH setup (bash/zsh/fish) ────────────────────────────────────
setup_path() {
    local bin_dir="$1"
    local path_export="export PATH=\"$bin_dir:\$PATH\""

    # Already in PATH?
    if echo "$PATH" | tr ':' '\n' | grep -qx "$bin_dir"; then
        info "PATH already includes $bin_dir"
        return
    fi

    # GitHub Actions
    if [[ -n "${GITHUB_PATH:-}" ]]; then
        echo "$bin_dir" >> "$GITHUB_PATH"
        return
    fi

    local current_shell
    current_shell=$(basename "${SHELL:-bash}")
    local XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

    case "$current_shell" in
        fish)
            local fish_config="$XDG_CONFIG_HOME/fish/config.fish"
            if [[ -f "$fish_config" ]]; then
                if ! grep -q "$bin_dir" "$fish_config" 2>/dev/null; then
                    echo -e "\n# decepticon" >> "$fish_config"
                    echo "fish_add_path $bin_dir" >> "$fish_config"
                    info "Added to PATH in $fish_config"
                fi
            fi
            ;;
        zsh)
            local zshrc="${ZDOTDIR:-$HOME}/.zshrc"
            if [[ -f "$zshrc" ]] || [[ -w "$(dirname "$zshrc")" ]]; then
                if ! grep -q "$bin_dir" "$zshrc" 2>/dev/null; then
                    echo -e "\n# decepticon" >> "$zshrc"
                    echo "$path_export" >> "$zshrc"
                    info "Added to PATH in $zshrc"
                fi
            fi
            ;;
        *)
            # bash and others
            local bashrc="$HOME/.bashrc"
            local profile="$HOME/.profile"
            local target="$bashrc"
            [[ ! -f "$target" ]] && target="$profile"

            if [[ -f "$target" ]] || [[ -w "$(dirname "$target")" ]]; then
                if ! grep -q "$bin_dir" "$target" 2>/dev/null; then
                    echo -e "\n# decepticon" >> "$target"
                    echo "$path_export" >> "$target"
                    info "Added to PATH in $target"
                fi
            fi
            ;;
    esac
}

# ── Pull Docker images ────────────────────────────────────────────
pull_images() {
    local install_dir="$1"

    if [[ "${SKIP_PULL:-}" == "true" ]]; then
        info "Skipping Docker image pull (SKIP_PULL=true)."
        return
    fi

    echo ""
    info "Pulling Docker images (this may take a few minutes)..."
    (cd "$install_dir" && docker compose --env-file .env --profile cli pull) || {
        warn "Warning: Failed to pull some images."
        info "You can pull them manually later: decepticon update"
    }
}

# ── Main ──────────────────────────────────────────────────────────
main() {
    local install_dir="${DECEPTICON_HOME:-$HOME/.decepticon}"
    local bin_dir="$HOME/.local/bin"


    echo ""
    echo -e "${BOLD}Decepticon${NC} — Installer"
    echo ""

    # Pre-flight
    preflight

    # Version
    resolve_version

    mkdir -p "$install_dir"

    info "Installing Decepticon $DECEPTICON_VERSION"
    info "Directory: $install_dir"
    echo ""

    # Download
    download_files "$install_dir"
    success "Configuration files downloaded."

    # Launcher
    create_launcher "$bin_dir" "$install_dir"
    success "Launcher installed to $bin_dir/decepticon"

    # PATH
    setup_path "$bin_dir"

    # Stale launcher detection (runs after PATH setup so $bin_dir is the
    # source of truth for "where the new launcher lives")
    detect_stale_launcher "$bin_dir"

    # Docker images
    pull_images "$install_dir"

    # Done
    echo ""
    echo -e "${GREEN}────────────────────────────────────────────${NC}"
    echo -e "${GREEN}  Decepticon installed successfully!${NC}"
    echo -e "${GREEN}────────────────────────────────────────────${NC}"
    echo ""
    echo -e "  ${BOLD}1.${NC} Configure your API keys:"
    echo -e "     ${BOLD}decepticon onboard${NC}"
    echo ""
    echo -e "  ${BOLD}2.${NC} Start Decepticon:"
    echo -e "     ${BOLD}decepticon${NC}"
    echo ""

    # Reload-shell hint — always show it.
    # Two failure modes a user can hit on a fresh shell:
    #   (a) $bin_dir was just added to .bashrc/.zshrc/etc. but the current
    #       shell hasn't sourced it yet → `decepticon` not found.
    #   (b) The shell already has $bin_dir on PATH but a stale `decepticon`
    #       (e.g. removed npm shim) is cached in its hash table → the wrong
    #       binary is invoked or "No such file or directory" is reported.
    # Spelling both fixes out unconditionally is cheaper than diagnosing
    # either failure after the fact.
    echo -e "  ${DIM}Reload your shell to pick up the new launcher:${NC}"
    echo -e "     ${BOLD}exec \$SHELL${NC}     ${DIM}# or open a new terminal${NC}"
    echo -e "  ${DIM}If $bin_dir is already on PATH (e.g. you upgraded), refresh the cache:${NC}"
    echo -e "     ${BOLD}hash -r${NC}"
    echo ""
}

main "$@"
