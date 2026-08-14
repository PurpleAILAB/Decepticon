package config

import (
	"strings"
	"testing"
)

func TestNewInstallationSecrets_generates_nondefault_credentials(t *testing.T) {
	// Given
	const defaultMasterKey = "sk-decepticon-master"
	const defaultDatabasePassword = "decepticon"

	// When
	secrets, err := NewInstallationSecrets()

	// Then
	if err != nil {
		t.Fatalf("NewInstallationSecrets() error = %v", err)
	}
	if secrets.LiteLLMMasterKey == defaultMasterKey {
		t.Fatal("LiteLLM master key must not use the public default")
	}
	if secrets.PostgresPassword == defaultDatabasePassword {
		t.Fatal("Postgres password must not use the public default")
	}
	if !strings.HasPrefix(secrets.LiteLLMMasterKey, "sk-") {
		t.Fatalf("LiteLLM master key = %q, want sk- prefix", secrets.LiteLLMMasterKey)
	}
	wantLengths := map[string]int{
		secrets.LiteLLMMasterKey: 67,
		secrets.LiteLLMSaltKey:   67,
		secrets.PostgresPassword: 48,
		secrets.Neo4jPassword:    64,
	}
	for value, want := range wantLengths {
		if len(value) != want {
			t.Fatalf("generated credential length = %d, want %d", len(value), want)
		}
	}
}

func TestNewInstallationSecrets_generates_independent_values(t *testing.T) {
	// Given
	const generatedSecretCount = 4

	// When
	secrets, err := NewInstallationSecrets()

	// Then
	if err != nil {
		t.Fatalf("NewInstallationSecrets() error = %v", err)
	}
	values := map[string]struct{}{
		secrets.LiteLLMMasterKey: {},
		secrets.LiteLLMSaltKey:   {},
		secrets.PostgresPassword: {},
		secrets.Neo4jPassword:    {},
	}
	if len(values) != generatedSecretCount {
		t.Fatalf("generated %d unique values, want %d", len(values), generatedSecretCount)
	}
}
