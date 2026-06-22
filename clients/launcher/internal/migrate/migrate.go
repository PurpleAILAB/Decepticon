// Package migrate runs idempotent, ordered upgrade steps at
// `decepticon start` so that already-onboarded users — who never re-run
// the onboard wizard (cmd/start.go only invokes it when .env is absent) —
// still pick up config keys and policy changes introduced by later
// releases.
//
// There are two kinds of step:
//
//   - Non-interactive (Interactive=false): a pure, self-idempotent config
//     migration. Runs on EVERY start regardless of TTY and is never
//     ack-recorded (so it keeps catching newly-added keys after each
//     update). Example: backfilling new env.example keys into an existing
//     .env.
//
//   - Interactive (Interactive=true): a one-time prompt, e.g. a consent
//     re-ask after a policy change. It is recorded in the ack store so it
//     runs at most once, and is SILENTLY SKIPPED (deferred) when stdin is
//     not a TTY — so CI / piped starts are never blocked and the next
//     interactive start reconsiders.
//
// Adding a future migration is one line: append a Step to Registry().
// That is the whole mechanism; no new wiring in start.go.
package migrate

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"golang.org/x/term"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
)

// ackFileName is the JSON record of interactive migrations the user has
// already been through, stored inside DECEPTICON_HOME.
const ackFileName = ".migrations.json"

// Ctx is the shared state threaded through every step.
type Ctx struct {
	EnvPath string
	Env     map[string]string // current .env, mutated as steps write
	Home    string
	IsTTY   bool

	ackPath string
	acks    map[string]string
}

// Step is one upgrade applied at start. See the package doc for the
// interactive vs non-interactive contract.
type Step struct {
	ID          string
	Description string
	Interactive bool
	// Apply performs the migration and returns a human note to surface
	// (empty for "nothing happened"). For interactive steps a nil error
	// records the ack so the step never runs again.
	Apply func(c *Ctx) (note string, err error)
}

// Indirections so tests can drive the framework without a real TTY or
// Huh prompt.
var (
	isInteractive = func() bool { return term.IsTerminal(int(os.Stdin.Fd())) }
)

// RunAll builds a real Ctx from the launcher environment and applies the
// registered steps. env is the already-loaded .env map; steps may mutate
// it so the rest of `start` sees post-migration values.
func RunAll(env map[string]string) {
	home := config.DecepticonHome()
	c := &Ctx{
		EnvPath: config.EnvPath(),
		Env:     env,
		Home:    home,
		IsTTY:   isInteractive(),
		ackPath: filepath.Join(home, ackFileName),
	}
	c.loadAcks()
	Run(c, Registry())
}

// Run applies steps in order against c. Errors are surfaced as warnings
// and never abort the start flow.
func Run(c *Ctx, steps []Step) {
	for _, s := range steps {
		if s.Interactive {
			if c.Acked(s.ID) {
				continue
			}
			if !c.IsTTY {
				continue // defer to the next interactive start
			}
		}
		note, err := s.Apply(c)
		if err != nil {
			ui.Warning(fmt.Sprintf("migration %q: %v", s.ID, err))
			continue
		}
		if note != "" {
			ui.Info(note)
		}
		if s.Interactive {
			if ackErr := c.ack(s.ID); ackErr != nil {
				ui.Warning(fmt.Sprintf("could not record migration %q: %v", s.ID, ackErr))
			}
		}
	}
}

// MarkAcked records an interactive migration as already handled. The
// onboard wizard calls this for the telemetry policy so a fresh install —
// which just made the same choice in the wizard — never gets re-prompted
// at first start.
func MarkAcked(home, id string) error {
	c := &Ctx{ackPath: filepath.Join(home, ackFileName)}
	c.loadAcks()
	return c.ack(id)
}

// Acked reports whether the interactive migration id has been recorded.
func (c *Ctx) Acked(id string) bool {
	_, ok := c.acks[id]
	return ok
}

func (c *Ctx) loadAcks() {
	c.acks = map[string]string{}
	data, err := os.ReadFile(c.ackPath)
	if err != nil {
		return
	}
	_ = json.Unmarshal(data, &c.acks)
}

func (c *Ctx) ack(id string) error {
	if c.acks == nil {
		c.acks = map[string]string{}
	}
	c.acks[id] = "acked"
	if err := os.MkdirAll(filepath.Dir(c.ackPath), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(c.acks, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(c.ackPath, data, 0o600)
}
