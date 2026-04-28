package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestParseEnvLine(t *testing.T) {
	tests := []struct {
		line      string
		wantKey   string
		wantVal   string
		wantOk    bool
	}{
		{"KEY=value", "KEY", "value", true},
		{"KEY=\"quoted value\"", "KEY", "quoted value", true},
		{"KEY='single quoted'", "KEY", "single quoted", true},
		{"KEY=", "KEY", "", true},
		{"# comment", "", "", false},
		{"", "", "", false},
		{"NOEQUALS", "", "", false},
		{"KEY=value with spaces", "KEY", "value with spaces", true},
	}
	for _, tt := range tests {
		key, val, ok := parseEnvLine(tt.line)
		if key != tt.wantKey || val != tt.wantVal || ok != tt.wantOk {
			t.Errorf("parseEnvLine(%q) = (%q, %q, %v), want (%q, %q, %v)",
				tt.line, key, val, ok, tt.wantKey, tt.wantVal, tt.wantOk)
		}
	}
}

func TestLoadEnv(t *testing.T) {
	dir := t.TempDir()
	envFile := filepath.Join(dir, ".env")
	content := `# Comment
ANTHROPIC_API_KEY=sk-ant-real-key
OPENAI_API_KEY=your-openai-key-here
DECEPTICON_MODEL_PROFILE=eco

# Another comment
DECEPTICON_MODEL_PROVIDER=api
`
	if err := os.WriteFile(envFile, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}

	env, err := LoadEnv(envFile)
	if err != nil {
		t.Fatalf("LoadEnv() error: %v", err)
	}

	if env["ANTHROPIC_API_KEY"] != "sk-ant-real-key" {
		t.Errorf("ANTHROPIC_API_KEY = %q, want %q", env["ANTHROPIC_API_KEY"], "sk-ant-real-key")
	}
	if env["DECEPTICON_MODEL_PROFILE"] != "eco" {
		t.Errorf("DECEPTICON_MODEL_PROFILE = %q, want %q", env["DECEPTICON_MODEL_PROFILE"], "eco")
	}
	if len(env) != 4 {
		t.Errorf("len(env) = %d, want 4", len(env))
	}
}

func TestIsPlaceholder(t *testing.T) {
	if !IsPlaceholder("your-anthropic-key-here") {
		t.Error("expected placeholder for 'your-anthropic-key-here'")
	}
	if !IsPlaceholder("your-openai-key-here") {
		t.Error("expected placeholder for 'your-openai-key-here'")
	}
	if IsPlaceholder("sk-ant-api03-real-key") {
		t.Error("did not expect placeholder for real key")
	}
	if !IsPlaceholder("") {
		t.Error("expected placeholder for empty string")
	}
}

func TestValidateAPIKeys(t *testing.T) {
	// All placeholders → error
	env := map[string]string{
		"ANTHROPIC_API_KEY": "your-anthropic-key-here",
		"OPENAI_API_KEY":    "your-openai-key-here",
	}
	if err := ValidateAPIKeys(env); err == nil {
		t.Error("expected error for all-placeholder keys")
	}

	// One real, well-formed key → ok
	env["ANTHROPIC_API_KEY"] = "sk-ant-api03-realkeythatislongenough"
	if err := ValidateAPIKeys(env); err != nil {
		t.Errorf("unexpected error: %v", err)
	}

	// Empty env → error
	if err := ValidateAPIKeys(map[string]string{}); err == nil {
		t.Error("expected error for empty env")
	}
}

func TestValidateAPIKeys_RejectsBadFormat(t *testing.T) {
	tests := []struct {
		name string
		env  map[string]string
	}{
		{"missing prefix", map[string]string{"ANTHROPIC_API_KEY": "no-prefix-key-of-decent-length"}},
		{"too short", map[string]string{"OPENAI_API_KEY": "sk-short"}},
		{"google missing prefix", map[string]string{"GOOGLE_API_KEY": "sk-wrongprefix-key-long-enough-here"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := ValidateAPIKeys(tt.env); err == nil {
				t.Errorf("expected error for %s", tt.name)
			}
		})
	}
}

func TestValidateAuth_AuthMode(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	env := map[string]string{"DECEPTICON_MODEL_PROVIDER": "auth"}

	// auth mode without credentials file → error
	if err := ValidateAuth(env); err == nil {
		t.Error("expected error when ~/.claude/.credentials.json is missing")
	}

	credDir := filepath.Join(home, ".claude")
	if err := os.MkdirAll(credDir, 0o755); err != nil {
		t.Fatal(err)
	}
	credPath := filepath.Join(credDir, ".credentials.json")

	// malformed JSON → error
	if err := os.WriteFile(credPath, []byte("not-json"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := ValidateAuth(env); err == nil {
		t.Error("expected error for malformed credentials JSON")
	}

	// valid JSON but no access token → error
	if err := os.WriteFile(credPath, []byte("{}"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := ValidateAuth(env); err == nil {
		t.Error("expected error when credentials JSON has no access token")
	}

	// current nested format (claudeAiOauth.accessToken) → ok
	current := `{"claudeAiOauth":{"accessToken":"sk-ant-oat01-test-token-of-sufficient-length"}}`
	if err := os.WriteFile(credPath, []byte(current), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := ValidateAuth(env); err != nil {
		t.Errorf("unexpected error for current format: %v", err)
	}

	// legacy top-level accessToken → ok
	legacy := `{"accessToken":"sk-ant-oat01-legacy-token"}`
	if err := os.WriteFile(credPath, []byte(legacy), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := ValidateAuth(env); err != nil {
		t.Errorf("unexpected error for legacy accessToken format: %v", err)
	}

	// legacy oauthToken → ok
	legacyOAuth := `{"oauthToken":"sk-ant-oat01-emulator-token"}`
	if err := os.WriteFile(credPath, []byte(legacyOAuth), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := ValidateAuth(env); err != nil {
		t.Errorf("unexpected error for legacy oauthToken format: %v", err)
	}
}

func TestValidateAuth_UnknownMode(t *testing.T) {
	env := map[string]string{"DECEPTICON_MODEL_PROVIDER": "telepathy"}
	if err := ValidateAuth(env); err == nil {
		t.Error("expected error for unknown provider mode")
	}
}

func TestWriteEnv(t *testing.T) {
	dir := t.TempDir()
	tmplPath := filepath.Join(dir, ".env.example")
	outPath := filepath.Join(dir, "out", ".env")

	template := `# Config
ANTHROPIC_API_KEY=your-anthropic-key-here
OPENAI_API_KEY=your-openai-key-here
DECEPTICON_MODEL_PROFILE=eco
`
	if err := os.WriteFile(tmplPath, []byte(template), 0o644); err != nil {
		t.Fatal(err)
	}

	values := map[string]string{
		"ANTHROPIC_API_KEY":       "sk-real-key",
		"DECEPTICON_MODEL_PROFILE": "max",
	}

	if err := WriteEnv(tmplPath, outPath, values); err != nil {
		t.Fatalf("WriteEnv() error: %v", err)
	}

	env, err := LoadEnv(outPath)
	if err != nil {
		t.Fatalf("LoadEnv() error: %v", err)
	}

	if env["ANTHROPIC_API_KEY"] != "sk-real-key" {
		t.Errorf("ANTHROPIC_API_KEY = %q, want %q", env["ANTHROPIC_API_KEY"], "sk-real-key")
	}
	if env["OPENAI_API_KEY"] != "your-openai-key-here" {
		t.Errorf("OPENAI_API_KEY should stay as template value")
	}
	if env["DECEPTICON_MODEL_PROFILE"] != "max" {
		t.Errorf("DECEPTICON_MODEL_PROFILE = %q, want %q", env["DECEPTICON_MODEL_PROFILE"], "max")
	}
}

func TestDecepticonHome(t *testing.T) {
	// With DECEPTICON_HOME set
	t.Setenv("DECEPTICON_HOME", "/custom/path")
	if got := DecepticonHome(); got != "/custom/path" {
		t.Errorf("DecepticonHome() = %q, want /custom/path", got)
	}

	// Without DECEPTICON_HOME — falls back to ~/.decepticon
	t.Setenv("DECEPTICON_HOME", "")
	home := DecepticonHome()
	if !filepath.IsAbs(home) {
		t.Errorf("DecepticonHome() = %q, want absolute path", home)
	}
}

func TestGet(t *testing.T) {
	env := map[string]string{"KEY": "val"}
	if Get(env, "KEY", "default") != "val" {
		t.Error("expected val")
	}
	if Get(env, "MISSING", "default") != "default" {
		t.Error("expected default")
	}
}
