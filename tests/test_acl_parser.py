import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.acl_parser import parse_acl, evaluate, ACLParseError, wildcard_to_prefixlen


SAMPLE_ACL = """
ip access-list extended BRANCH-IN
 remark allow HTTPS from branch subnet to DC
 permit tcp 10.20.0.0 0.0.0.255 host 10.1.1.10 eq 443
 permit udp 10.20.0.0 0.0.0.255 any range 1000 2000
 deny   ip 10.20.0.0 0.0.0.255 any
 permit ip any any
"""


def test_parse_acl_skips_header_and_remarks():
    rules = parse_acl(SAMPLE_ACL)
    assert len(rules) == 4  # 3 explicit rules + implicit deny... wait, implicit deny is not a line
    assert rules[0].action == "permit"
    assert rules[0].protocol == "tcp"


def test_wildcard_to_prefixlen_common_masks():
    assert wildcard_to_prefixlen("0.0.0.255") == 24
    assert wildcard_to_prefixlen("0.0.0.0") == 32
    assert wildcard_to_prefixlen("0.0.1.255") == 23


def test_permit_matches_specific_host_and_port():
    rules = parse_acl(SAMPLE_ACL)
    action, rule = evaluate(rules, "tcp", "10.20.0.5", "10.1.1.10", 443)
    assert action == "permit"
    assert rule.line_no == rules[0].line_no


def test_same_source_wrong_port_falls_through_to_next_rule():
    # Not 443, not in the UDP range, so first two rules skip; third rule
    # is a blanket "deny ip 10.20.0.0/24 any" that should catch it.
    rules = parse_acl(SAMPLE_ACL)
    action, rule = evaluate(rules, "tcp", "10.20.0.5", "10.1.1.10", 80)
    assert action == "deny"
    assert rule.protocol == "ip"


def test_udp_range_match():
    rules = parse_acl(SAMPLE_ACL)
    action, rule = evaluate(rules, "udp", "10.20.0.7", "8.8.8.8", 1500)
    assert action == "permit"


def test_traffic_outside_branch_subnet_hits_final_permit_any():
    rules = parse_acl(SAMPLE_ACL)
    action, rule = evaluate(rules, "tcp", "192.168.1.1", "1.2.3.4", 22)
    assert action == "permit"
    assert rule.source.kind == "any"


def test_no_match_at_all_is_implicit_deny():
    rules = parse_acl("ip access-list extended EMPTY\n")
    action, rule = evaluate(rules, "tcp", "1.1.1.1", "2.2.2.2", 22)
    assert action == "deny"
    assert rule is None


def test_bad_action_keyword_raises_parse_error():
    with pytest.raises(ACLParseError):
        parse_acl("allow tcp any any eq 80\n")


def test_host_keyword_matches_exact_address_only():
    rules = parse_acl("permit ip host 10.1.1.5 any\n")
    action, _ = evaluate(rules, "ip", "10.1.1.5", "9.9.9.9", None)
    assert action == "permit"
    action2, rule2 = evaluate(rules, "ip", "10.1.1.6", "9.9.9.9", None)
    assert action2 == "deny"
    assert rule2 is None
