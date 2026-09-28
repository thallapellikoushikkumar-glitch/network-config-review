"""
Hand-written parser and simulator for Cisco-style extended ACLs.

Pure Python: regex + dataclasses + the stdlib `ipaddress` module. No
Batfish, no LLM. This is the piece that gets diffed and explained by the
agent layer, but the parsing and matching logic itself has nothing to do
with AI — it's the same kind of text-processing/rule-engine work as any
scripting-heavy infra role.

Supports a useful (not complete) subset of real Cisco extended ACL syntax:

    permit tcp 10.1.1.0 0.0.0.255 any eq 443
    deny   udp host 10.1.1.5 10.2.2.0 0.0.0.255 range 1000 2000
    permit ip any any
    remark this is a comment, ignored

Anything it can't parse raises ACLParseError with the offending line and
number, rather than silently guessing — a parser that fails loud is more
trustworthy than one that fails quiet.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field


class ACLParseError(ValueError):
    def __init__(self, line_no: int, line: str, reason: str):
        super().__init__(f"line {line_no}: {reason!r} in {line!r}")
        self.line_no = line_no
        self.line = line
        self.reason = reason


@dataclass(frozen=True)
class Endpoint:
    """A source or destination match: 'any', a single host, or a network
    expressed with a Cisco wildcard mask."""

    kind: str  # "any" | "host" | "network"
    network: ipaddress.IPv4Network | None = None

    def matches(self, ip: str) -> bool:
        if self.kind == "any":
            return True
        addr = ipaddress.ip_address(ip)
        assert self.network is not None
        return addr in self.network

    def __str__(self) -> str:
        if self.kind == "any":
            return "any"
        assert self.network is not None
        if self.kind == "host":
            return f"host {self.network.network_address}"
        return f"{self.network.network_address} {wildcard_mask(self.network)}"


@dataclass(frozen=True)
class PortMatch:
    op: str  # "eq" | "range" | "gt" | "lt" | None
    low: int | None = None
    high: int | None = None

    def matches(self, port: int) -> bool:
        if self.op is None:
            return True
        if self.op == "eq":
            return port == self.low
        if self.op == "gt":
            return port > self.low
        if self.op == "lt":
            return port < self.low
        if self.op == "range":
            return self.low <= port <= self.high
        raise ValueError(f"unknown port op {self.op!r}")


@dataclass(frozen=True)
class ACLRule:
    line_no: int
    action: str  # "permit" | "deny"
    protocol: str  # "tcp" | "udp" | "ip" | ...
    source: Endpoint
    destination: Endpoint
    dst_port: PortMatch = field(default_factory=lambda: PortMatch(op=None))
    raw: str = ""

    def matches(self, protocol: str, src_ip: str, dst_ip: str, dst_port: int | None) -> bool:
        if self.protocol != "ip" and protocol != self.protocol:
            return False
        if not self.source.matches(src_ip):
            return False
        if not self.destination.matches(dst_ip):
            return False
        if self.dst_port.op is not None:
            if dst_port is None:
                return False
            if not self.dst_port.matches(dst_port):
                return False
        return True


def wildcard_to_prefixlen(wildcard: str) -> int:
    """Convert a Cisco wildcard mask (e.g. '0.0.0.255') to a prefix length (24)."""
    inverted = ipaddress.IPv4Address(
        int(ipaddress.IPv4Address(wildcard)) ^ 0xFFFFFFFF
    )
    return ipaddress.IPv4Network(f"0.0.0.0/{inverted}").prefixlen


def wildcard_mask(network: ipaddress.IPv4Network) -> str:
    """Inverse of wildcard_to_prefixlen — render a network's wildcard mask."""
    netmask_int = int(network.netmask)
    wildcard_int = netmask_int ^ 0xFFFFFFFF
    return str(ipaddress.IPv4Address(wildcard_int))


_TOKEN_RE = re.compile(r"\S+")

_PORT_OPS = {"eq", "gt", "lt", "range"}


def _consume_endpoint(tokens: list[str], pos: int, line_no: int, raw: str) -> tuple[Endpoint, int]:
    if tokens[pos] == "any":
        return Endpoint(kind="any"), pos + 1
    if tokens[pos] == "host":
        if pos + 1 >= len(tokens):
            raise ACLParseError(line_no, raw, "'host' with no address")
        addr = tokens[pos + 1]
        net = ipaddress.ip_network(f"{addr}/32", strict=True)
        return Endpoint(kind="host", network=net), pos + 2
    # network + wildcard mask
    if pos + 1 >= len(tokens):
        raise ACLParseError(line_no, raw, "expected '<network> <wildcard-mask>'")
    addr, wildcard = tokens[pos], tokens[pos + 1]
    try:
        prefixlen = wildcard_to_prefixlen(wildcard)
        net = ipaddress.ip_network(f"{addr}/{prefixlen}", strict=False)
    except (ValueError, ipaddress.AddressValueError) as exc:
        raise ACLParseError(line_no, raw, f"bad network/wildcard: {exc}") from exc
    return Endpoint(kind="network", network=net), pos + 2


def _consume_port_match(tokens: list[str], pos: int, line_no: int, raw: str) -> tuple[PortMatch, int]:
    if pos >= len(tokens) or tokens[pos] not in _PORT_OPS:
        return PortMatch(op=None), pos
    op = tokens[pos]
    if op == "range":
        if pos + 2 >= len(tokens):
            raise ACLParseError(line_no, raw, "'range' needs two port numbers")
        low, high = int(tokens[pos + 1]), int(tokens[pos + 2])
        return PortMatch(op="range", low=low, high=high), pos + 3
    if pos + 1 >= len(tokens):
        raise ACLParseError(line_no, raw, f"'{op}' needs a port number")
    return PortMatch(op=op, low=int(tokens[pos + 1])), pos + 2


def parse_line(line_no: int, raw_line: str) -> ACLRule | None:
    """Parse a single ACL line. Returns None for blank lines, remarks, and
    the 'ip access-list extended NAME' header line."""
    line = raw_line.strip()
    if not line or line.startswith("!"):
        return None
    if line.startswith("remark"):
        return None
    if line.startswith("ip access-list"):
        return None

    tokens = _TOKEN_RE.findall(line)
    if not tokens:
        return None

    if tokens[0] not in ("permit", "deny"):
        raise ACLParseError(line_no, raw_line, f"expected 'permit' or 'deny', got {tokens[0]!r}")
    action = tokens[0]

    if len(tokens) < 2:
        raise ACLParseError(line_no, raw_line, "missing protocol")
    protocol = tokens[1]

    pos = 2
    source, pos = _consume_endpoint(tokens, pos, line_no, raw_line)
    destination, pos = _consume_endpoint(tokens, pos, line_no, raw_line)
    dst_port, pos = _consume_port_match(tokens, pos, line_no, raw_line)

    return ACLRule(
        line_no=line_no,
        action=action,
        protocol=protocol,
        source=source,
        destination=destination,
        dst_port=dst_port,
        raw=raw_line.rstrip("\n"),
    )


def parse_acl(text: str) -> list[ACLRule]:
    """Parse a full ACL (as it would appear in a running-config) into an
    ordered list of rules. Order matters: ACLs are first-match-wins."""
    rules: list[ACLRule] = []
    for i, raw_line in enumerate(text.splitlines(), start=1):
        rule = parse_line(i, raw_line)
        if rule is not None:
            rules.append(rule)
    return rules


def evaluate(
    rules: list[ACLRule],
    protocol: str,
    src_ip: str,
    dst_ip: str,
    dst_port: int | None = None,
) -> tuple[str, ACLRule | None]:
    """Simulate the ACL against a single packet description.

    Returns (action, matching_rule). If nothing matches, returns the Cisco
    implicit-deny behavior: ("deny", None).
    """
    for rule in rules:
        if rule.matches(protocol, src_ip, dst_ip, dst_port):
            return rule.action, rule
    return "deny", None
