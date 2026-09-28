# Current intent

Write down what a config change in `configs/vars/*.yml` is supposed to do
before asking Claude to check it. Nothing is inferred or guessed from a git
diff — this file is the one place intent is declared, by the person making
the change.

Replace the example below with your own, then tell whichever Claude Code
session you have open in this folder to check it. Claude's job is to turn
this into a real pybatfish query, run it against the live Batfish
container, and report back whether it actually holds — not to decide what
the intent should be.

---

Example: BRANCH-03's LAN (10.20.3.0/24) should be able to reach DC-B-CORE's
LAN (10.2.2.0/24) through its direct WAN link to DC-B-CORE.
