package config

import (
	"bufio"
	_ "embed"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

//go:embed env.example
var EnvTemplate string

const (
	DefaultHome       = ".decepticon"
	EnvFileName       = ".env"
	EnvExampleName    = ".env.example"
	PlaceholderSuffix = "-key-here"
)

// Config holds the Decepticon launcher configuration.
type Config struct {
	Home string
	Env  map[string]string
}

// DecepticonHome returns the resolved DECEPTICON_HOME path.
func DecepticonHome() string {
	if h := os.Getenv("DECEPTICON_HOME"); h != "" {
		return h
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return filepath.Join("~", DefaultHome)
	}
	return filepath.Join(home, DefaultHome)
}

// EnvPath returns the full path to the .env file.
func EnvPath() string {
	return filepath.Join(DecepticonHome(), EnvFileName)
}

// EnvExists checks whether .env exists.
func EnvExists() bool {
	_, err := os.Stat(EnvPath())
	return err == nil
}

// LoadEnv reads a .env file and returns key-value pairs.
// It handles comments (#), empty lines, and optional quoting.
func LoadEnv(path string) (map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open env file: %w", err)
	}
	defer f.Close()

	env := make(map[string]string)
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, val, ok := parseEnvLine(line)
		if !ok {
			continue
		}
		env[key] = val
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read env file: %w", err)
	}
	return env, nil
}

// parseEnvLine splits "KEY=VALUE" handling optional quotes.
func parseEnvLine(line string) (key, val string, ok bool) {
	idx := strings.IndexByte(line, '=')
	if idx < 1 {
		return "", "", false
	}
	key = strings.TrimSpace(line[:idx])
	val = strings.TrimSpace(line[idx+1:])
	// Strip surrounding quotes
	if len(val) >= 2 {
		if (val[0] == '"' && val[len(val)-1] == '"') ||
			(val[0] == '\'' && val[len(val)-1] == '\'') {
			val = val[1 : len(val)-1]
		}
	}
	return key, val, true
}

// WriteEnvFromEmbed writes key-value pairs into a .env file using the embedded template.
func WriteEnvFromEmbed(outputPath string, values map[string]string) error {
	return writeEnvFromString(EnvTemplate, outputPath, values)
}

// WriteEnv writes key-value pairs into a .env file using a template file.
func WriteEnv(templatePath, outputPath string, values map[string]string) error {
	tmpl, err := os.ReadFile(templatePath)
	if err != nil {
		return fmt.Errorf("read template: %w", err)
	}
	return writeEnvFromString(string(tmpl), outputPath, values)
}

func writeEnvFromString(tmpl string, outputPath string, values map[string]string) error {
	lines := strings.Split(tmpl, "\n")
	var out []string
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		// Skip commented lines — keep as-is
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			out = append(out, line)
			continue
		}
		key, _, ok := parseEnvLine(trimmed)
		if !ok {
			out = append(out, line)
			continue
		}
		if newVal, exists := values[key]; exists {
			out = append(out, key+"="+newVal)
		} else {
			out = append(out, line)
		}
	}

	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return fmt.Errorf("create directory: %w", err)
	}
	return os.WriteFile(outputPath, []byte(strings.Join(out, "\n")), 0o600)
}

// APIKeyNames lists the API key environment variable names to check.
var APIKeyNames = []string{
	"ANTHROPIC_API_KEY",
	"OPENAI_API_KEY",
	"GEMINI_API_KEY",
	"MINIMAX_API_KEY",
}

// IsPlaceholder checks if a value looks like a placeholder.
func IsPlaceholder(val string) bool {
	return strings.HasSuffix(val, PlaceholderSuffix) || val == ""
}

// keyFormatRules maps an API key env var to its expected prefix and human-readable hint.
// Format checks are intentionally lenient — providers occasionally evolve key shapes
// (OpenAI shipped sk-proj-* in 2024, Anthropic sk-ant-api03-* etc.). The check only
// rejects values that are obviously malformed (typos, missing prefix).
var keyFormatRules = map[string]struct {
	Prefix string
	Hint   string
}{
	"ANTHROPIC_API_KEY": {Prefix: "sk-", Hint: "Anthropic keys start with 'sk-'"},
	"OPENAI_API_KEY":    {Prefix: "sk-", Hint: "OpenAI keys start with 'sk-'"},
	"GEMINI_API_KEY":    {Prefix: "AIza", Hint: "Gemini keys start with 'AIza'"},
}

// validateKeyFormat returns an empty string if the key looks valid, or a reason if not.
func validateKeyFormat(name, val string) string {
	if len(val) < 20 {
		return "value is too short to be a valid API key"
	}
	if rule, ok := keyFormatRules[name]; ok {
		if !strings.HasPrefix(val, rule.Prefix) {
			return rule.Hint
		}
	}
	return ""
}

// ValidateAPIKeys checks that at least one API key is set with a valid format.
// Returns a fatal error listing both unset keys and any format problems found.
func ValidateAPIKeys(env map[string]string) error {
	var validNames []string
	invalidReasons := make(map[string]string)

	for _, name := range APIKeyNames {
		val := env[name]
		if val == "" || IsPlaceholder(val) {
			continue
		}
		if reason := validateKeyFormat(name, val); reason != "" {
			invalidReasons[name] = reason
			continue
		}
		validNames = append(validNames, name)
	}

	if len(validNames) > 0 {
		return nil
	}

	var msg strings.Builder
	msg.WriteString("no valid API key found.")
	if len(invalidReasons) > 0 {
		msg.WriteString(" Detected malformed key(s):")
		for name, reason := range invalidReasons {
			msg.WriteString(fmt.Sprintf("\n  %s: %s", name, reason))
		}
	}
	msg.WriteString("\nRun 'decepticon onboard --reset' to reconfigure credentials.")
	return fmt.Errorf("%s", msg.String())
}

// ValidateAuth ensures at least one valid AuthMethod is configured.
//
// OAuth path: DECEPTICON_AUTH_CLAUDE_CODE=true (set by the onboard wizard
// when Claude Code OAuth is selected) requires a parseable
// ~/.claude/.credentials.json with an access token. LiteLLM mounts the
// file read-only at runtime; missing or empty fails opaquely on the
// first prompt unless we catch it here.
//
// API path: at least one ANTHROPIC / OPENAI / GEMINI / MINIMAX_API_KEY
// must be set to a non-placeholder, well-formed value.
//
// At least one path must succeed. When OAuth is requested and its
// credentials file is broken, the API path is checked as a fallback;
// if both fail, the OAuth error is surfaced because that was the
// user's explicit choice.
func ValidateAuth(env map[string]string) error {
	oauthEnabled := isTruthy(Get(env, "DECEPTICON_AUTH_CLAUDE_CODE", ""))
	apiErr := ValidateAPIKeys(env)

	if oauthEnabled {
		if oauthErr := validateClaudeCredentials(); oauthErr == nil {
			return nil
		} else if apiErr == nil {
			return nil
		} else {
			return oauthErr
		}
	}

	return apiErr
}

func isTruthy(s string) bool {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "true", "1", "yes", "on":
		return true
	}
	return false
}

// validateClaudeCredentials verifies ~/.claude/.credentials.json exists, is a regular
// file, parses as JSON, and carries an access token in one of the shapes the LiteLLM
// claude_code_handler accepts (claudeAiOauth.accessToken, top-level accessToken, or
// legacy oauthToken). Compose mounts this path into the LiteLLM container; if it's
// missing or empty, authentication fails opaquely on the first prompt instead of here.
func validateClaudeCredentials() error {
	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("locate home directory: %w", err)
	}
	path := filepath.Join(home, ".claude", ".credentials.json")
	info, err := os.Stat(path)
	if os.IsNotExist(err) {
		return fmt.Errorf("Claude Code credentials not found at %s\nRun 'claude /login' (Claude Code CLI) to authenticate, then retry.", path)
	}
	if err != nil {
		return fmt.Errorf("stat %s: %w", path, err)
	}
	if info.IsDir() {
		return fmt.Errorf("expected credentials file at %s but found a directory.\nRemove it and run 'claude /login' to re-authenticate.", path)
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read %s: %w\nCheck file permissions and re-run.", path, err)
	}
	var creds map[string]any
	if err := json.Unmarshal(raw, &creds); err != nil {
		return fmt.Errorf("credentials file at %s is not valid JSON: %w\nRun 'claude /login' to re-authenticate.", path, err)
	}
	if extractClaudeAccessToken(creds) == "" {
		return fmt.Errorf("no access token found in %s\nRun 'claude /login' to re-authenticate.", path)
	}
	return nil
}

// extractClaudeAccessToken walks the credentials JSON in the same resolution order as
// the LiteLLM handler (config/claude_code_handler.py): current nested format first,
// then legacy top-level keys. Returns "" if no usable token is present.
func extractClaudeAccessToken(creds map[string]any) string {
	if oauth, ok := creds["claudeAiOauth"].(map[string]any); ok {
		if tok, _ := oauth["accessToken"].(string); tok != "" {
			return tok
		}
	}
	if tok, _ := creds["accessToken"].(string); tok != "" {
		return tok
	}
	if tok, _ := creds["oauthToken"].(string); tok != "" {
		return tok
	}
	return ""
}

// AppendEnvLine appends a KEY=VALUE line to an existing .env file.
func AppendEnvLine(path, key, value string) error {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = fmt.Fprintf(f, "\n%s=%s\n", key, value)
	return err
}

// Get returns a config value with a fallback default.
func Get(env map[string]string, key, fallback string) string {
	if val, ok := env[key]; ok && val != "" {
		return val
	}
	return fallback
}
