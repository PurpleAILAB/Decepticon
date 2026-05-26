//go:build darwin

package cmd

import (
	"os"
	"os/exec"
	"path/filepath"
)

// keychainProbeState represents the outcome of probing for the Claude
// Code Keychain item plus the on-disk credentials file.
//
// Background: on macOS, Claude Code stores its OAuth credentials in the
// system Keychain under the generic-password service name
// "Claude Code-credentials". Decepticon's LiteLLM custom handler reads
// the credentials from `~/.claude/.credentials.json` instead, so users
// who picked the OAuth method during onboard but only have Keychain
// state silently fall through to file-based auth and hit 401s.
type keychainProbeState int

const (
	// keychainItemNotFound means the macOS Keychain has no
	// "Claude Code-credentials" item (user is not logged into the
	// Claude Code CLI on this Mac, or never has been).
	keychainItemNotFound keychainProbeState = iota

	// keychainItemPresentFileAbsent is the silent-401 case: Keychain
	// has the item but Decepticon's reader (the file) has nothing.
	keychainItemPresentFileAbsent

	// keychainItemPresentFilePresent is the refresh-race case: both
	// sides have credentials and both will try to refresh the same
	// account, eventually yielding invalid_grant 401s.
	keychainItemPresentFilePresent
)

// probeClaudeCredentials checks for the macOS Keychain item used by
// Claude Code AND for the on-disk credentials file Decepticon's
// LiteLLM handler reads.
//
// The probe uses `security find-generic-password -s 'Claude Code-credentials'`
// WITHOUT the `-w` flag, so it inspects metadata only and never reads
// the secret. This is deliberate — `-w` triggers the macOS GUI Keychain
// access prompt which is hostile during a CLI onboarding flow, whereas
// the metadata-only form is silent.
//
// On unexpected errors (security binary missing, permission denied on
// HOME, etc.) we conservatively return keychainItemNotFound: spurious
// warnings during onboard are more harmful than a missed hint, and
// Decepticon still functions without this guidance.
func probeClaudeCredentials() keychainProbeState {
	out, err := exec.Command(
		"security", "find-generic-password", "-s", "Claude Code-credentials",
	).CombinedOutput()
	// security exits non-zero with "could not be found" when the item
	// is absent. Any non-zero exit (binary missing, malformed args)
	// collapses to not-found for the reasons documented above.
	if err != nil {
		_ = out
		return keychainItemNotFound
	}
	if len(out) == 0 {
		return keychainItemNotFound
	}

	home, herr := os.UserHomeDir()
	if herr != nil {
		// Can't resolve HOME → can't check the file. Treat as
		// present-and-present so the user gets the race warning rather
		// than nothing — the silent-401 path is the worse failure mode.
		return keychainItemPresentFilePresent
	}
	credsPath := filepath.Join(home, ".claude", ".credentials.json")
	if _, ferr := os.Stat(credsPath); os.IsNotExist(ferr) {
		return keychainItemPresentFileAbsent
	}
	return keychainItemPresentFilePresent
}
