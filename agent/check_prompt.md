# Task: verify a stated network intent against Batfish

You are a non-interactive Claude Code session with Bash access, working inside
the "Network Project" repo (your current working directory). Nobody is
watching this run live — do the whole task yourself and print a final,
readable verdict. Do not ask clarifying questions; make reasonable choices
and state any assumptions in your final answer instead.

## Project layout (for context)

- `configs/vars/*.yml` — human-edited per-device data (hostname, interfaces, ACLs, BGP)
- `configs/templates/router.conf.j2` — Jinja2 template that turns vars into a real Cisco config
- `render_configs.py` — renders `configs/vars/*.yml` -> `configs/rendered/*.cfg`
- `core/acl_parser.py` — local ACL syntax validation only (not used for this task)
- A Batfish server is already running in Docker, reachable at `localhost` on
  ports 9996/9997 (the Batfish coordinator API). Do not try to start or manage
  the container yourself — assume it is already up. If a pybatfish call fails
  to connect, say so plainly in your verdict rather than trying to fix Docker.

## What to actually do, in order

1. Run `python render_configs.py` (use the project's own `.venv`:
   `.venv/Scripts/python.exe render_configs.py` on Windows) so
   `configs/rendered/*.cfg` reflects the current state of `configs/vars/*.yml`.
2. Batfish requires a snapshot directory laid out as `<some_dir>/configs/*.cfg`
   (a `configs` subfolder, not loose files). Copy the contents of the
   project's `configs/rendered/` directory into a fresh temp directory under
   that layout — do not upload `configs/rendered/` directly, it will be
   rejected.
3. Using `pybatfish` (already installed in the project's `.venv`), open a
   session against `localhost`, use network name `"network-project"` and
   snapshot name `"current"` with `overwrite=True` so repeated runs don't
   pile up stale snapshots.
4. Read the intent given to you below. Decide which Batfish query (or queries)
   actually test it, write the Python/pybatfish code yourself, and run it.
   Some starting points (not an exhaustive list — use whatever `bf.q.*`
   query genuinely answers the stated intent):
   - A specific "does this traffic get through" question ("X should reach Y
     on port Z") -> `bf.q.testFilters(...)` or `bf.q.reachability(...)`
     with `HeaderConstraints` matching the intent.
   - A structural ACL question ("did I break some other rule", "is my new
     rule even reachable") -> `bf.q.filterLineReachability()`.
   - A BGP session question ("will this neighbor relationship come up") ->
     `bf.q.bgpSessionStatus()` / `bf.q.bgpSessionCompatibility()`.
   - "Did anything's reachability change at all" (no specific flow given) ->
     `bf.q.differentialReachability()` between a `reference_snapshot` (the
     config before your edit, if you can reconstruct it, e.g. via `git show`
     or `git stash` if the working tree has uncommitted changes) and the
     current snapshot.
   Pick the query type(s) that actually match what the intent is claiming,
   not just the first one in this list.
5. Run the query for real against the live Batfish server. Do not guess or
   fabricate what Batfish would say — actually execute the code and read the
   real result.

## How to report back

End with a short, plain-English verdict, not a raw dataframe dump. Structure it as:

- **Intent checked:** (restate it in one line)
- **Verdict:** HOLDS / DOES NOT HOLD / INCONCLUSIVE (say which, plainly, first)
- **Why:** 2-4 sentences explaining what Batfish actually found, referencing
  the real device/interface/ACL-line names involved, not generic language.
- **Evidence:** the specific Batfish query you ran and the key row(s) of its
  output that justify the verdict (short, not the entire dataframe).

If the intent is ambiguous or you had to make an assumption to test it
concretely (e.g. picking which device "the branch" means), say so explicitly
in the verdict rather than silently guessing and staying quiet about it.

## Intent to check

{{INTENT}}
