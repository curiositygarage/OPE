# Security policy

## Reporting a vulnerability

Use **GitHub private vulnerability reporting** on this repository — *Security → Report a
vulnerability* in the repository's Security tab. That channel is enabled as of 2026-11-01 and it is
the only entry point: do not open a public issue or pull request for a security problem.

There is deliberately **no email address in this file**. A personal address in a public repository
gets harvested, and a reporting channel nobody monitors is worse than none. If the private report
form is ever unavailable to you, open an issue whose entire content is *"Security report — private
reporting form unavailable"* and name nothing else: not the file, not the route, not how to
reproduce it.

## What OPE's safety actually rests on

OPE is an unauthenticated file writer. There is no login, no token, no session, so the controls are
all at the edges: the server binds `127.0.0.1` and writes only `.html`/`.htm` files inside the
directory it was started in. Everything below is a claim that a specific line of `serve.py` or
`ope.js` enforces — if one of them is false, that is the bug.

## What counts as a vulnerability here

- a write that lands **outside the served directory**: `..` traversal, a symlink planted in the
  directory, a sibling directory whose name merely prefixes the base path;
- a write to a **non-HTML** file, or a `.bak` chain deeper than one per save;
- a **cross-site write that lands** — a way past the `Content-Type: application/json` requirement
  or the `Sec-Fetch-Site: cross-site` rejection, including a form-encoded or `text/plain` request
  that reaches the write;
- a **stale-tab save accepted** on a page that carries an `<!-- ope-ver: N -->` marker, or a marker
  that disappears or gets downgraded when a save is applied;
- a read that leaves the machine: page contents, `changes.md` or `.bak` bytes sent anywhere other
  than the local `OPE_NOTIFY_DIR` drop;
- a credential, secret or PII in a shipped file or a published git object.

## Out of scope — documented, not vulnerabilities

- **No authentication.** Setting `OPE_HOST` beyond `127.0.0.1` exposes an unauthenticated editor to
  anyone who can reach the port. That is a documented operator choice, not a defect. The same goes
  for everything else in the served directory: `<page>.bak` and `changes.md` are readable by anyone
  who can reach the port, which is why the README says not to serve a directory holding private
  files.
- **Resource bounds.** 32 MB body ceiling and a 30-second socket timeout are the stated limits.
  A body under the ceiling is accepted by design.
- **`ope_ver` in a POST body is ignored.** The version lives only in the marker comment. Sending the
  field is accepted and does nothing; that is the documented contract, not a bypass.

## The claims are testable

`scripts/test_traversal.py`, `scripts/test_hardening.py` and `scripts/test_stale_marker.py` are
stdlib-only and run against a throwaway copy of `serve.py`; CI runs all three. A behavioural claim
in `SKILL.md` that no script covers is a documentation bug — report it as one.

OPE ships no dependencies, makes no outbound network calls, and has no telemetry. The only network
traffic it produces is the browser POSTing a save back to the page's own origin.
