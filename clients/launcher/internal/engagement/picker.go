// Package engagement scans the host workspace for ready engagements and
// presents a Huh-based picker that decides which assistant the CLI should
// connect to (decepticon vs soundwave).
package engagement

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"charm.land/huh/v2"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
)

// AssistantSoundwave drives the document-writing interview for a fresh engagement.
const AssistantSoundwave = "soundwave"

// AssistantDecepticon drives kill-chain execution against an existing engagement.
const AssistantDecepticon = "decepticon"

// Choice carries the picker result back to the launcher.
type Choice struct {
	// AssistantID is the LangGraph assistant the CLI should connect to.
	AssistantID string
	// Engagement is the slug of the resumed engagement, empty for new ones.
	Engagement string
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

// Select shows a Huh select picker for the engagement choice. When there are
// no ready engagements, the picker is short-circuited and the operator goes
// straight to the soundwave interview lane.
func Select(home string) (Choice, error) {
	ready, err := ScanReady(home)
	if err != nil {
		// Best-effort: fall through to a soundwave-only choice on scan failure.
		ui.Warning("Could not scan engagements: " + err.Error())
		ready = nil
	}

	if len(ready) == 0 {
		return Choice{AssistantID: AssistantSoundwave}, nil
	}

	const newLabel = "__new__"
	options := make([]huh.Option[string], 0, len(ready)+1)
	options = append(options, huh.NewOption("[+] New engagement (Soundwave interview)", newLabel))
	for _, slug := range ready {
		options = append(options, huh.NewOption("Resume "+slug, slug))
	}

	var picked string
	form := huh.NewForm(
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("Engagement").
				Description("Pick an existing engagement or start a new one with Soundwave.").
				Options(options...).
				Value(&picked),
		).Title("Decepticon").Description("Engagement selection"),
	).WithTheme(huh.ThemeFunc(ui.DecepticonTheme))

	if err := form.Run(); err != nil {
		return Choice{}, fmt.Errorf("engagement picker cancelled: %w", err)
	}

	if picked == newLabel {
		return Choice{AssistantID: AssistantSoundwave}, nil
	}
	return Choice{AssistantID: AssistantDecepticon, Engagement: picked}, nil
}
