#!/bin/bash
# Entrypoint for the Havoc C2 teamserver container.
# Runs as root to fix volume permissions, then starts the teamserver.
# 1. Fixes ownership on mounted volumes
# 2. Generates default profile if none exists
# 3. Starts havoc-server with the profile
set -e

PROFILE_DIR="/opt/havoc/profiles"
PROFILE_FILE="${PROFILE_DIR}/decepticon.yaotl"
DATA_DIR="/opt/havoc/data"

# ── Fix volume permissions (runs as root) ──────────────────────────
# Docker named volumes are created as root. Ensure havoc user can write.
chown -R havoc:users /home/havoc/.havoc
mkdir -p "$PROFILE_DIR" "$DATA_DIR"
chown -R havoc:users "$PROFILE_DIR" "$DATA_DIR"

# ── Everything below runs as havoc user ────────────────────────────
run_as_havoc() {
  runuser -u havoc -- "$@"
}

# Generate default profile if not already present
if [ ! -f "$PROFILE_FILE" ]; then
  HAVOC_OPERATOR_PASSWORD="${HAVOC_OPERATOR_PASSWORD:-decepticon-default}"
  cat > "$PROFILE_FILE" << YAOTL
Teamserver {
  Host = "0.0.0.0"
  Port = 40056
  Build {
    Compiler64 = "/usr/bin/x86_64-w64-mingw32-gcc"
    Compiler86 = "/usr/bin/i686-w64-mingw32-gcc"
    Nasm       = "/usr/bin/nasm"
  }
}

Operators {
  user "decepticon" {
    Password = "${HAVOC_OPERATOR_PASSWORD}"
  }
}

Listeners {
  Http {
    Name       = "decepticon-https"
    Hosts      = ["0.0.0.0"]
    HostBind   = "0.0.0.0"
    PortBind   = 443
    PortConn   = 443
    Secure     = true
    UserAgent  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  }
}

Demon {
  Sleep   = 5
  Jitter  = 20
  IndirectSyscall = true
  SleepTechnique  = "Ekko"
  Injection {
    Spawn64 = "C:\\\\Windows\\\\System32\\\\notepad.exe"
    Spawn86 = "C:\\\\Windows\\\\SysWOW64\\\\notepad.exe"
  }
}
YAOTL
  chown havoc:users "$PROFILE_FILE"
  echo "[c2-havoc] Default profile generated → ${PROFILE_FILE}"
else
  echo "[c2-havoc] Profile already exists → ${PROFILE_FILE}"
fi

# Start teamserver
echo "[c2-havoc] Starting Havoc teamserver on port 40056..."
exec run_as_havoc havoc-server --profile "$PROFILE_FILE" -v
