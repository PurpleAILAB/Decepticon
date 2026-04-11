"""Tests for the one-liner recipe indexer."""

from __future__ import annotations

from pathlib import Path

from decepticon.tools.references.oneliners import load_recipes, search

_README = """# The Book of Secret Knowledge

## Networking

### tcpdump filters

Capture only TLS handshakes:

```
tcpdump -i eth0 -nn 'tcp port 443 and tcp[((tcp[12:1] & 0xf0) >> 2):1] = 0x16'
```

### ssh tunneling

Local port forward to an internal server:

```
ssh -L 8080:internal:80 user@jumphost
```

## Crypto

### openssl one-liners

Show peer certificate chain:

```
openssl s_client -showcerts -connect example.com:443 </dev/null
```
"""


def _build_cache(root: Path) -> Path:
    repo = root / "book-of-secret-knowledge"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text(_README, encoding="utf-8")
    return repo


class TestLoadRecipes:
    def test_absent_cache(self, tmp_path: Path) -> None:
        assert load_recipes(root=tmp_path) == []

    def test_parses_three_recipes(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        recipes = load_recipes(root=tmp_path)
        assert len(recipes) == 3
        topics = {r.topic for r in recipes}
        assert "tcpdump filters" in topics
        assert "ssh tunneling" in topics
        assert "openssl one-liners" in topics

    def test_heading_chain_preserved(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        recipes = load_recipes(root=tmp_path)
        ssh = next(r for r in recipes if r.topic == "ssh tunneling")
        assert ssh.headings[0] == "The Book of Secret Knowledge"
        assert ssh.headings[1] == "Networking"

    def test_command_body_captured(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        recipes = load_recipes(root=tmp_path)
        ssh = next(r for r in recipes if r.topic == "ssh tunneling")
        assert "ssh -L 8080" in ssh.command


class TestSearch:
    def test_empty_query(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        assert search("", root=tmp_path) == []

    def test_simple_match(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = search("tcpdump", root=tmp_path)
        assert len(hits) >= 1
        assert hits[0].topic == "tcpdump filters"

    def test_multi_term_ranking(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        hits = search("ssh tunnel", root=tmp_path)
        assert any(h.topic == "ssh tunneling" for h in hits)

    def test_unmatched_returns_empty(self, tmp_path: Path) -> None:
        _build_cache(tmp_path)
        assert search("kubernetes mesh", root=tmp_path) == []
