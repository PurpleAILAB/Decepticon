// Package platform exposes host-environment detection helpers shared
// across the launcher. The launcher runs on macOS, native Linux, and
// WSL2 (Windows Subsystem for Linux); some startup logic — most
// notably the Ollama reachability probe — has to branch on which one
// is in play.
package platform

import (
	"os"
	"runtime"
	"strings"
)

// procVersionPath is overridable in tests. The default reads the
// kernel-supplied /proc/version, which contains "Microsoft" or "WSL"
// on every WSL release shipped to date.
var procVersionPath = "/proc/version"

// resolvConfPath is overridable in tests. The default reads
// /etc/resolv.conf, where WSL2 records the Windows host as the first
// nameserver under the default DNS forwarder mode.
var resolvConfPath = "/etc/resolv.conf"

// IsWSL returns true when the launcher is running inside the Windows
// Subsystem for Linux. WSL1 and WSL2 both stamp the kernel version
// string with a recognizable token, so a single substring check is
// sufficient and avoids requiring CGO or extra system probes.
//
// On non-Linux GOOS the answer is unconditionally false — macOS and
// native Windows can't be WSL even if /proc/version somehow exists.
func IsWSL() bool {
	if runtime.GOOS != "linux" {
		return false
	}
	data, err := os.ReadFile(procVersionPath)
	if err != nil {
		return false
	}
	s := strings.ToLower(string(data))
	return strings.Contains(s, "microsoft") || strings.Contains(s, "wsl")
}

// WSLHostIP returns the IP address that the WSL2 distro can use to
// reach the Windows host. Under the default WSL2 networking mode
// (NAT), the Windows host appears as the first nameserver in
// /etc/resolv.conf — Microsoft's WSL DNS forwarder runs on the
// Windows side and is the only nameserver injected by default.
//
// Returns "" when the file is missing, has no nameserver line, or
// cannot be parsed; callers should fall back to a sensible default
// (typically 127.0.0.1 for the WSL distro's own loopback, which is
// where Ollama lives in the "WSL-side install" scenario).
func WSLHostIP() string {
	data, err := os.ReadFile(resolvConfPath)
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && fields[0] == "nameserver" {
			return fields[1]
		}
	}
	return ""
}
