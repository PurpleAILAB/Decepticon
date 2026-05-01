package cmd

import (
	"reflect"
	"testing"
)

// withProbeStubs swaps the WSL detection function variables for the
// duration of one test, then restores them via t.Cleanup.
func withProbeStubs(t *testing.T, isWSL bool, wslIP string) {
	t.Helper()
	prevIsWSL := isWSLFn
	prevHostIP := wslHostIPFn
	isWSLFn = func() bool { return isWSL }
	wslHostIPFn = func() string { return wslIP }
	t.Cleanup(func() {
		isWSLFn = prevIsWSL
		wslHostIPFn = prevHostIP
	})
}

func TestCandidateProbeURLs_NonDockerHostPassesThrough(t *testing.T) {
	withProbeStubs(t, false, "")
	got := candidateProbeURLs("http://10.0.0.5:11434")
	want := []string{"http://10.0.0.5:11434"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("non-docker host should pass through; got %v want %v", got, want)
	}
}

func TestCandidateProbeURLs_NativeLinuxFallsBackToLoopback(t *testing.T) {
	withProbeStubs(t, false, "")
	got := candidateProbeURLs("http://host.docker.internal:11434")
	want := []string{
		"http://host.docker.internal:11434",
		"http://127.0.0.1:11434",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("native linux candidates wrong:\n got %v\nwant %v", got, want)
	}
}

func TestCandidateProbeURLs_WSLAddsResolvedHostThenLoopback(t *testing.T) {
	withProbeStubs(t, true, "172.29.176.1")
	got := candidateProbeURLs("http://host.docker.internal:11434")
	want := []string{
		"http://host.docker.internal:11434",
		"http://172.29.176.1:11434",
		"http://127.0.0.1:11434",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("WSL candidates wrong:\n got %v\nwant %v", got, want)
	}
}

func TestCandidateProbeURLs_WSLWithoutResolvedHostStillTriesLoopback(t *testing.T) {
	withProbeStubs(t, true, "")
	got := candidateProbeURLs("http://host.docker.internal:11434")
	want := []string{
		"http://host.docker.internal:11434",
		"http://127.0.0.1:11434",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("WSL without resolv.conf IP should still fall back to loopback:\n got %v\nwant %v", got, want)
	}
}

func TestCandidateProbeURLs_DedupesWhenResolvedHostIsLoopback(t *testing.T) {
	// A WSL2 setup where /etc/resolv.conf already points at 127.0.0.1
	// (e.g. systemd-resolved local stub on the distro) should not
	// produce two identical loopback entries.
	withProbeStubs(t, true, "127.0.0.1")
	got := candidateProbeURLs("http://host.docker.internal:11434")
	want := []string{
		"http://host.docker.internal:11434",
		"http://127.0.0.1:11434",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("expected dedup of duplicate loopback candidates:\n got %v\nwant %v", got, want)
	}
}

func TestCandidateProbeURLs_HostWithoutPortRewritesCleanly(t *testing.T) {
	withProbeStubs(t, false, "")
	got := candidateProbeURLs("http://host.docker.internal")
	want := []string{
		"http://host.docker.internal",
		"http://127.0.0.1",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("port-less URL should rewrite cleanly:\n got %v\nwant %v", got, want)
	}
}

func TestCandidateProbeURLs_PreservesScheme(t *testing.T) {
	withProbeStubs(t, false, "")
	got := candidateProbeURLs("https://host.docker.internal:11434/v1")
	want := []string{
		"https://host.docker.internal:11434/v1",
		"https://127.0.0.1:11434/v1",
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("scheme/path should be preserved across candidates:\n got %v\nwant %v", got, want)
	}
}
