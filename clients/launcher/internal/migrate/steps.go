package migrate

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"charm.land/huh/v2"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
)

// TelemetryPolicyID identifies the one-time telemetry re-consent prompt.
// Bumping the date suffix (a new step ID) re-asks every user again after a
// future policy change.
const TelemetryPolicyID = "telemetry-policy-2026-06"

// confirm is indirected so tests can answer the prompt without a TTY.
var confirm = func(title, description, affirmative, negative string, defaultYes bool) bool {
	v := defaultYes
	if err := huh.NewConfirm().
		Title(title).
		Description(description).
		Affirmative(affirmative).
		Negative(negative).
		Value(&v).
		Run(); err != nil {
		// A prompt error (e.g. aborted) must not silently enable a
		// data-collection setting — fail to the conservative answer.
		return false
	}
	return v
}

// Registry is the ordered list of migrations applied at every start.
// Append a Step here to ship a future config/policy migration.
func Registry() []Step {
	return []Step{
		{
			ID:          "env-backfill",
			Description: "Backfill newly-added env.example keys into an existing .env",
			Interactive: false,
			Apply:       applyEnvBackfill,
		},
		{
			ID:          TelemetryPolicyID,
			Description: "Re-ask telemetry consent after the opt-out policy change",
			Interactive: true,
			Apply:       applyTelemetryReconsent,
		},
	}
}

func applyEnvBackfill(c *Ctx) (string, error) {
	added, err := config.BackfillEnvFromEmbed(c.EnvPath)
	if err != nil {
		return "", err
	}
	if len(added) == 0 {
		return "", nil
	}
	// Reflect the new keys into the in-memory env so the rest of `start`
	// sees them this run (without clobbering anything already loaded).
	if reloaded, lerr := config.LoadEnv(c.EnvPath); lerr == nil {
		for k, v := range reloaded {
			if _, ok := c.Env[k]; !ok {
				c.Env[k] = v
			}
		}
	}
	shown := added
	const cap = 8
	suffix := ""
	if len(added) > cap {
		shown = added[:cap]
		suffix = fmt.Sprintf(", +%d more", len(added)-cap)
	}
	return fmt.Sprintf(
		"Added %d new config key(s) to .env: %s%s (backup at %s.bak)",
		len(added), strings.Join(shown, ", "), suffix, c.EnvPath,
	), nil
}

const telemetryConsentBlurb = "" +
	"Decepticon is free and open source. Sharing anonymous usage helps fund\n" +
	"and improve it, and — with your consent — contributes masked red-team\n" +
	"reasoning to train future open offensive-security agents.\n\n" +
	"What is shared (research tier):\n" +
	"  • anonymous structural stats (tools used, finding severity/CWE, phase)\n" +
	"  • the agent's red-team REASONING, with target identifiers MASKED\n" +
	"    (10.0.0.5 -> <HOST_1>, acme.com -> <DOMAIN_1>)\n\n" +
	"Never sent at any tier: raw prompts, real target IPs/hosts, credentials.\n" +
	"Your IP is dropped at the gateway.\n\n" +
	"You can change this anytime: set DECEPTICON_TELEMETRY=off (or basic) in\n" +
	"~/.decepticon/.env, run `decepticon-cli telemetry off`, or DO_NOT_TRACK=1."

func applyTelemetryReconsent(c *Ctx) (string, error) {
	// Honor hard opt-outs without prompting (and record the ack so we
	// never re-ask): DO_NOT_TRACK, or the persistent opt-out marker
	// written by `decepticon-cli telemetry off`.
	if truthy(os.Getenv("DO_NOT_TRACK")) || truthy(c.Env["DO_NOT_TRACK"]) || hasOptOutMarker(c.Home) {
		return "", nil
	}

	consent := confirm(
		"Share anonymous + masked red-team telemetry?",
		telemetryConsentBlurb,
		"Yes, share (recommended)",
		"No, keep it off",
		true, // default Yes
	)

	mode := "research"
	if !consent {
		mode = "off"
	}
	if err := config.SetEnvKey(c.EnvPath, "DECEPTICON_TELEMETRY", mode); err != nil {
		return "", err
	}
	c.Env["DECEPTICON_TELEMETRY"] = mode

	if consent {
		return "Telemetry: research tier enabled (identifiers masked). " +
			"Disable anytime with DECEPTICON_TELEMETRY=off or DO_NOT_TRACK=1.", nil
	}
	return "Telemetry: kept off.", nil
}

// hasOptOutMarker mirrors the Python config's persistent opt-out marker at
// $DECEPTICON_HOME/telemetry/opt_out (decepticon_core/.../telemetry).
func hasOptOutMarker(home string) bool {
	_, err := os.Stat(filepath.Join(home, "telemetry", "opt_out"))
	return err == nil
}

func truthy(v string) bool {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "1", "true", "yes", "on":
		return true
	}
	return false
}
