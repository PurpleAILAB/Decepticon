package opscontrol

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
)

// LaunchdManager owns a per-user LaunchAgent at
// ~/Library/LaunchAgents/red.decepticon.opscontrol[.${STACK}].plist.
//
// LaunchAgents (not LaunchDaemons) is intentional — same UID story
// as the systemd user-unit choice in systemd.go.
type LaunchdManager struct {
	Label string // e.g. "red.decepticon.opscontrol" or
	//               "red.decepticon.opscontrol.stack2"
}

func newLaunchdManager() *LaunchdManager {
	label := "red.decepticon.opscontrol"
	if stack := StackName(); stack != "" {
		label = label + "." + stack
	}
	return &LaunchdManager{Label: label}
}

var launchctlBinary = "launchctl"

func (l *LaunchdManager) Name() string { return "launchd" }

// Available probes the user-session launchd by asking for its print
// dump. Exit 0 → bus is reachable; non-zero → no session bus (e.g.
// CI runner without `launchctl bootstrap`). Failure degrades to
// noopManager.
func (l *LaunchdManager) Available() bool {
	if _, err := exec.LookPath(launchctlBinary); err != nil {
		return false
	}
	uid := strconv.Itoa(os.Getuid())
	if err := exec.Command(launchctlBinary, "print", "gui/"+uid).Run(); err != nil {
		return false
	}
	return true
}

func (l *LaunchdManager) plistPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("opscontrol: resolve user home: %w", err)
	}
	return filepath.Join(home, "Library", "LaunchAgents", l.Label+".plist"), nil
}

func (l *LaunchdManager) Installed() (bool, error) {
	p, err := l.plistPath()
	if err != nil {
		return false, err
	}
	_, err = os.Stat(p)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	return err == nil, err
}

// Active uses `launchctl print` against the user domain. The output
// contains a `state = running` line when the agent has live processes.
// We grep for that — `launchctl list <label>` is the older surface
// and returns 0 even when the agent has never started.
func (l *LaunchdManager) Active() (bool, error) {
	uid := strconv.Itoa(os.Getuid())
	out, err := exec.Command(launchctlBinary, "print", "gui/"+uid+"/"+l.Label).Output()
	if err != nil {
		return false, nil
	}
	return strings.Contains(string(out), "state = running"), nil
}

func (l *LaunchdManager) Install(spec InstallSpec) error {
	if spec.BinaryPath == "" || spec.HomePath == "" {
		return errors.New("opscontrol: InstallSpec requires BinaryPath and HomePath")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("opscontrol: resolve user home: %w", err)
	}
	agentsDir := filepath.Join(home, "Library", "LaunchAgents")
	if err := os.MkdirAll(agentsDir, 0o755); err != nil {
		return fmt.Errorf("opscontrol: create LaunchAgents dir: %w", err)
	}

	plist := l.renderPlist(spec)
	plistFile := filepath.Join(agentsDir, l.Label+".plist")
	if err := os.WriteFile(plistFile, []byte(plist), 0o644); err != nil {
		return fmt.Errorf("opscontrol: write plist: %w", err)
	}

	uid := strconv.Itoa(os.Getuid())
	// Bootout first to recover from a stale install; ignore errors so
	// the never-installed case still proceeds.
	_ = exec.Command(launchctlBinary, "bootout", "gui/"+uid+"/"+l.Label).Run()

	if out, err := exec.Command(launchctlBinary, "bootstrap", "gui/"+uid, plistFile).CombinedOutput(); err != nil {
		return fmt.Errorf("opscontrol: launchctl bootstrap: %w: %s", err, strings.TrimSpace(string(out)))
	}
	if out, err := exec.Command(launchctlBinary, "enable", "gui/"+uid+"/"+l.Label).CombinedOutput(); err != nil {
		return fmt.Errorf("opscontrol: launchctl enable: %w: %s", err, strings.TrimSpace(string(out)))
	}
	if out, err := exec.Command(launchctlBinary, "kickstart", "gui/"+uid+"/"+l.Label).CombinedOutput(); err != nil {
		return fmt.Errorf("opscontrol: launchctl kickstart: %w: %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

func (l *LaunchdManager) Uninstall() error {
	uid := strconv.Itoa(os.Getuid())
	_ = exec.Command(launchctlBinary, "bootout", "gui/"+uid+"/"+l.Label).Run()
	p, err := l.plistPath()
	if err != nil {
		return err
	}
	if err := os.Remove(p); err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("opscontrol: remove plist: %w", err)
	}
	return nil
}

func (l *LaunchdManager) Start() error {
	installed, err := l.Installed()
	if err != nil {
		return err
	}
	if !installed {
		return ErrNotInstalled
	}
	uid := strconv.Itoa(os.Getuid())
	if out, err := exec.Command(launchctlBinary, "kickstart", "gui/"+uid+"/"+l.Label).CombinedOutput(); err != nil {
		return fmt.Errorf("opscontrol: launchctl kickstart: %w: %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

func (l *LaunchdManager) Stop() error {
	uid := strconv.Itoa(os.Getuid())
	_ = exec.Command(launchctlBinary, "kill", "TERM", "gui/"+uid+"/"+l.Label).Run()
	return nil
}

// renderPlist produces the LaunchAgent .plist body. KeepAlive +
// SuccessfulExit=false mirrors systemd's Restart=on-failure — the
// daemon comes back on crash but won't loop after a clean stop.
func (l *LaunchdManager) renderPlist(spec InstallSpec) string {
	logPath := filepath.Join(spec.HomePath, "run", "opscontrol"+stackSuffix())
	stackEntry := ""
	if spec.StackName != "" {
		stackEntry = fmt.Sprintf(`
        <key>DECEPTICON_STACK_NAME</key>
        <string>%s</string>`, spec.StackName)
	}
	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>%s</string>
    <key>ProgramArguments</key>
    <array>
        <string>%s</string>
        <string>opscontrol</string>
        <string>daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>DECEPTICON_HOME</key>
        <string>%s</string>%s
    </dict>
    <key>StandardOutPath</key>
    <string>%s.out.log</string>
    <key>StandardErrorPath</key>
    <string>%s.err.log</string>
</dict>
</plist>
`, l.Label, spec.BinaryPath, spec.HomePath, stackEntry, logPath, logPath)
}
