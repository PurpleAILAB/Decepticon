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

	// One real key → ok
	env["ANTHROPIC_API_KEY"] = "sk-ant-real-key"
	if err := ValidateAPIKeys(env); err != nil {
		t.Errorf("unexpected error: %v", err)
	}

	// Empty env → error
	if err := ValidateAPIKeys(map[string]string{}); err == nil {
		t.Error("expected error for empty env")
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
