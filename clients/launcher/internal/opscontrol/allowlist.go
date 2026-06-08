package opscontrol

import (
	"fmt"
	"os"
	"regexp"
	"sort"
	"strings"
)

// DefaultAllowlist is the workload catalog from ADR-0006's catalog
// table. It lives in the binary, not in user-visible config, so OSS
// users do not gain `ops_start("malicious")` rights by editing .env.
// New OSS workloads are added by amending this slice and the
// docker-compose.yml profile entry (extension protocol §Catalog
// extension protocol).
var DefaultAllowlist = []string{
	"ad",
	"c2-sliver",
	"c2-havoc",
	"reversing",
	"phishing",
	"mobile",
	"wireless",
	"cloud",
	"iot",
	"ics",
	"forensics",
	"supply-chain",
}

// AllowlistExtraEnv lets tests / plugin authors append (never remove)
// names without rebuilding the binary. Removing or overriding the
// baked-in list is intentionally not possible — see ADR-0006 §1'.
const AllowlistExtraEnv = "DECEPTICON_OPS_ALLOWLIST_EXTRA"

// workloadName matches the names compose accepts as profile labels
// (lowercase, digits, dash). The 63-char cap mirrors DNS-label
// semantics so KubernetesBackend can reuse the validator without
// rework.
var workloadName = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,62}$`)

// Allowlist is the resolved permission set used by the daemon.
type Allowlist struct {
	members map[string]struct{}
}

// LoadAllowlist returns the default catalog merged with any extra
// names from DECEPTICON_OPS_ALLOWLIST_EXTRA. Invalid names in the env
// variable are reported as an error rather than silently dropped.
func LoadAllowlist() (*Allowlist, error) {
	members := make(map[string]struct{}, len(DefaultAllowlist))
	for _, name := range DefaultAllowlist {
		members[name] = struct{}{}
	}
	if extra := os.Getenv(AllowlistExtraEnv); extra != "" {
		for _, name := range strings.Split(extra, ",") {
			name = strings.TrimSpace(name)
			if name == "" {
				continue
			}
			if !workloadName.MatchString(name) {
				return nil, fmt.Errorf("%s: invalid workload name %q", AllowlistExtraEnv, name)
			}
			members[name] = struct{}{}
		}
	}
	return &Allowlist{members: members}, nil
}

// Permits reports whether name is a valid workload AND is in the
// resolved allowlist. Used by the server before any docker shell-out.
func (a *Allowlist) Permits(name string) bool {
	if !workloadName.MatchString(name) {
		return false
	}
	_, ok := a.members[name]
	return ok
}

// Members returns the resolved allowlist sorted for stable health /
// status responses.
func (a *Allowlist) Members() []string {
	out := make([]string, 0, len(a.members))
	for name := range a.members {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}
