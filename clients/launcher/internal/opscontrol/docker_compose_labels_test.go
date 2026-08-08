package opscontrol

import (
	"encoding/json"
	"os"
	"testing"
)

func TestLabeledComposeOverrideScopesEveryService(t *testing.T) {
	path, err := labeledComposeOverride([]string{"bhce", "bhce-neo4j"}, "ad", "eng-1", "run-1")
	if err != nil {
		t.Fatalf("labeledComposeOverride: %v", err)
	}
	defer os.Remove(path)

	contents, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read override: %v", err)
	}
	var document map[string]map[string]map[string]map[string]string
	if err := json.Unmarshal(contents, &document); err != nil {
		t.Fatalf("decode override: %v", err)
	}
	for _, service := range []string{"bhce", "bhce-neo4j"} {
		labels := document["services"][service]["labels"]
		if labels["decepticon.engagement"] != "eng-1" || labels["decepticon.run"] != "run-1" || labels["decepticon.workload"] != "ad" {
			t.Fatalf("%s labels = %#v", service, labels)
		}
	}
}
