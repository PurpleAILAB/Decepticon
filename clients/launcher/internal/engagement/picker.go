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

// isReady reports whether a single engagement carries the full planning
// bundle (roe.json + conops.json + deconfliction.json). Used both for sorting
// the picker (ready engagements bubble up) and for deciding which assistant
// to route to when the operator resumes one.
func isReady(home, slug string) bool {
	plan := filepath.Join(home, "workspace", slug, "plan")
	for _, name := range []string{"roe.json", "conops.json", "deconfliction.json"} {
		if _, err := os.Stat(filepath.Join(plan, name)); err != nil {
			return false
		}
	}
	return true
}

// engagementEntry pairs a slug with metadata used for picker rendering and
// downstream assistant selection.
type engagementEntry struct {
	Slug  string
	Ready bool
	mtime int64
}

// ScanEngagements returns every directory under home/workspace/ regardless
// of completeness. Each entry carries a Ready flag so the picker can mark
// in-progress engagements and the launcher can pick the right assistant on
// resume (ready → decepticon, incomplete → soundwave to finish the
// interview). Sort: ready engagements first (most recent RoE), in-progress
// engagements second (most recent dir mtime).
func ScanEngagements(home string) ([]engagementEntry, error) {
	root := filepath.Join(home, "workspace")
	entries, err := os.ReadDir(root)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("read workspace: %w", err)
	}

	var out []engagementEntry
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		slug := e.Name()
		entry := engagementEntry{Slug: slug, Ready: isReady(home, slug)}
		if entry.Ready {
			if st, err := os.Stat(filepath.Join(root, slug, "plan", "roe.json")); err == nil {
				entry.mtime = st.ModTime().Unix()
			}
		} else if info, err := e.Info(); err == nil {
			entry.mtime = info.ModTime().Unix()
		}
		out = append(out, entry)
	}

	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Ready != out[j].Ready {
			return out[i].Ready
		}
		return out[i].mtime > out[j].mtime
	})
	return out, nil
}

// listAllSlugs returns every directory name under home/workspace, used for
// new-slug collision detection (a partial engagement is still a name clash).
func listAllSlugs(home string) ([]string, error) {
	all, err := ScanEngagements(home)
	if err != nil {
		return nil, err
	}
	out := make([]string, len(all))
	for i, e := range all {
		out[i] = e.Slug
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

// Select shows the engagement picker. The list always carries "[+] New"
// plus every existing engagement under home/workspace/, completed or
// in-progress alike — partial engagements (interview interrupted, planning
// not yet finalised) must be resumable.
//
// Resume routing:
//   - Ready engagements (full planning bundle) → decepticon assistant.
//   - In-progress engagements                  → soundwave assistant so
//     the interview lane can finish the missing documents.
//
// "[+] New" triggers a chained slug-input prompt; the host directory is
// created before the sandbox starts so the bind has somewhere to point at.
func Select(home string) (Choice, error) {
	all, err := ScanEngagements(home)
	if err != nil {
		ui.Warning("Could not scan engagements: " + err.Error())
		all = nil
	}

	const newSentinel = "__new__"

	picked := newSentinel
	var newSlug string

	options := make([]huh.Option[string], 0, len(all)+1)
	options = append(options, huh.NewOption("[+] New engagement (Soundwave interview)", newSentinel))
	for _, e := range all {
		label := "Resume " + e.Slug
		if !e.Ready {
			label += "  (in progress)"
		}
		options = append(options, huh.NewOption(label, e.Slug))
	}

	form := huh.NewForm(
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("Engagement").
				Description("Pick an existing engagement or start a new one with Soundwave.").
				Options(options...).
				Value(&picked),
		).Title("Decepticon").Description("Engagement selection"),
		huh.NewGroup(
			huh.NewInput().
				Title("Engagement name").
				Description("Lowercase, hyphens allowed. Used as the workspace directory name (e.g., acme-external-2026).").
				Placeholder("e.g., acme-external-2026").
				Value(&newSlug).
				Validate(func(s string) error { return validateSlug(home, s) }),
		).Title("New engagement").Description("Create the engagement workspace").
			WithHideFunc(func() bool { return picked != newSentinel }),
	).WithTheme(huh.ThemeFunc(ui.DecepticonTheme))

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

	assistant := AssistantSoundwave
	if isReady(home, picked) {
		assistant = AssistantDecepticon
	}
	return Choice{
		AssistantID:   assistant,
		Engagement:    picked,
		WorkspacePath: filepath.Join(root, picked),
	}, nil
}
