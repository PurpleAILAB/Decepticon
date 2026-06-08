package opscontrol

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	internal "github.com/PurpleAILAB/Decepticon/clients/launcher/internal/opscontrol"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/spf13/cobra"
)

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Report opscontrol service + daemon health",
	Long: `Shows three pieces of state operators usually need together:

  1. Service manager — systemd-user / launchd / none (= fallback)
  2. Service install + active status, when a manager is available
  3. Daemon /v1/health envelope, when the socket is reachable`,
	RunE: runStatus,
}

func runStatus(_ *cobra.Command, _ []string) error {
	mgr := internal.DetectServiceManager()
	ui.Info("Service manager: " + mgr.Name())

	if mgr.Available() {
		installed, err := mgr.Installed()
		if err != nil {
			return err
		}
		active, err := mgr.Active()
		if err != nil {
			return err
		}
		ui.Info(fmt.Sprintf("  unit=%s  installed=%v  active=%v", internal.ServiceUnitName(), installed, active))
	}

	body, err := probeHealth(internal.HostSocketPath())
	if err != nil {
		ui.Warning("Daemon socket: " + err.Error())
		return nil
	}
	ui.Success("Daemon /v1/health:")
	pretty, _ := json.MarshalIndent(body, "  ", "  ")
	fmt.Println("  " + string(pretty))
	return nil
}

// probeHealth performs a one-shot GET /v1/health over the Unix socket.
// Returns the decoded body or a diagnostic error suitable for the
// user-facing CLI ("daemon not reachable: socket missing", etc.).
func probeHealth(socketPath string) (map[string]any, error) {
	tr := &http.Transport{
		DialContext: func(_ context.Context, _, _ string) (net.Conn, error) {
			return net.DialTimeout("unix", socketPath, 2*time.Second)
		},
	}
	client := &http.Client{Transport: tr, Timeout: 5 * time.Second}
	resp, err := client.Get("http://opscontrol/v1/health")
	if err != nil {
		return nil, errors.New("not reachable (" + strings.TrimSpace(err.Error()) + ")")
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, errors.New("unexpected status " + strconv.Itoa(resp.StatusCode))
	}
	var out map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}

func init() {
	Cmd.AddCommand(statusCmd)
}
