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

# ── Create launcher script ───────────────────────────────────────
create_launcher() {
    local bin_dir="$1"
    local install_dir="$2"

    mkdir -p "$bin_dir"

    cat > "$bin_dir/decepticon" << 'LAUNCHER'
#!/usr/bin/env bash
# Wrap in { } so bash reads the entire script into memory before executing.
# This prevents "unexpected EOF" errors when `decepticon update` overwrites
# this file while it is still running.
{
set -euo pipefail

DECEPTICON_HOME="${DECEPTICON_HOME:-$HOME/.decepticon}"
REPO="PurpleAILAB/Decepticon"
BRANCH="${DECEPTICON_BRANCH:-main}"
RAW_BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"
COMPOSE_FILE="$DECEPTICON_HOME/docker-compose.yml"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $DECEPTICON_HOME/.env"
COMPOSE_PROFILES="$COMPOSE --profile cli"
# Every profile that may have started services. Required for `down` to reach
# profile-gated containers (cli, victims, c2-*) — without these flags compose
# silently leaves them running. Keep in sync with docker-compose.yml profiles.
COMPOSE_ALL_PROFILES="$COMPOSE --profile cli --profile victims --profile c2-sliver"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[0;2m'
BOLD='\033[1m'
NC='\033[0m'

check_api_key() {
    # Warn only if ALL API keys are still placeholders (any one real key is enough)
    local env_file="$DECEPTICON_HOME/.env"
    [[ ! -f "$env_file" ]] && return
    local has_real_key=false
    while IFS='=' read -r key value; do
        case "$key" in
            ANTHROPIC_API_KEY|OPENAI_API_KEY|GOOGLE_API_KEY)
                value="${value#"${value%%[![:space:]]*}"}"
                if [[ -n "$value" && ! "$value" =~ ^your-.*-key-here$ && ! "$value" =~ ^# ]]; then
                    has_real_key=true
                    break
                fi
                ;;
        esac
    done < "$env_file"
    if [[ "$has_real_key" == false ]]; then
        echo -e "${YELLOW}Warning: No API keys configured.${NC}"
        echo -e "${DIM}Run ${NC}${BOLD}decepticon config${NC}${DIM} to set at least one API key.${NC}"
        echo ""
    fi
}

check_for_update() {
    local current
    current=$(cat "$DECEPTICON_HOME/.version" 2>/dev/null || echo "")
    [[ -z "$current" ]] && return

    # Background check — don't block startup
    local latest
    latest=$(curl -sf --max-time 3 "https://api.github.com/repos/$REPO/releases/latest" \
        | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p') 2>/dev/null || true

    if [[ -n "$latest" && "$latest" != "$current" ]]; then
        echo -e "${CYAN}Update available: ${BOLD}v${latest}${NC}${CYAN} (current: v${current})${NC}"
        echo -e "${DIM}Run ${NC}${BOLD}decepticon update${NC}${DIM} to upgrade.${NC}"
        echo ""
    fi
}

wait_for_server() {
    local port="${LANGGRAPH_PORT:-2024}"
    local max_wait=90
    local waited=0
    echo -ne "${DIM}Waiting for LangGraph server"
    # Phase 1: Wait for HTTP server to respond
    while ! curl -sf "http://localhost:$port/ok" >/dev/null 2>&1; do
        if [[ $waited -ge $max_wait ]]; then
            echo -e "${NC}"
            echo -e "${RED}Server failed to start within ${max_wait}s.${NC}"
            echo -e "${DIM}Check logs: ${NC}${BOLD}decepticon logs${NC}"
            exit 1
        fi
        echo -n "."
        sleep 2
        waited=$((waited + 2))
    done
    # Phase 2: Wait for agent graph to be loaded and ready
    while ! curl -sf "http://localhost:$port/assistants/search" \
        -H "Content-Type: application/json" -d '{"graph_id":"decepticon","limit":1}' \
        | grep -q "decepticon" 2>/dev/null; do
        if [[ $waited -ge $max_wait ]]; then
            echo -e "${NC}"
            echo -e "${RED}Agent graph failed to load within ${max_wait}s.${NC}"
            echo -e "${DIM}Check logs: ${NC}${BOLD}decepticon logs${NC}"
            exit 1
        fi
        echo -n "."
        sleep 2
        waited=$((waited + 2))
    done
    echo -e " ${GREEN}ready${NC}"
}

case "${1:-}" in
    ""|start)
        check_api_key
        check_for_update

        # Start background services including victim targets
        echo -e "${DIM}Starting services...${NC}"
        $COMPOSE --profile victims up -d --no-build > /dev/null 2>&1

        wait_for_server

        # Run CLI in foreground (interactive)
        $COMPOSE_PROFILES run --rm cli
        ;;

    stop)
        echo -e "${DIM}Stopping all services...${NC}"
        $COMPOSE_ALL_PROFILES down > /dev/null 2>&1
        # Clean up orphaned CLI containers from 'docker compose run'
        docker rm $(docker ps -aq --filter "name=decepticon-cli-run" --filter "status=exited") 2>/dev/null || true
        echo -e "${GREEN}All services stopped.${NC}"
        ;;

    update)
        force=false
        if [[ "${2:-}" == "--force" || "${2:-}" == "-f" ]]; then
            force=true
        fi

        # Resolve latest version
        local_version=$(cat "$DECEPTICON_HOME/.version" 2>/dev/null || echo "unknown")
        echo -e "${DIM}Current version: v${local_version}${NC}"

        latest=$(curl -sf --max-time 5 "https://api.github.com/repos/$REPO/releases/latest" \
            | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p') 2>/dev/null || true

        if [[ -z "$latest" ]]; then
            echo -e "${YELLOW}Could not fetch latest version from GitHub.${NC}"
            echo -e "${DIM}Check your network connection and try again.${NC}"
            exit 1
        fi

        echo -e "${DIM}Latest version:  v${latest}${NC}"

        version_changed=false
        if [[ "$latest" != "$local_version" ]]; then
            version_changed=true
        fi

        echo "$latest" > "$DECEPTICON_HOME/.version"

        # Always sync config files and launcher (even for same version —
        # the release tag may have been updated with hotfixes)
        tag_base="https://raw.githubusercontent.com/$REPO/v${latest}"
        echo -e "${DIM}Updating configuration files...${NC}"
        curl -fsSL "$tag_base/docker-compose.yml" -o "$DECEPTICON_HOME/docker-compose.yml"
        mkdir -p "$DECEPTICON_HOME/config"
        curl -fsSL "$tag_base/config/litellm.yaml" -o "$DECEPTICON_HOME/config/litellm.yaml"
        echo -e "${GREEN}Configuration files updated.${NC}"

        # Pull images only when version changed or --force
        if [[ "$version_changed" == true || "$force" == true ]]; then
            echo -e "${DIM}Pulling images (v${latest})...${NC}"
            DECEPTICON_VERSION="$latest" $COMPOSE_PROFILES pull \
                || echo -e "${YELLOW}Warning: Some images failed to pull.${NC}"

            # Restart services if running
            if docker ps --filter "name=decepticon-langgraph" --format '{{.Names}}' | grep -q .; then
                echo -e "${DIM}Restarting services with new version...${NC}"
                $COMPOSE_ALL_PROFILES down > /dev/null 2>&1
                $COMPOSE up -d --no-build > /dev/null 2>&1
                echo -e "${GREEN}Updated and restarted (v${latest}).${NC}"
            else
                echo -e "${GREEN}Updated to v${latest}. Run ${NC}${BOLD}decepticon${NC}${GREEN} to start.${NC}"
            fi
        else
            echo -e "${GREEN}Already on v${latest}. Config and launcher synced.${NC}"
        fi

        # Update launcher script itself — MUST be last because this overwrites
        # the currently running script. The { } wrapper makes this safe, but
        # older launchers without it will crash after this point.
        echo -e "${DIM}Updating launcher...${NC}"
        curl -fsSL "$tag_base/scripts/install.sh" -o /tmp/decepticon-installer-$$.sh
        bash /tmp/decepticon-installer-$$.sh --launcher-only 2>/dev/null && \
            echo -e "${GREEN}Launcher updated.${NC}" || true
        rm -f /tmp/decepticon-installer-$$.sh
        ;;

    status)
        $COMPOSE ps
        ;;

    kg-health|graph-health)
        if ! docker ps --filter "name=decepticon-langgraph" --format '{{.Names}}' | grep -q .; then
            echo -e "${YELLOW}LangGraph is not running. Start Decepticon first: ${BOLD}decepticon${NC}"
            exit 1
        fi
        $COMPOSE exec -T langgraph python -m decepticon.research.health
        ;;

    logs)
        $COMPOSE logs -f "${2:-langgraph}"
        ;;

    config)
        ${EDITOR:-${VISUAL:-nano}} "$DECEPTICON_HOME/.env"
        ;;

    demo)
        check_api_key
        echo -e "${BOLD}Starting Decepticon Demo${NC}"
        echo -e "${DIM}Target: Metasploitable 2 (decepticon-msf2)${NC}"
        echo ""

        # Fix workspace ownership if Docker created it as root
        if [[ -d "$DECEPTICON_HOME/workspace" && ! -w "$DECEPTICON_HOME/workspace" ]]; then
            sudo chown -R "$(id -u):$(id -g)" "$DECEPTICON_HOME/workspace" 2>/dev/null || true
        fi

        # Download demo engagement files (skip if already present or offline)
        demo_dir="$DECEPTICON_HOME/workspace/demo/plan"
        mkdir -p "$demo_dir"
        mkdir -p "$DECEPTICON_HOME/workspace/demo/recon"
        mkdir -p "$DECEPTICON_HOME/workspace/demo/exploit"
        mkdir -p "$DECEPTICON_HOME/workspace/demo/post-exploit"
        touch "$DECEPTICON_HOME/workspace/demo/findings.md"
        for f in roe.json conops.json opplan.json; do
            if [[ ! -f "$demo_dir/$f" ]]; then
                curl -fsSL "$RAW_BASE/demo/plan/$f" -o "$demo_dir/$f" 2>/dev/null || {
                    echo -e "${RED}Failed to download $f. Run 'decepticon update' first.${NC}"
                    exit 1
                }
            fi
        done
        echo -e "${GREEN}Demo engagement loaded.${NC}"

        # Start victim target
        echo -e "${DIM}Starting Metasploitable 2...${NC}"
        $COMPOSE --profile victims up -d --no-build > /dev/null 2>&1 metasploitable2 > /dev/null 2>&1

        # Start core services (COMPOSE_PROFILES in .env controls which C2 framework starts)
        echo -e "${DIM}Starting services...${NC}"
        $COMPOSE up -d --no-build > /dev/null 2>&1

        wait_for_server

        echo ""
        echo -e "${GREEN}Demo ready.${NC} The CLI will open with a pre-configured engagement targeting Metasploitable 2."
        echo -e "${DIM}Objectives: port scan → vsftpd exploit → Sliver C2 implant → credential harvesting → internal recon${NC}"
        echo ""

        # Run CLI with auto-start message
        $COMPOSE_PROFILES run --rm -e DECEPTICON_INITIAL_MESSAGE="Resume the demo engagement and execute all objectives." cli
        ;;

    victims)
        $COMPOSE --profile victims up -d --no-build > /dev/null 2>&1
        echo -e "${GREEN}Victim targets started.${NC}"
        echo -e "${DIM}Use ${NC}${BOLD}decepticon status${NC}${DIM} to verify.${NC}"
        ;;

    remove|uninstall)
        echo -e "${BOLD}Decepticon — Uninstaller${NC}"
        echo ""
        echo -e "This will remove:"
        echo -e "  ${DIM}•${NC} All Decepticon Docker containers, images, volumes, and networks"
        echo -e "  ${DIM}•${NC} Configuration directory: ${BOLD}$DECEPTICON_HOME${NC}"
        echo -e "  ${DIM}•${NC} Launcher script: ${BOLD}$(which decepticon 2>/dev/null || echo "$HOME/.local/bin/decepticon")${NC}"
        echo -e "  ${DIM}•${NC} PATH entries from shell config"

        if [[ "${2:-}" != "--yes" ]]; then
            echo ""
            echo -ne "${YELLOW}Are you sure? [y/N] ${NC}"
            read -r confirm
            if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
                echo -e "${DIM}Aborted.${NC}"
                exit 0
            fi
        fi

        echo ""

        # 1. Stop and remove containers + networks + volumes
        echo -e "${DIM}Stopping and removing containers...${NC}"
        if [[ -f "$COMPOSE_FILE" ]]; then
            $COMPOSE_ALL_PROFILES down --volumes --remove-orphans 2>/dev/null || true
        fi
        # Clean up any remaining containers by name
        for c in decepticon-sandbox decepticon-langgraph decepticon-litellm decepticon-postgres decepticon-cli decepticon-dvwa decepticon-msf2 decepticon-c2-sliver decepticon-neo4j; do
            docker rm -f "$c" 2>/dev/null || true
        done
        # Clean up 'docker compose run' orphans
        docker rm $(docker ps -aq --filter "name=decepticon" --filter "status=exited") 2>/dev/null || true
        echo -e "${GREEN}Containers removed.${NC}"

        # 2. Remove Docker images
        echo -e "${DIM}Removing Docker images...${NC}"
        docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "decepticon-(sandbox|langgraph|cli|c2-sliver)" | xargs -r docker rmi -f 2>/dev/null || true
        echo -e "${GREEN}Images removed.${NC}"

        # 3. Remove install directory
        if [[ -d "$DECEPTICON_HOME" ]]; then
            # Preserve workspace if user wants it
            if [[ -d "$DECEPTICON_HOME/workspace" ]]; then
                echo -ne "${YELLOW}Keep workspace data ($DECEPTICON_HOME/workspace)? [Y/n] ${NC}"
                if [[ "${2:-}" == "--yes" ]]; then
                    keep_ws="n"
                else
                    read -r keep_ws
                fi
                if [[ "$keep_ws" =~ ^[Nn]$ ]]; then
                    echo -e "${DIM}Removing workspace...${NC}"
                else
                    echo -e "${DIM}Preserving workspace...${NC}"
                    mv "$DECEPTICON_HOME/workspace" "/tmp/decepticon-workspace-backup-$$" 2>/dev/null || true
                fi
            fi
            # Docker containers create root-owned files in workspace/;
            # try normal rm first, fall back to sudo if needed.
            if ! rm -rf "$DECEPTICON_HOME" 2>/dev/null; then
                echo -e "${DIM}Root-owned files detected (created by Docker). Using sudo...${NC}"
                sudo rm -rf "$DECEPTICON_HOME"
            fi
            # Restore workspace if preserved
            if [[ -d "/tmp/decepticon-workspace-backup-$$" ]]; then
                mkdir -p "$(dirname "$DECEPTICON_HOME")"
                mv "/tmp/decepticon-workspace-backup-$$" "$DECEPTICON_HOME/workspace"
                echo -e "${DIM}Workspace saved at $DECEPTICON_HOME/workspace${NC}"
            fi
            echo -e "${GREEN}Configuration removed.${NC}"
        fi

        # 4. Remove launcher script
        launcher_path="$(which decepticon 2>/dev/null || echo "$HOME/.local/bin/decepticon")"
        if [[ -f "$launcher_path" ]]; then
            rm -f "$launcher_path"
            echo -e "${GREEN}Launcher removed.${NC}"
        fi

        # 5. Clean PATH from shell configs
        echo -e "${DIM}Cleaning shell configuration...${NC}"
        bin_dir="$HOME/.local/bin"
        for rc in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.zshrc" "${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish"; do
            if [[ -f "$rc" ]]; then
                # Remove the '# decepticon' comment and the line after it
                sed -i '/^# decepticon$/,+1d' "$rc" 2>/dev/null || true
            fi
        done
        echo -e "${GREEN}Shell config cleaned.${NC}"

        echo ""
        echo -e "${GREEN}────────────────────────────────────────────${NC}"
        echo -e "${GREEN}  Decepticon has been removed.${NC}"
        echo -e "${GREEN}────────────────────────────────────────────${NC}"
        echo ""
        echo -e "  ${DIM}To reinstall:${NC}"
        echo -e "  ${BOLD}curl -fsSL https://raw.githubusercontent.com/$REPO/main/scripts/install.sh | bash${NC}"
        echo ""
        ;;

    --version|-v)
        echo "decepticon $(cat "$DECEPTICON_HOME/.version" 2>/dev/null || echo 'dev')"
        ;;

    --help|-h|help)
        echo -e "${BOLD}Decepticon${NC} — AI-powered autonomous red team framework"
        echo ""
        echo -e "${BOLD}Usage:${NC}"
        echo "  decepticon              Start services and open CLI"
        echo "  decepticon stop         Stop all services"
        echo "  decepticon update [-f]  Update images and config files (--force to re-pull)"
        echo "  decepticon status       Show service status"
        echo "  decepticon kg-health    Graph backend health diagnostics"
        echo "  decepticon logs [svc]   Follow service logs (default: langgraph)"
        echo "  decepticon config       Edit configuration (.env)"
        echo "  decepticon demo         Run guided demo (Metasploitable 2)"
        echo "  decepticon victims      Start vulnerable test targets"
        echo "  decepticon remove       Uninstall Decepticon completely"
        echo "  decepticon --version    Show version"
        ;;

    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo -e "${DIM}Run ${NC}${BOLD}decepticon --help${NC}${DIM} for usage.${NC}"
        exit 1
        ;;
esac
exit
}
LAUNCHER

    chmod 755 "$bin_dir/decepticon"
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

    # Quick path: only regenerate the launcher script (used by `decepticon update`)
    if [[ "${1:-}" == "--launcher-only" ]]; then
        create_launcher "$bin_dir" "$install_dir"
        return
    fi

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

    # Docker images
    pull_images "$install_dir"

    # Done
    echo ""
    echo -e "${GREEN}────────────────────────────────────────────${NC}"
    echo -e "${GREEN}  Decepticon installed successfully!${NC}"
    echo -e "${GREEN}────────────────────────────────────────────${NC}"
    echo ""
    echo -e "  ${BOLD}1.${NC} Configure your API key:"
    echo -e "     ${BOLD}decepticon config${NC}"
    echo ""
    echo -e "  ${BOLD}2.${NC} Start Decepticon:"
    echo -e "     ${BOLD}decepticon${NC}"
    echo ""

    # Hint to reload shell
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$bin_dir"; then
        echo -e "  ${DIM}Restart your shell or run:${NC}"
        echo -e "     ${BOLD}export PATH=\"$bin_dir:\$PATH\"${NC}"
        echo ""
    fi
}

main "$@"
