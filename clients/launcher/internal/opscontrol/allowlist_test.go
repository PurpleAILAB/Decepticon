package opscontrol

import "testing"

func TestLoadAllowlist_DefaultsMatchCatalog(t *testing.T) {
	t.Setenv(AllowlistExtraEnv, "")
	al, err := LoadAllowlist()
	if err != nil {
		t.Fatalf("LoadAllowlist: %v", err)
	}
	for _, name := range DefaultAllowlist {
		if !al.Permits(name) {
			t.Errorf("default catalog entry %q not permitted", name)
		}
	}
}

func TestLoadAllowlist_ExtraEnvAppends(t *testing.T) {
	t.Setenv(AllowlistExtraEnv, "fake-test, another-one")
	al, err := LoadAllowlist()
	if err != nil {
		t.Fatalf("LoadAllowlist: %v", err)
	}
	if !al.Permits("fake-test") {
		t.Errorf("extra env entry %q not permitted", "fake-test")
	}
	if !al.Permits("another-one") {
		t.Errorf("extra env entry %q not permitted", "another-one")
	}
	// Baseline still present.
	if !al.Permits("ad") {
		t.Errorf("default %q dropped after extra env merge", "ad")
	}
}

func TestLoadAllowlist_RejectsInvalidExtra(t *testing.T) {
	t.Setenv(AllowlistExtraEnv, "BadName_with_underscore")
	if _, err := LoadAllowlist(); err == nil {
		t.Fatal("expected error for invalid workload name in extra env")
	}
}

func TestPermits_RejectsIllegalNames(t *testing.T) {
	t.Setenv(AllowlistExtraEnv, "")
	al, err := LoadAllowlist()
	if err != nil {
		t.Fatalf("LoadAllowlist: %v", err)
	}
	cases := []string{
		"",
		"-leading-dash",
		"UPPER",
		"has space",
		"path/traversal",
		"with.dot",
		"with_under",
		"a" + string(make([]byte, 64)), // > 63 chars
	}
	for _, c := range cases {
		if al.Permits(c) {
			t.Errorf("Permits(%q) returned true; want false", c)
		}
	}
}

func TestPermits_RejectsUnknownButValid(t *testing.T) {
	t.Setenv(AllowlistExtraEnv, "")
	al, err := LoadAllowlist()
	if err != nil {
		t.Fatalf("LoadAllowlist: %v", err)
	}
	// "fake-but-valid-name" matches the regex but is not in the
	// baked-in catalog, so it must be rejected. This is the OWASP
	// LLM06 "narrow extension" property in action.
	if al.Permits("fake-but-valid-name") {
		t.Error(`Permits("fake-but-valid-name") = true; valid name must still be rejected if not in catalog`)
	}
}
