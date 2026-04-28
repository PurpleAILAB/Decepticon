// Bubbletea-based prompt primitives shared across launcher commands.
//
// These replace huh forms in flows that benefit from the same look-and-feel
// as the engagement picker (single-key navigation, item-level highlighting).
// Each prompt runs as its own tea.Program; sequential prompts compose into a
// multi-step form by calling them in order.
//
// Cancellation: any prompt returns ErrPromptCancelled when the operator hits
// esc / ctrl+c. Callers wrap the error to produce a user-friendly message.

package ui

import (
	"errors"
	"fmt"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/bubbles/v2/textinput"
	"charm.land/lipgloss/v2"
)

// ErrPromptCancelled is returned when the operator cancels a prompt with esc
// or ctrl+c.
var ErrPromptCancelled = errors.New("prompt cancelled")

// ── Shared prompt styles ────────────────────────────────────────────────────

var (
	promptTitle  = lipgloss.NewStyle().Foreground(lipgloss.Color("#ef4444")).Bold(true)
	promptDesc   = lipgloss.NewStyle().Faint(true)
	promptCursor = lipgloss.NewStyle().Foreground(lipgloss.Color("#06b6d4")) // cyan
	promptHint   = lipgloss.NewStyle().Faint(true)
	promptError  = lipgloss.NewStyle().Foreground(lipgloss.Color("#ef4444"))
)

// ── Select prompt ──────────────────────────────────────────────────────────

// SelectOption is one entry in a Select prompt. Label is shown to the
// operator; Value is what Select returns when the entry is chosen.
type SelectOption struct {
	Label       string
	Description string
	Value       string
}

type selectModel struct {
	title       string
	description string
	options     []SelectOption
	cursor      int
	chosen      bool
	cancelled   bool
}

func (m selectModel) Init() tea.Cmd { return nil }

func (m selectModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	if k, ok := msg.(tea.KeyMsg); ok {
		switch k.String() {
		case "esc", "ctrl+c", "q":
			m.cancelled = true
			return m, tea.Quit
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.options)-1 {
				m.cursor++
			}
		case "enter":
			m.chosen = true
			return m, tea.Quit
		}
	}
	return m, nil
}

func (m selectModel) View() tea.View {
	var b strings.Builder
	b.WriteString(promptTitle.Render(m.title))
	b.WriteString("\n")
	if m.description != "" {
		b.WriteString(promptDesc.Render(m.description))
		b.WriteString("\n")
	}
	b.WriteString("\n")
	for i, opt := range m.options {
		if i == m.cursor {
			b.WriteString(promptCursor.Render("▸ " + opt.Label))
		} else {
			b.WriteString("  " + opt.Label)
		}
		if opt.Description != "" {
			b.WriteString(promptDesc.Render("  — " + opt.Description))
		}
		b.WriteString("\n")
	}
	b.WriteString("\n")
	b.WriteString(promptHint.Render("  ↑/↓: move  enter: select  esc: cancel"))
	return tea.NewView(b.String())
}

// Select runs a single-choice picker and returns the selected option's Value,
// or ErrPromptCancelled if the operator backs out.
func Select(title, description string, options []SelectOption) (string, error) {
	if len(options) == 0 {
		return "", fmt.Errorf("ui.Select: at least one option required")
	}
	final, err := tea.NewProgram(selectModel{
		title:       title,
		description: description,
		options:     options,
	}).Run()
	if err != nil {
		return "", err
	}
	fm, ok := final.(selectModel)
	if !ok {
		return "", fmt.Errorf("ui.Select: unexpected model type")
	}
	if fm.cancelled || !fm.chosen {
		return "", ErrPromptCancelled
	}
	return fm.options[fm.cursor].Value, nil
}

// Confirm presents a two-option picker and returns true when the operator
// picks the affirmative entry. Pass empty strings to use "Yes" / "No".
func Confirm(title, description, affirmative, negative string) (bool, error) {
	if affirmative == "" {
		affirmative = "Yes"
	}
	if negative == "" {
		negative = "No"
	}
	choice, err := Select(title, description, []SelectOption{
		{Label: affirmative, Value: "yes"},
		{Label: negative, Value: "no"},
	})
	if err != nil {
		return false, err
	}
	return choice == "yes", nil
}

// ── Continue (note + advance) ──────────────────────────────────────────────

// Continue presents a note and waits for the operator to press enter. It is
// equivalent to a Select with one entry but reads more clearly at call sites
// where the page is informational rather than a choice.
func Continue(title, description string) error {
	_, err := Select(title, description, []SelectOption{
		{Label: "Continue", Value: "ok"},
	})
	return err
}

// ── Input prompt ───────────────────────────────────────────────────────────

// InputOptions configures a text input prompt.
type InputOptions struct {
	Title       string
	Description string
	Placeholder string
	// Password masks the typed characters with the textinput default cipher.
	Password bool
	// Validate is called on Enter; returning a non-nil error keeps the prompt
	// open and shows the error message under the input.
	Validate func(string) error
}

type inputModel struct {
	opts      InputOptions
	ti        textinput.Model
	submitted bool
	cancelled bool
	err       error
}

func newInputModel(opts InputOptions) inputModel {
	ti := textinput.New()
	ti.Placeholder = opts.Placeholder
	if opts.Password {
		ti.EchoMode = textinput.EchoPassword
	}
	return inputModel{opts: opts, ti: ti}
}

func (m inputModel) Init() tea.Cmd {
	return m.ti.Focus()
}

func (m inputModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	if k, ok := msg.(tea.KeyMsg); ok {
		switch k.String() {
		case "esc", "ctrl+c":
			m.cancelled = true
			return m, tea.Quit
		case "enter":
			val := m.ti.Value()
			if m.opts.Validate != nil {
				if err := m.opts.Validate(val); err != nil {
					m.err = err
					return m, nil
				}
			}
			m.submitted = true
			return m, tea.Quit
		}
	}
	var cmd tea.Cmd
	m.ti, cmd = m.ti.Update(msg)
	// Clear stale validation error on any keystroke that reaches the input.
	m.err = nil
	return m, cmd
}

func (m inputModel) View() tea.View {
	var b strings.Builder
	b.WriteString(promptTitle.Render(m.opts.Title))
	b.WriteString("\n")
	if m.opts.Description != "" {
		b.WriteString(promptDesc.Render(m.opts.Description))
		b.WriteString("\n")
	}
	b.WriteString("\n")
	b.WriteString("› ")
	b.WriteString(m.ti.View())
	b.WriteString("\n\n")
	if m.err != nil {
		b.WriteString(promptError.Render("  ! " + m.err.Error()))
		b.WriteString("\n\n")
	}
	b.WriteString(promptHint.Render("  enter: submit  esc: cancel"))
	return tea.NewView(b.String())
}

// Input runs a text input prompt. Returns the trimmed value or
// ErrPromptCancelled.
func Input(opts InputOptions) (string, error) {
	final, err := tea.NewProgram(newInputModel(opts)).Run()
	if err != nil {
		return "", err
	}
	fm, ok := final.(inputModel)
	if !ok {
		return "", fmt.Errorf("ui.Input: unexpected model type")
	}
	if fm.cancelled || !fm.submitted {
		return "", ErrPromptCancelled
	}
	return fm.ti.Value(), nil
}
