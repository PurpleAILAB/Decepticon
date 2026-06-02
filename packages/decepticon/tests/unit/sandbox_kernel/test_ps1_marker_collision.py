"""Collision-proofing tests for the PS1 completion marker regex.

The marker is emitted by the in-sandbox shell as::

    [DCPTN:$?:$PWD]

and parsed back out of tmux ``capture-pane`` output. The CWD group must:

* refuse to swallow a literal ``]`` that appears later in tool output
  (otherwise findall miscounts and stall/completion detection breaks);
* refuse to span newlines (a real ``$PWD`` is always a single line);
* still match every legitimately-emitted marker, including normal paths,
  paths with spaces, and non-zero exit codes.

These tests pin the regex shape AND its behavior so future edits cannot
silently re-introduce the non-greedy ``.+?`` collision footgun.
"""

from __future__ import annotations

from decepticon.sandbox_kernel.tmux import PS1_PATTERN, _extract_output


class TestPS1PatternShape:
    def test_cwd_group_forbids_close_bracket_and_newline(self) -> None:
        # Intent lock-in: the CWD group must be a negated character class
        # that excludes ']' and newlines, not a non-greedy '.+?'. The
        # latter relies on backtracking and on '.' not matching newlines
        # by default — both fragile under capture-pane edge cases.
        assert PS1_PATTERN.pattern == r"\[DCPTN:(\d+):([^\]\n]+)\]"


class TestLegitimateMarkersStillMatch:
    def test_canonical_workspace_marker(self) -> None:
        m = PS1_PATTERN.search("[DCPTN:0:/workspace] ")
        assert m is not None
        assert m.group(1) == "0"
        assert m.group(2) == "/workspace"

    def test_nonzero_exit_code(self) -> None:
        m = PS1_PATTERN.search("[DCPTN:127:/tmp] ")
        assert m is not None
        assert m.group(1) == "127"
        assert m.group(2) == "/tmp"

    def test_path_with_spaces(self) -> None:
        m = PS1_PATTERN.search("[DCPTN:0:/home/user/dir with space] ")
        assert m is not None
        assert m.group(2) == "/home/user/dir with space"

    def test_path_with_dots_and_dashes(self) -> None:
        m = PS1_PATTERN.search("[DCPTN:2:/var/log/.cache/foo-bar.d] ")
        assert m is not None
        assert m.group(2) == "/var/log/.cache/foo-bar.d"


class TestBracketInPayloadDoesNotCorruptCount:
    def test_two_real_markers_with_bracket_payload_between(self) -> None:
        # Real session: agent ran `echo "fake ]"`. There must be exactly
        # the two real markers (baseline + completion), never three.
        screen = '[DCPTN:0:/workspace] echo "fake ]"\nfake ]\n[DCPTN:0:/workspace] '
        markers = PS1_PATTERN.findall(screen)
        assert len(markers) == 2
        for exit_code, cwd in markers:
            assert exit_code == "0"
            assert cwd == "/workspace"

    def test_extract_output_cwd_is_not_swallowed_past_bracket(self) -> None:
        # If the CWD capture were to swallow past ']', the reported cwd
        # would bleed into subsequent payload (and the marker count would
        # collapse). Verify _extract_output() returns the precise cwd.
        screen = "[DCPTN:0:/workspace] ls -la\nfile with ] in name\n[DCPTN:0:/workspace] "
        output, exit_code, cwd = _extract_output(screen, "ls -la")
        assert exit_code == 0
        assert cwd == "/workspace"
        assert "file with ] in name" in output


class TestNewlineBoundedCwd:
    def test_cwd_cannot_cross_newline(self) -> None:
        # A malformed half-marker followed by a real marker on the next
        # line must not collapse into a single (corrupt) match — the
        # first '[DCPTN:' is junk, only the second is a real marker.
        screen = "[DCPTN:0:/partial-no-close\n[DCPTN:0:/workspace] "
        markers = PS1_PATTERN.findall(screen)
        assert len(markers) == 1
        assert markers[0] == ("0", "/workspace")
