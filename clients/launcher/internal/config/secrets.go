package config

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
)

// InstallationSecrets contains the service credentials generated for a new
// launcher-managed installation.
type InstallationSecrets struct {
	LiteLLMMasterKey string
	LiteLLMSaltKey   string
	PostgresPassword string
	Neo4jPassword    string
}

// NewInstallationSecrets generates independent credentials for every service
// that otherwise inherits a public development default from .env.example.
func NewInstallationSecrets() (InstallationSecrets, error) {
	masterKey, err := randomHex(32)
	if err != nil {
		return InstallationSecrets{}, fmt.Errorf("generate LiteLLM master key: %w", err)
	}
	saltKey, err := randomHex(32)
	if err != nil {
		return InstallationSecrets{}, fmt.Errorf("generate LiteLLM salt key: %w", err)
	}
	postgresPassword, err := randomHex(24)
	if err != nil {
		return InstallationSecrets{}, fmt.Errorf("generate Postgres password: %w", err)
	}
	neo4jPassword, err := randomHex(32)
	if err != nil {
		return InstallationSecrets{}, fmt.Errorf("generate Neo4j password: %w", err)
	}

	return InstallationSecrets{
		LiteLLMMasterKey: "sk-" + masterKey,
		LiteLLMSaltKey:   "sk-" + saltKey,
		PostgresPassword: postgresPassword,
		Neo4jPassword:    neo4jPassword,
	}, nil
}

func randomHex(byteLength int) (string, error) {
	value := make([]byte, byteLength)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("read operating-system randomness: %w", err)
	}
	return hex.EncodeToString(value), nil
}
