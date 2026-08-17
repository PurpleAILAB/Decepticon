from decepticon_core.types.roe import MachineEnforcement, evaluate_target


def test_bug_bounty_wildcard_allows_nested_subdomains() -> None:
    rules = MachineEnforcement.from_dict(
        {"in_scope": [{"target": "*.anduril.dev", "type": "domain-glob"}]}
    )

    assert evaluate_target("sentry.anduril.dev", rules).allow
    assert evaluate_target("internal.sentry.anduril.dev", rules).allow


def test_bug_bounty_wildcard_does_not_expand_to_apex_or_lookalike() -> None:
    rules = MachineEnforcement.from_dict(
        {"in_scope": [{"target": "*.anduril.dev", "type": "domain-glob"}]}
    )

    assert not evaluate_target("anduril.dev", rules).allow
    assert not evaluate_target("internal.sentry.anduril.dev.evil.test", rules).allow
    assert not evaluate_target("evil-anduril.dev", rules).allow


def test_explicit_exclusion_overrides_recursive_wildcard() -> None:
    rules = MachineEnforcement.from_dict(
        {
            "in_scope": [
                {"target": "*.anduril.dev", "type": "domain-glob"},
            ],
            "out_of_scope": [
                {"target": "internal.sentry.anduril.dev", "type": "host"},
            ],
        }
    )

    decision = evaluate_target("internal.sentry.anduril.dev", rules)

    assert not decision.allow
    assert decision.reason_code == "OUT_OF_SCOPE"
