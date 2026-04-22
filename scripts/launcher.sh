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
    local auto_update
    auto_update=$(grep -m1 '^AUTO_UPDATE=' "$DECEPTICON_HOME/.env" 2>/dev/null | cut -d= -f2 | tr -d "'\"" || true)
    if [[ "${auto_update,,}" == "false" ]]; then
        return
    fi

    local current
    current=$(cat "$DECEPTICON_HOME/.version" 2>/dev/null || echo "")
    [[ -z "$current" ]] && return

    local latest
    latest=$(curl -sf --max-time 5 "https://api.github.com/repos/$REPO/releases/latest" \
        | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p') 2>/dev/null || true

    [[ -z "$latest" ]] && return  # offline / API error -- skip silently

    # sort -V puts the higher version last; skip if current is already >= latest
    local newer
    newer=$(printf '%s\n%s' "$latest" "$current" | sort -V | tail -1)
    [[ "$newer" == "$current" ]] && return  # already up to date or ahead

    echo -e "${CYAN}Auto-updating: ${BOLD}v${current}${NC}${CYAN} -> ${BOLD}v${latest}${NC}"

    local tag_base="https://raw.githubusercontent.com/$REPO/v${latest}"

    # Sync config files
    if ! curl -fsSL "$tag_base/docker-compose.yml" \
        -o "$DECEPTICON_HOME/docker-compose.yml" 2>/dev/null; then
        echo -e "${YELLOW}Auto-update: failed to fetch docker-compose.yml -- skipping.${NC}"
        return
    fi
    mkdir -p "$DECEPTICON_HOME/config"
    curl -fsSL "$tag_base/config/litellm.yaml" \
        -o "$DECEPTICON_HOME/config/litellm.yaml" 2>/dev/null || true
    echo "$latest" > "$DECEPTICON_HOME/.version"

    # Pull updated images
    echo -e "${DIM}Pulling images (v${latest})...${NC}"
    if ! DECEPTICON_VERSION="$latest" $COMPOSE_PROFILES pull 2>/dev/null; then
        echo -e "${YELLOW}Some images failed to pull -- cached versions will be used.${NC}"
    fi

    # Update launcher itself (safe: { } wrapper keeps this script in memory)
    if curl -fsSL "$tag_base/scripts/launcher.sh" \
        -o /tmp/decepticon-launcher-$$.sh 2>/dev/null; then
        chmod 755 /tmp/decepticon-launcher-$$.sh
        mv /tmp/decepticon-launcher-$$.sh "$(which decepticon 2>/dev/null || echo "$HOME/.local/bin/decepticon")" 2>/dev/null || true
    fi

    echo -e "${GREEN}Updated to v${latest}.${NC}"
    echo ""

    # Re-exec so the new launcher code takes effect immediately.
    # The { } wrapper means bash is still running the OLD in-memory code;
    # exec replaces this process with the NEW on-disk script.
    # On re-entry, check_for_update will see version == latest and skip,
    # so there is no infinite loop risk.
    exec "$0" "$@"
}

wait_for_web() {
    local port="${WEB_PORT:-3000}"
    local max_wait=60
    local waited=0 frame=0 spin
    local spinners='-\|/'
    while ! curl -sf "http://localhost:$port" >/dev/null 2>&1; do
        if [[ $waited -ge $max_wait ]]; then
            printf "\r  ${YELLOW}[!]${NC} ${DIM}Web :${port} -- not ready after %ss${NC}          \n" "$waited"
            echo -e "${DIM}Check: ${NC}${BOLD}decepticon logs web${NC}"
            return
        fi
        spin="${spinners:$((frame % 4)):1}"
        printf "\r  ${DIM}%s Web :${port} (%ss)...${NC}" "$spin" "$waited"
        frame=$((frame + 1)); sleep 2; waited=$((waited + 2))
    done
    printf "\r  ${GREEN}[ok]${NC} ${DIM}Web :${port} (%ss)${NC}          \n" "$waited"
}

wait_for_server() {
    local port="${LANGGRAPH_PORT:-2024}"
    local litellm_port="${LITELLM_PORT:-4000}"
    local max_wait=90
    local litellm_max=60
    local waited frame spin
    local spinners='-\|/'

    echo -e "${DIM}Waiting for services to be ready:${NC}"

    # Phase 1+2: LangGraph HTTP up + agent graph loaded
    waited=0; frame=0
    while true; do
        if curl -sf "http://localhost:$port/assistants/search" \
            -H "Content-Type: application/json" -d '{"graph_id":"decepticon","limit":1}' \
            2>/dev/null | grep -q "decepticon"; then
            printf "\r  ${GREEN}[ok]${NC} ${DIM}LangGraph :${port} (%ss)${NC}          \n" "$waited"
            break
        fi
        if [[ $waited -ge $max_wait ]]; then
            printf "\r  ${RED}[!!] LangGraph :${port} -- not ready after %ss${NC}          \n" "$max_wait"
            echo -e "${DIM}Check logs: ${NC}${BOLD}decepticon logs${NC}"
            exit 1
        fi
        spin="${spinners:$((frame % 4)):1}"
        printf "\r  ${DIM}%s LangGraph :${port} (%ss)...${NC}" "$spin" "$waited"
        frame=$((frame + 1)); sleep 2; waited=$((waited + 2))
    done

    # Phase 3: LiteLLM readiness -- prevents APIConnectionError window where
    # LangGraph is up but LiteLLM is still initializing (service_started, not service_healthy)
    waited=0; frame=0
    while true; do
        if curl -sf "http://localhost:${litellm_port}/health/readiness" >/dev/null 2>&1; then
            printf "\r  ${GREEN}[ok]${NC} ${DIM}LiteLLM :${litellm_port} (%ss)${NC}          \n" "$waited"
            break
        fi
        if [[ $waited -ge $litellm_max ]]; then
            printf "\r  ${YELLOW}[!]${NC} ${DIM}LiteLLM :${litellm_port} -- not ready after %ss${NC}          \n" "$litellm_max"
            echo -e "${DIM}First LLM call may fail. Check: ${NC}${BOLD}decepticon logs litellm${NC}"
            break
        fi
        spin="${spinners:$((frame % 4)):1}"
        printf "\r  ${DIM}%s LiteLLM :${litellm_port} (%ss)...${NC}" "$spin" "$waited"
        frame=$((frame + 1)); sleep 2; waited=$((waited + 2))
    done
}

# ── Auto-migrate to Go binary ────────────────────────────────────
# If a compiled Go launcher is available in GitHub Releases, download
# it and replace this bash script. Re-exec so the user seamlessly
# switches to the Go version on next run.
migrate_to_go_binary() {
    # Skip if disabled
    local auto_update
    auto_update=$(grep -m1 '^AUTO_UPDATE=' "$DECEPTICON_HOME/.env" 2>/dev/null | cut -d= -f2 | tr -d "'\"" || true)
    [[ "${auto_update,,}" == "false" ]] && return

    # Skip if already tried and failed recently (cooldown: 24h)
    local marker="$DECEPTICON_HOME/.go-migration-checked"
    if [[ -f "$marker" ]]; then
        local age=$(( $(date +%s) - $(stat -c %Y "$marker" 2>/dev/null || echo 0) ))
        [[ $age -lt 86400 ]] && return
    fi

    # Detect OS and architecture
    local os arch
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m)
    case "$arch" in
        x86_64)  arch="amd64" ;;
        aarch64|arm64) arch="arm64" ;;
        *) return ;;  # unsupported arch, stay on bash
    esac

    # Find the latest release with a Go binary
    local latest binary_name download_url
    latest=$(curl -sf --max-time 5 "https://api.github.com/repos/$REPO/releases/latest" \
        | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p') 2>/dev/null || true
    [[ -z "$latest" ]] && return

    binary_name="decepticon-${os}-${arch}"
    download_url="https://github.com/$REPO/releases/download/v${latest}/${binary_name}"

    # Check if binary exists in the release (HEAD request)
    if ! curl -sfI --max-time 5 "$download_url" >/dev/null 2>&1; then
        touch "$marker"  # no binary yet, check again tomorrow
        return
    fi

    echo -e "${CYAN}Upgrading to native launcher (v${latest})...${NC}"

    local self
    self=$(which decepticon 2>/dev/null || echo "$HOME/.local/bin/decepticon")
    local tmp="/tmp/decepticon-go-$$"

    if curl -fsSL --max-time 60 "$download_url" -o "$tmp" 2>/dev/null; then
        chmod 755 "$tmp"
        # Verify it's a real binary (not an HTML error page)
        if file "$tmp" 2>/dev/null | grep -qiE "ELF|Mach-O"; then
            mv "$tmp" "$self"
            echo -e "${GREEN}Upgraded to Go launcher v${latest}.${NC}"
            exec "$self" "$@"
        else
            rm -f "$tmp"
            touch "$marker"
        fi
    else
        touch "$marker"
    fi
}

migrate_to_go_binary "$@"

case "${1:-}" in
    ""|start)
        check_api_key
        check_for_update

        # Start background services including victim targets
        echo -e "${DIM}Starting services...${NC}"
        $COMPOSE --profile victims up -d --no-build > /dev/null

        wait_for_server
        wait_for_web

        # Print web dashboard URL (reads WEB_PORT from .env, defaults to 3000)
        _web_port=$(grep -m1 '^WEB_PORT=' "$DECEPTICON_HOME/.env" 2>/dev/null | cut -d= -f2 | tr -d "'\"" || true)
        echo -e "${DIM}Web dashboard:${NC} ${BOLD}http://localhost:${_web_port:-3000}${NC}"

        # Export installed version so the CLI container can display it
        _ver=$(cat "$DECEPTICON_HOME/.version" 2>/dev/null || echo "")
        [[ -n "$_ver" ]] && export DECEPTICON_VERSION="$_ver"

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
                $COMPOSE up -d --no-build > /dev/null
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
        echo -e "${YELLOW}Note: 'decepticon config' is deprecated. Use 'decepticon onboard' instead.${NC}"
        echo ""
        ;&

    onboard)
        $COMPOSE_PROFILES run --rm cli python -m decepticon.cli.app onboard
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
        $COMPOSE --profile victims up -d --no-build metasploitable2 > /dev/null

        # Start core services (COMPOSE_PROFILES in .env controls which C2 framework starts)
        echo -e "${DIM}Starting services...${NC}"
        $COMPOSE up -d --no-build > /dev/null

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
        for c in decepticon-sandbox decepticon-langgraph decepticon-litellm decepticon-postgres decepticon-cli decepticon-web decepticon-dvwa decepticon-msf2 decepticon-c2-sliver decepticon-neo4j; do
            docker rm -f "$c" 2>/dev/null || true
        done
        # Clean up 'docker compose run' orphans
        docker rm $(docker ps -aq --filter "name=decepticon" --filter "status=exited") 2>/dev/null || true
        echo -e "${GREEN}Containers removed.${NC}"

        # 2. Remove Docker images
        echo -e "${DIM}Removing Docker images...${NC}"
        docker images --format '{{.Repository}}:{{.Tag}}' | grep -E "(ghcr\.io/purpleailab/)?decepticon-(sandbox|langgraph|cli|web|c2-sliver)" | xargs -r docker rmi -f 2>/dev/null || true
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
