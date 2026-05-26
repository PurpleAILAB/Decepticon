package cmd

import (
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestProductNameDefaultsToDecepticon(t *testing.T) {
	if ProductName != "decepticon" {
		t.Fatalf("expected ProductName default %q, got %q", "decepticon", ProductName)
	}
}

func TestRootCommandUseFollowsProductName(t *testing.T) {
	if !strings.HasPrefix(rootCmd.Use, ProductName) {
		t.Fatalf("rootCmd.Use=%q should start with ProductName=%q", rootCmd.Use, ProductName)
	}
}

// TestLdflagInjection_End2End builds the launcher with custom ldflags
// and asserts the resulting binary reports the injected ProductName.
func TestLdflagInjection_End2End(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping go-build test in -short mode")
	}
	// Find launcher module root (cmd is one level down from launcher/).
	_, thisFile, _, _ := runtime.Caller(0)
	launcherRoot := filepath.Dir(filepath.Dir(thisFile))
	out := filepath.Join(t.TempDir(), "decepticon-mac-test")
	cmd := exec.Command(
		"go", "build",
		"-ldflags",
		"-X github.com/PurpleAILAB/Decepticon/clients/launcher/cmd.ProductName=decepticon-mac "+
			"-X github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config.DefaultHome=.decepticon-mac",
		"-o", out, ".",
	)
	cmd.Dir = launcherRoot
	if buildOut, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("ldflag build failed: %v\n%s", err, buildOut)
	}
	versionCmd := exec.Command(out, "--version")
	versionOut, err := versionCmd.CombinedOutput()
	if err != nil {
		t.Fatalf("--version failed: %v\n%s", err, versionOut)
	}
	if !strings.Contains(string(versionOut), "decepticon-mac") {
		t.Fatalf("expected --version to contain %q, got: %s",
			"decepticon-mac", versionOut)
	}
	// Verify the DefaultHome ldflag actually baked into the binary's build
	// metadata. `go version -m` prints the -ldflags string verbatim, which
	// is sufficient evidence without needing a runtime "print home" subcommand.
	infoCmd := exec.Command("go", "version", "-m", out)
	infoOut, err := infoCmd.CombinedOutput()
	if err != nil {
		t.Fatalf("`go version -m` failed: %v\n%s", err, infoOut)
	}
	if !strings.Contains(string(infoOut), "internal/config.DefaultHome=.decepticon-mac") {
		t.Fatalf("expected ldflags to include DefaultHome override; got:\n%s", infoOut)
	}
}
