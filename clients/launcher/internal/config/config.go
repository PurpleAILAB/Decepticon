package config

import (
	"bufio"
	_ "embed"
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
	"GOOGLE_API_KEY",
	"MINIMAX_API_KEY",
}

// IsPlaceholder checks if a value looks like a placeholder.
func IsPlaceholder(val string) bool {
	return strings.HasSuffix(val, PlaceholderSuffix) || val == ""
}

// ValidateAPIKeys checks that at least one API key is a real value.
func ValidateAPIKeys(env map[string]string) error {
	for _, name := range APIKeyNames {
		if val, ok := env[name]; ok && !IsPlaceholder(val) {
			return nil
		}
	}
	return fmt.Errorf("no valid API key found; run 'decepticon onboard' to configure")
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
