// Package engagement scans the host workspace for ready engagements and
// presents a Huh-based picker that decides which assistant the CLI should
// connect to (decepticon vs soundwave) and which host directory the
// sandbox container should bind-mount as /workspace.
package engagement

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"

	"charm.land/huh/v2"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
)

// AssistantSoundwave drives the document-writing interview for a fresh engagement.
const AssistantSoundwave = "soundwave"

// AssistantDecepticon drives kill-chain execution against an existing engagement.
const AssistantDecepticon = "decepticon"

// Slug regex: lowercase alphanumeric with internal hyphens, 3-64 chars.
// First and last char must be alphanumeric — disallows leading/trailing hyphens
// to keep filesystem and URL semantics simple.
var slugRe = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`)

// Choice carries the picker result back to the launcher.
type Choice struct {
	// AssistantID is the LangGraph assistant the CLI should connect to.
	AssistantID string
	// Engagement is the engagement slug. Always set — the launcher prompts for
	// it on new engagements.
	Engagement string
	// WorkspacePath is the absolute host path the sandbox should bind to
	// /workspace. The launcher exports it as DECEPTICON_ENGAGEMENT_WORKSPACE
	// before bringing the compose stack up.
	WorkspacePath string
}

// ScanReady returns the slugs under home/workspace/ that already carry the
// full ready-bundle (roe.json + conops.json + deconfliction.json). Slugs are
// returned sorted by most-recently-modified RoE first so the operator's
// active work surfaces at the top of the picker.
func ScanReady(home string) ([]string, error) {
	root := filepath.Join(home, "workspace")
	entries, err := os.ReadDir(root)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("read workspace: %w", err)
	}

	type slugMTime struct {
		slug  string
		mtime int64
	}
	var ready []slugMTime
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		plan := filepath.Join(root, e.Name(), "plan")
		roe, err1 := os.Stat(filepath.Join(plan, "roe.json"))
		_, err2 := os.Stat(filepath.Join(plan, "conops.json"))
		_, err3 := os.Stat(filepath.Join(plan, "deconfliction.json"))
		if err1 != nil || err2 != nil || err3 != nil {
			continue
		}
		ready = append(ready, slugMTime{slug: e.Name(), mtime: roe.ModTime().Unix()})
	}
	sort.SliceStable(ready, func(i, j int) bool { return ready[i].mtime > ready[j].mtime })

	out := make([]string, len(ready))
	for i, r := range ready {
		out[i] = r.slug
	}
	return out, nil
}

// listAllSlugs returns every directory name under home/workspace, used for
// new-slug collision detection (a partial engagement is still a name clash).
func listAllSlugs(home string) ([]string, error) {
	root := filepath.Join(home, "workspace")
	entries, err := os.ReadDir(root)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("read workspace: %w", err)
	}
	var out []string
	for _, e := range entries {
		if e.IsDir() {
			out = append(out, e.Name())
		}
	}
	return out, nil
}

// validateSlug enforces the slug regex and rejects collisions with any
// existing directory under home/workspace.
func validateSlug(home, slug string) error {
	if !slugRe.MatchString(slug) {
		return fmt.Errorf(
			"engagement name must be 3-64 chars, lowercase letters / digits / "+
				"internal hyphens (got %q)",
			slug,
		)
	}
	existing, err := listAllSlugs(home)
	if err != nil {
		return err
	}
	for _, s := range existing {
		if s == slug {
			return fmt.Errorf("engagement %q already exists — pick a different name or resume it", slug)
		}
	}
	return nil
}

// Select shows the engagement picker. When ready engagements exist the
// operator picks one or chooses "[+] New". For "new", a second prompt
// captures the slug (validated + collision-checked), creates the host
// directory, and the launcher uses that directory as the sandbox bind.
//
// When the workspace has zero ready engagements (first-time install), the
// picker still prompts for a slug — the operator must commit to a name
// before the sandbox starts.
func Select(home string) (Choice, error) {
	ready, err := ScanReady(home)
	if err != nil {
		ui.Warning("Could not scan engagements: " + err.Error())
		ready = nil
	}

	const newSentinel = "__new__"

	picked := newSentinel
	var newSlug string

	groups := []*huh.Group{}

	if len(ready) > 0 {
		options := make([]huh.Option[string], 0, len(ready)+1)
		options = append(options, huh.NewOption("[+] New engagement (Soundwave interview)", newSentinel))
		for _, slug := range ready {
			options = append(options, huh.NewOption("Resume "+slug, slug))
		}
		groups = append(groups, huh.NewGroup(
			huh.NewSelect[string]().
				Title("Engagement").
				Description("Pick an existing engagement or start a new one with Soundwave.").
				Options(options...).
				Value(&picked),
		).Title("Decepticon").Description("Engagement selection"))
	}

	groups = append(groups, huh.NewGroup(
		huh.NewInput().
			Title("Engagement name").
			Description("Lowercase, hyphens allowed. Used as the workspace directory name (e.g., acme-external-2026).").
			Placeholder("e.g., acme-external-2026").
			Value(&newSlug).
			Validate(func(s string) error { return validateSlug(home, s) }),
	).Title("New engagement").Description("Create the engagement workspace").
		WithHideFunc(func() bool { return picked != newSentinel }))

	form := huh.NewForm(groups...).WithTheme(huh.ThemeFunc(ui.DecepticonTheme))
	if err := form.Run(); err != nil {
		return Choice{}, fmt.Errorf("engagement picker cancelled: %w", err)
	}

	root := filepath.Join(home, "workspace")
	if picked == newSentinel {
		dir := filepath.Join(root, newSlug)
		if err := os.MkdirAll(filepath.Join(dir, "plan"), 0o755); err != nil {
			return Choice{}, fmt.Errorf("create engagement dir: %w", err)
		}
		return Choice{
			AssistantID:   AssistantSoundwave,
			Engagement:    newSlug,
			WorkspacePath: dir,
		}, nil
	}

	return Choice{
		AssistantID:   AssistantDecepticon,
		Engagement:    picked,
		WorkspacePath: filepath.Join(root, picked),
	}, nil
}
