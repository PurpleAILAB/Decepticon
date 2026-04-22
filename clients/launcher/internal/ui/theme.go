package ui

import (
	"fmt"
	"os"

	"charm.land/huh/v2"
	"charm.land/lipgloss/v2"
	"golang.org/x/term"
)

var (
	Red    = lipgloss.NewStyle().Foreground(lipgloss.Color("#FF0000"))
	Green  = lipgloss.NewStyle().Foreground(lipgloss.Color("#00FF00"))
	Yellow = lipgloss.NewStyle().Foreground(lipgloss.Color("#FFFF00")).Bold(true)
	Cyan   = lipgloss.NewStyle().Foreground(lipgloss.Color("#00FFFF"))
	Dim    = lipgloss.NewStyle().Faint(true)
	Bold   = lipgloss.NewStyle().Bold(true)

	// Banner style — red to match Ink CLI
	BannerStyle = lipgloss.NewStyle().
		Foreground(lipgloss.Color("#FF0000"))

	BannerBold = lipgloss.NewStyle().
		Foreground(lipgloss.Color("#FF0000")).
		Bold(true)
)

// Full banner: braille logo + block-character text art (≥140 cols)
const bannerFull = "" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⣶⣤⡀⠀⣤⣤⣾⣿⣦⣠⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣶⣶⣿⢿⣿⣿⣿⣿⣿⣻⣿⣟⣿⣿⣷⣾⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⢰⣿⣄⣼⣿⣆⠀⣀⣴⣾⣿⣻⣟⣷⣯⢿⡾⣯⣷⣿⣾⣯⣷⢿⡾⣿⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⣀⣸⣿⣿⣽⣯⣿⣻⣿⣟⣿⢾⣽⣟⣿⣻⣟⣿⣻⣯⡿⣾⣽⣟⣿⣽⣟⡿⣿⢿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⢠⣾⣿⣷⣽⣷⢿⣷⢟⣮⣿⣻⡿⣿⣻⣿⣽⣻⢾⣯⣿⣻⣛⠿⣾⣽⢷⡿⣾⣻⣟⣯⣿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠉⠙⢹⣷⢿⣯⡿⣿⢿⣟⣷⣿⣿⣿⣟⣯⣿⣻⢷⣿⡧⣿⢟⢮⣻⣟⣿⣽⣯⢿⣽⣿⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀██████████                                         █████     ███\n" +
	"⠀⠀⠀⠀⣼⣿⣻⣿⣾⣿⣟⣿⡾⣿⢾⣽⣟⣿⣿⡾⣯⣿⣾⣷⣽⣳⣧⣿⢿⣷⢿⡾⣿⣞⡿⣿⡀⠀⠀⠀⠀⠀⠀⠀░░███░░░░███                                       ░░███     ░░░\n" +
	"⠀⠀⠀⠀⠻⣟⢽⣿⣾⢯⣿⣾⣟⡿⣯⣿⣿⣽⢿⣟⣿⣽⣟⣾⣿⣯⢿⡾⣿⣽⣻⣟⣷⡿⣽⣿⣯⠀⠀⠀⠀⠀⠀⠀⠀░███   ░░███  ██████   ██████   ██████  ████████  ███████   ████   ██████   ██████  ████████\n" +
	"⠀⠀⠀⠀⠀⠀⠸⣿⣟⣿⣻⣾⣽⣿⣿⣻⣯⣿⣿⡿⣿⣾⣿⣿⣾⣻⣟⣿⣷⢿⣷⣯⣿⣽⢿⣾⠗⠀⠀⠀⠀⠀⠀⠀⠀░███    ░███ ███░░███ ███░░███ ███░░███░░███░░███░░░███░   ░░███  ███░░███ ███░░███░░███░░███\n" +
	"⠀⠀⠀⠀⠀⠀⢰⣿⣟⣿⢿⣿⡽⣷⣿⣿⡿⣿⡿⣿⣿⣿⣽⢷⣻⣽⣿⣿⣻⣿⣷⣿⣷⢿⠿⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀░███    ░███░███████ ░███ ░░░ ░███████  ░███ ░███  ░███     ░███ ░███ ░░░ ░███ ░███ ░███ ░███\n" +
	"⠀⠀⠀⠀⠀⠀⢸⣿⣯⣟⣿⣯⣿⣟⣿⣾⣿⣿⢿⣿⡿⣺⣷⣿⢿⡫⠷⠝⠽⠝⣟⢷⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀░███    ███ ░███░░░  ░███  ███░███░░░   ░███ ░███  ░███ ███ ░███ ░███  ███░███ ░███ ░███ ░███\n" +
	"⠀⠀⠀⠀⠀⠀⢘⣿⣾⢯⣿⣷⢿⡿⣿⣟⣿⣽⣿⣿⣝⣿⢿⠕⠁⠀⠀⢀⠄⠀⠀⠉⢻⢿⣿⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀ ██████████  ░░██████ ░░██████ ░░██████  ░███████   ░░█████  █████░░██████ ░░██████  ████ █████\n" +
	"⠀⠀⠀⠀⠀⠀⠀⣿⣿⢯⣿⣿⣻⣿⣿⣿⣻⣾⣿⣮⣿⡿⡇⠀⠀⠀⢃⣈⣤⠄⡨⠀⠈⢻⣿⡿⡄⠀⠀⠀⠀⠀⠀⠀⠀░░░░░░░░░░    ░░░░░░   ░░░░░░   ░░░░░░   ░███░░░     ░░░░░  ░░░░░  ░░░░░░   ░░░░░░  ░░░░ ░░░░░\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠸⣿⣟⣷⢿⣿⣿⣯⣿⣽⣿⣿⢮⣿⣯⠇⠀⢀⡉⢴⡽⣙⠀⠄⠀⠀⣸⣿⣟⡇⠀⠀⠀⠀⠀⠀⠀⠀                                         ░███\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠹⣿⣯⡿⣿⣾⣿⡿⣾⣷⣿⣯⢿⣿⣣⠀⠀⠀⠯⠋⡁⠐⠀⠀⢠⣟⣿⢯⠂⠀⠀⠀⠀⠀⠀⠀⠀                                         █████\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⡿⣿⣳⣿⣻⣿⣷⡿⣿⣿⣝⣿⣿⣷⣄⡀⠀⠀⠀⠈⣀⣴⣿⣿⣻⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀                                       ░░░░░\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⣻⣷⣿⣽⢿⣿⣿⣟⣿⣮⣟⣽⣿⣿⣷⣾⣾⣿⡿⣿⢯⣿⣾⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠑⠿⡿⣿⣾⣽⣟⣿⢿⣿⣷⣷⣽⣽⣫⣟⣽⣽⡾⠓⠻⣿⣿⣿⣦⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠑⠋⠟⢟⢿⢿⡷⣿⢿⢿⡻⢟⠟⠋⠈⠀⠀⠀⠑⠿⣿⣿⣿⣶⡀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢷⡿⡯⠃⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀"

// Braille logo only (extracted from full banner, no block text)
const bannerLogo = "" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⣶⣤⡀⠀⣤⣤⣾⣿⣦⣠⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣶⣶⣿⢿⣿⣿⣿⣿⣿⣻⣿⣟⣿⣿⣷⣾⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⠀⢰⣿⣄⣼⣿⣆⠀⣀⣴⣾⣿⣻⣟⣷⣯⢿⡾⣯⣷⣿⣾⣯⣷⢿⡾⣿⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠀⣀⣸⣿⣿⣽⣯⣿⣻⣿⣟⣿⢾⣽⣟⣿⣻⣟⣿⣻⣯⡿⣾⣽⣟⣿⣽⣟⡿⣿⢿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⢠⣾⣿⣷⣽⣷⢿⣷⢟⣮⣿⣻⡿⣿⣻⣿⣽⣻⢾⣯⣿⣻⣛⠿⣾⣽⢷⡿⣾⣻⣟⣯⣿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\n" +
	"⠀⠀⠀⠉⠙⢹⣷⢿⣯⡿⣿⢿⣟⣷⣿⣿⣿⣟⣯⣿⣻⢷⣿⡧⣿⢟⢮⣻⣟⣿⣽⣯⢿⣽⣿⠇\n" +
	"⠀⠀⠀⠀⣼⣿⣻⣿⣾⣿⣟⣿⡾⣿⢾⣽⣟⣿⣿⡾⣯⣿⣾⣷⣽⣳⣧⣿⢿⣷⢿⡾⣿⣞⡿⣿⡀\n" +
	"⠀⠀⠀⠀⠻⣟⢽⣿⣾⢯⣿⣾⣟⡿⣯⣿⣿⣽⢿⣟⣿⣽⣟⣾⣿⣯⢿⡾⣿⣽⣻⣟⣷⡿⣽⣿⣯\n" +
	"⠀⠀⠀⠀⠀⠀⠸⣿⣟⣿⣻⣾⣽⣿⣿⣻⣯⣿⣿⡿⣿⣾⣿⣿⣾⣻⣟⣿⣷⢿⣷⣯⣿⣽⢿⣾⠗\n" +
	"⠀⠀⠀⠀⠀⠀⢰⣿⣟⣿⢿⣿⡽⣷⣿⣿⡿⣿⡿⣿⣿⣿⣽⢷⣻⣽⣿⣿⣻⣿⣷⣿⣷⢿⠿⠉\n" +
	"⠀⠀⠀⠀⠀⠀⢸⣿⣯⣟⣿⣯⣿⣟⣿⣾⣿⣿⢿⣿⡿⣺⣷⣿⢿⡫⠷⠝⠽⠝⣟⢷⣿⣷⣄\n" +
	"⠀⠀⠀⠀⠀⠀⢘⣿⣾⢯⣿⣷⢿⡿⣿⣟⣿⣽⣿⣿⣝⣿⢿⠕⠁⠀⠀⢀⠄⠀⠀⠉⢻⢿⣿⣆\n" +
	"⠀⠀⠀⠀⠀⠀⠀⣿⣿⢯⣿⣿⣻⣿⣿⣿⣻⣾⣿⣮⣿⡿⡇⠀⠀⠀⢃⣈⣤⠄⡨⠀⠈⢻⣿⡿⡄\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠸⣿⣟⣷⢿⣿⣿⣯⣿⣽⣿⣿⢮⣿⣯⠇⠀⢀⡉⢴⡽⣙⠀⠄⠀⠀⣸⣿⣟⡇\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠹⣿⣯⡿⣿⣾⣿⡿⣾⣷⣿⣯⢿⣿⣣⠀⠀⠀⠯⠋⡁⠐⠀⠀⢠⣟⣿⢯⠂\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⡿⣿⣳⣿⣻⣿⣷⡿⣿⣿⣝⣿⣿⣷⣄⡀⠀⠀⠀⠈⣀⣴⣿⣿⣻⠃\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⣻⣷⣿⣽⢿⣿⣿⣟⣿⣮⣟⣽⣿⣿⣷⣾⣾⣿⡿⣿⢯⣿⣾⣦⡀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠑⠿⡿⣿⣾⣽⣟⣿⢿⣿⣷⣷⣽⣽⣫⣟⣽⣽⡾⠓⠻⣿⣿⣿⣦⡄\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠑⠋⠟⢟⢿⢿⡷⣿⢿⢿⡻⢟⠟⠋⠈⠀⠀⠀⠑⠿⣿⣿⣿⣶⡀\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢷⡿⡯⠃\n" +
	"⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁"

const bannerFullWidth = 165
const bannerLogoWidth = 60

// RenderBanner returns a responsive banner based on terminal width.
func RenderBanner() string {
	cols := termWidth()

	// Wide terminal — full banner with logo + text art
	if cols >= bannerFullWidth {
		return BannerStyle.Render(bannerFull)
	}

	// Medium terminal — braille logo + text name below
	if cols >= bannerLogoWidth {
		return BannerStyle.Render(bannerLogo) + "\n" +
			BannerBold.Render("       D E C E P T I C O N")
	}

	// Narrow terminal — text only
	return BannerBold.Render("D E C E P T I C O N")
}

func termWidth() int {
	w, _, err := term.GetSize(int(os.Stdout.Fd()))
	if err != nil || w <= 0 {
		return 80
	}
	return w
}

func Success(msg string) {
	fmt.Println(Green.Render("✓ " + msg))
}

func Warning(msg string) {
	fmt.Println(Yellow.Render("⚠ " + msg))
}

func Error(msg string) {
	fmt.Println(Red.Render("✗ " + msg))
}

func Info(msg string) {
	fmt.Println(Cyan.Render("● " + msg))
}

func DimText(msg string) {
	fmt.Println(Dim.Render(msg))
}

// DecepticonTheme returns a custom huh theme with Decepticon red branding.
// Based on ThemeCharm for polished visuals, recolored to red.
func DecepticonTheme(isDark bool) *huh.Styles {
	t := huh.ThemeCharm(isDark)

	red := lipgloss.Color("#FF3333")
	brightRed := lipgloss.Color("#FF0000")
	dimRed := lipgloss.Color("#CC4444")
	gray := lipgloss.Color("#888888")
	lightGray := lipgloss.Color("#AAAAAA")
	darkBg := lipgloss.Color("#1A1A1A")

	// Focused field — red left border
	t.Focused.Base = t.Focused.Base.
		BorderForeground(brightRed)
	t.Blurred.Base = t.Blurred.Base.
		BorderForeground(lipgloss.Color("#444444"))

	// Titles
	t.Focused.Title = t.Focused.Title.Foreground(red).Bold(true)
	t.Blurred.Title = t.Blurred.Title.Foreground(gray)

	// Descriptions
	t.Focused.Description = t.Focused.Description.Foreground(lightGray)
	t.Blurred.Description = t.Blurred.Description.Foreground(gray)

	// Select cursor and options
	t.Focused.SelectSelector = t.Focused.SelectSelector.Foreground(brightRed)
	t.Focused.SelectedOption = t.Focused.SelectedOption.Foreground(red)
	t.Focused.SelectedPrefix = t.Focused.SelectedPrefix.Foreground(red)

	// Confirm buttons
	t.Focused.FocusedButton = t.Focused.FocusedButton.
		Background(brightRed).Foreground(lipgloss.Color("#FFFFFF")).Bold(true)
	t.Focused.BlurredButton = t.Focused.BlurredButton.
		Background(darkBg).Foreground(gray)

	// Text input
	t.Focused.TextInput.Cursor = t.Focused.TextInput.Cursor.Foreground(brightRed)
	t.Focused.TextInput.Prompt = t.Focused.TextInput.Prompt.Foreground(dimRed)

	// Error styling
	t.Focused.ErrorIndicator = t.Focused.ErrorIndicator.Foreground(brightRed)
	t.Focused.ErrorMessage = t.Focused.ErrorMessage.Foreground(brightRed)

	// Note (intro/outro card)
	t.Focused.Card = t.Focused.Card.BorderForeground(brightRed)
	t.Focused.NoteTitle = t.Focused.NoteTitle.Foreground(brightRed).Bold(true)
	t.Blurred.Card = t.Blurred.Card.BorderForeground(lipgloss.Color("#444444"))
	t.Blurred.NoteTitle = t.Blurred.NoteTitle.Foreground(gray)

	// Navigation hints
	t.Focused.Next = t.Focused.Next.Foreground(dimRed)

	// Group headers
	t.Group.Title = lipgloss.NewStyle().Foreground(red).Bold(true).PaddingBottom(1)
	t.Group.Description = lipgloss.NewStyle().Foreground(gray)

	return t
}
