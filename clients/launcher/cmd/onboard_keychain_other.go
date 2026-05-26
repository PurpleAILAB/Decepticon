//go:build !darwin

package cmd

// Non-darwin builds get the no-op stub: there's no macOS Keychain to
// probe, so the probe always reports "not found" and the warning path
// in onboard.go is skipped entirely. Linux and Windows users see zero
// change.

type keychainProbeState int

const (
	keychainItemNotFound keychainProbeState = iota
	keychainItemPresentFileAbsent
	keychainItemPresentFilePresent
)

func probeClaudeCredentials() keychainProbeState {
	return keychainItemNotFound
}
