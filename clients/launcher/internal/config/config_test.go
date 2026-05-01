package config

import (
	"os"
	"path/filepath"
	"strings"
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
DECEPTICON_AUTH_PRIORITY=anthropic_api
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
		{"google missing prefix", map[string]string{"GEMINI_API_KEY": "sk-wrongprefix-key-long-enough-here"}},
		{"openrouter missing prefix", map[string]string{"OPENROUTER_API_KEY": "sk-wrongprefix-key-long-enough-here"}},
		{"nvidia missing prefix", map[string]string{"NVIDIA_API_KEY": "sk-wrongprefix-key-long-enough-here"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := ValidateAPIKeys(tt.env); err == nil {
				t.Errorf("expected error for %s", tt.name)
			}
		})
	}
}

// TestValidateAPIKeys_AcceptsAllProviders covers issue #105: keys for
// providers added past the original four (Anthropic/OpenAI/Gemini/MiniMax)
// were silently dropped because APIKeyNames + keyFormatRules only knew
// about the original four. Each provider must now satisfy the gate on
// its own.
func TestValidateAPIKeys_AcceptsAllProviders(t *testing.T) {
	tests := []struct {
		name string
		env  map[string]string
	}{
		{"openrouter", map[string]string{"OPENROUTER_API_KEY": "sk-or-realkeythatislongenough"}},
		{"nvidia", map[string]string{"NVIDIA_API_KEY": "nvapi-realkeythatislongenough"}},
		{"deepseek", map[string]string{"DEEPSEEK_API_KEY": "sk-realkeythatislongenough"}},
		{"xai", map[string]string{"XAI_API_KEY": "xai-realkeythatislongenough"}},
		{"mistral_no_prefix", map[string]string{"MISTRAL_API_KEY": "any-shape-key-of-sufficient-length"}},
		{"minimax_no_prefix", map[string]string{"MINIMAX_API_KEY": "eyJ-shaped-or-not-just-long-enough"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := ValidateAPIKeys(tt.env); err != nil {
				t.Errorf("expected %s to pass validation, got: %v", tt.name, err)
			}
		})
	}
}

// TestValidateAuth_OAuthSubscriptions verifies each subscription handler
// (Gemini Advanced / Copilot Pro / SuperGrok / Perplexity Pro) accepts
// any of its supported credential surfaces — env token or tokens.json.
// Mirrors the resolution order in config/<provider>_handler.py.
func TestValidateAuth_OAuthSubscriptions(t *testing.T) {
	cases := []struct {
		toggle      string
		envName     string
		configDir   string
		fileFmt     string
	}{
		{"DECEPTICON_AUTH_GEMINI", "GEMINI_SESSION_COOKIES", "gemini", "tokens.json"},
		{"DECEPTICON_AUTH_COPILOT", "COPILOT_REFRESH_TOKEN", "copilot", "tokens.json"},
		{"DECEPTICON_AUTH_GROK", "GROK_SESSION_TOKEN", "grok", "tokens.json"},
		{"DECEPTICON_AUTH_PERPLEXITY", "PERPLEXITY_SESSION_TOKEN", "perplexity", "tokens.json"},
	}
	for _, c := range cases {
		t.Run(c.envName+" via env", func(t *testing.T) {
			home := t.TempDir()
			t.Setenv("HOME", home)
			env := map[string]string{c.toggle: "true", c.envName: "anything-not-empty"}
			if err := ValidateAuth(env); err != nil {
				t.Errorf("expected env-token to satisfy %s: %v", c.toggle, err)
			}
		})
		t.Run(c.envName+" via tokens.json", func(t *testing.T) {
			home := t.TempDir()
			t.Setenv("HOME", home)
			dir := filepath.Join(home, ".config", c.configDir)
			if err := os.MkdirAll(dir, 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(filepath.Join(dir, c.fileFmt), []byte("{}"), 0o600); err != nil {
				t.Fatal(err)
			}
			env := map[string]string{c.toggle: "true"}
			if err := ValidateAuth(env); err != nil {
				t.Errorf("expected tokens.json to satisfy %s: %v", c.toggle, err)
			}
		})
		t.Run(c.envName+" toggle on but no creds fails", func(t *testing.T) {
			home := t.TempDir()
			t.Setenv("HOME", home)
			env := map[string]string{c.toggle: "true"}
			err := ValidateAuth(env)
			if err == nil {
				t.Errorf("expected %s with no creds to fail", c.toggle)
			}
		})
	}
}

// TestValidateAuth_OllamaLocal covers issue #106: the user picks
// ``ollama_local`` and sets OLLAMA_API_BASE, no API key needed. The
// previous gate rejected this because it only checked API-key columns.
func TestValidateAuth_OllamaLocal(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)

	t.Run("priority+base passes", func(t *testing.T) {
		env := map[string]string{
			"DECEPTICON_AUTH_PRIORITY": "ollama_local",
			"OLLAMA_API_BASE":          "http://host.docker.internal:11434",
		}
		if err := ValidateAuth(env); err != nil {
			t.Errorf("expected ollama_local to pass without API key: %v", err)
		}
	})

	t.Run("priority alone without base fails with helpful message", func(t *testing.T) {
		env := map[string]string{"DECEPTICON_AUTH_PRIORITY": "ollama_local"}
		err := ValidateAuth(env)
		if err == nil {
			t.Fatal("expected error when ollama_local is selected but base url is missing")
		}
		if !strings.Contains(err.Error(), "OLLAMA_API_BASE") {
			t.Errorf("expected error mentioning OLLAMA_API_BASE, got: %v", err)
		}
	})

	t.Run("base url alone (no priority entry) is enough", func(t *testing.T) {
		// User edits .env directly with just OLLAMA_API_BASE — accept it
		// as an opt-in signal.
		env := map[string]string{"OLLAMA_API_BASE": "http://localhost:11434"}
		if err := ValidateAuth(env); err != nil {
			t.Errorf("expected bare OLLAMA_API_BASE to satisfy auth: %v", err)
		}
	})
}

func TestValidateAuth_OAuth(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	// OAuth requested, no API keys configured.
	env := map[string]string{"DECEPTICON_AUTH_CLAUDE_CODE": "true"}

	// OAuth path without credentials file → error
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

func TestValidateAuth_OAuthFallsBackToAPIKey(t *testing.T) {
	// OAuth requested but file missing; a valid API key satisfies the
	// "at least one method works" rule.
	home := t.TempDir()
	t.Setenv("HOME", home)
	env := map[string]string{
		"DECEPTICON_AUTH_CLAUDE_CODE": "true",
		"ANTHROPIC_API_KEY":           "sk-ant-api03-realkeythatislongenough",
	}
	if err := ValidateAuth(env); err != nil {
		t.Errorf("expected fallback to API key when OAuth file missing: %v", err)
	}
}

func TestValidateAuth_NeitherConfigured(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	// No OAuth, no real API keys.
	env := map[string]string{
		"ANTHROPIC_API_KEY": "your-anthropic-key-here",
	}
	if err := ValidateAuth(env); err == nil {
		t.Error("expected error when neither OAuth nor any API key is configured")
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
