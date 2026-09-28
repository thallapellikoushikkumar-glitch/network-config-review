"""
Subnet/IPAM engine: pure Python, standard library only.

No Batfish, no LLM, no third-party dependency beyond the stdlib `ipaddress`
module. Everything here is real logic (overlap detection, gap-finding,
CIDR summarization) that the agent layer in agent/ builds on top of.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass


Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_cidr(cidr: str) -> Network:
    """Parse a CIDR string into a network object. Raises ValueError on bad input."""
    return ipaddress.ip_network(cidr, strict=True)


def overlaps(a: str, b: str) -> bool:
    """True if two CIDR blocks share any address space."""
    net_a, net_b = parse_cidr(a), parse_cidr(b)
    if net_a.version != net_b.version:
        return False
    return net_a.overlaps(net_b)


def find_overlaps(subnets: list[str]) -> list[tuple[str, str]]:
    """Return every pair of subnets in the list that overlap each other.

    O(n^2) pairwise check — fine for the scale an IPAM audit actually needs
    (hundreds, not millions, of allocated blocks per site).
    """
    parsed = [(s, parse_cidr(s)) for s in subnets]
    found: list[tuple[str, str]] = []
    for i in range(len(parsed)):
        for j in range(i + 1, len(parsed)):
            s1, n1 = parsed[i]
            s2, n2 = parsed[j]
            if n1.version == n2.version and n1.overlaps(n2):
                found.append((s1, s2))
    return found


@dataclass
class AllocationResult:
    subnet: str | None
    reason: str


def find_next_available(
    supernet: str,
    prefix_len: int,
    already_allocated: list[str],
) -> AllocationResult:
    """Find the first available subnet of size `prefix_len` inside `supernet`
    that doesn't overlap anything in `already_allocated`.

    This is the actual algorithmic core: walk the candidate subnets of the
    supernet in order, skip any that collide with an existing allocation,
    return the first clean one. Mirrors what a real IPAM tool has to do
    before handing out the next /24 for a new branch.
    """
    super_net = parse_cidr(supernet)
    if prefix_len < super_net.prefixlen:
        return AllocationResult(
            None, f"requested /{prefix_len} is larger than supernet /{super_net.prefixlen}"
        )

    allocated_nets = [parse_cidr(s) for s in already_allocated]

    for candidate in super_net.subnets(new_prefix=prefix_len):
        if not any(candidate.overlaps(existing) for existing in allocated_nets):
            return AllocationResult(str(candidate), "ok")

    return AllocationResult(
        None, f"supernet {supernet} is fully allocated at /{prefix_len}"
    )


def summarize(cidrs: list[str]) -> list[str]:
    """Collapse a list of CIDR blocks into the minimal set of supernets that
    cover the same address space (route summarization / aggregation).
    """
    version_groups: dict[int, list] = {4: [], 6: []}
    for c in cidrs:
        net = parse_cidr(c)
        version_groups[net.version].append(net)

    summarized: list[str] = []
    for version, nets in version_groups.items():
        if not nets:
            continue
        collapsed = ipaddress.collapse_addresses(nets)
        summarized.extend(str(n) for n in collapsed)
    return summarized


def fits_within(inner: str, outer: str) -> bool:
    """True if `inner` CIDR is fully contained within `outer` CIDR."""
    inner_net, outer_net = parse_cidr(inner), parse_cidr(outer)
    return inner_net.version == outer_net.version and inner_net.subnet_of(outer_net)
