package starprompt

import (
	"os/exec"
	"runtime"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/platform"
)

// platformIsWSLFn is overridable for tests — production wires it to
// platform.IsWSL, the same detector cmd/start.go uses for its Ollama
// host-IP probe.
var platformIsWSLFn = platform.IsWSL

// openBrowserToRepo opens RepoURL in the host's default browser.
// Supported targets are macOS and WSL; native Linux is a best-effort
// fallback that lets a launcher built on a native Linux dev box still
// work.
//
//   - macOS                : `open <url>`
//   - WSL with wslview     : `wslview <url>` (purpose-built; from wslu)
//   - WSL without wslview  : `cmd.exe /c start <url>` (WSL2 interop)
//   - Native Linux         : `xdg-open <url>` (not a primary target)
//
// A non-nil error tells the caller to surface the URL as text instead
// — used when the host has no usable opener (headless SSH, WSL2 with
// interop disabled, etc.).
func openBrowserToRepo() error {
	if runtime.GOOS == "darwin" {
		return exec.Command("open", RepoURL).Start()
	}
	if platformIsWSLFn() {
		if _, err := exec.LookPath("wslview"); err == nil {
			return exec.Command("wslview", RepoURL).Start()
		}
		// WSL2 with Windows interop guarantees cmd.exe on PATH at
		// /mnt/c/Windows/System32/cmd.exe. If interop is disabled the
		// caller's fallback prints the URL.
		return exec.Command("cmd.exe", "/c", "start", RepoURL).Start()
	}
	return exec.Command("xdg-open", RepoURL).Start()
}
