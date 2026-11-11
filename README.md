# CIPHERHOUND

```
   ____ ___ ____  _   _ _____ ____  _   _  ___  _   _ _   _ ____
  / ___|_ _|  _ \| | | | ____|  _ \| | | |/ _ \| | | | \ | |  _ \
 | |    | || |_) | |_| |  _| | |_) | |_| | | | | | | |  \| | | | |
 | |___ | ||  __/|  _  | |___|  _ <|  _  | |_| | |_| | |\  | |_| |
  \____|___|_|   |_| |_|_____|_| \_\_| |_|\___/ \___/|_| \_|____/
```

**CIPHERHOUND** is an internal, terminal-inspired **password-security research
platform** built for **CGT Enterprises**. It helps the security team study
password vulnerabilities, common password-construction habits, and defensive
countermeasures — entirely offline, using **synthetic accounts and synthetic
passwords**.

> **Authorized, private research use only.** CIPHERHOUND is **100% local and
> offline**. It never contacts any external website or real authentication
> system, and it never collects or stores real credentials or personal data.

---

## Table of contents

1. [Safety & scope](#safety--scope)
2. [Features](#features)
3. [Installation](#installation)
4. [Quick start](#quick-start)
5. [Command-line options](#command-line-options)
6. [Architecture](#architecture)
7. [Research module reference](#research-module-reference)
8. [Research logs & exports](#research-logs--exports)
9. [Testing](#testing)
10. [Responsible use](#responsible-use)

---

## Safety & scope

CIPHERHOUND is designed so that it **cannot** be pointed at systems you don't
control:

* **Loopback-only networking** — the only outbound connections the tool makes
  are to a **loopback lab server** (`127.0.0.1` / `::1`) that *you* run. Any
  domain or remote/public/LAN address is refused in code (see
  [Live lab target](#live-lab-target-loopback-only)). There is no HTTP client
  and no way to reach an external site.
* **Synthetic data only** — inputs are fictional (favorite colors, fake
  birthdays, invented names, etc.). The interactive prompts explicitly steer
  the operator away from real credentials.
* **No plaintext secrets stored** — synthetic account passwords live only
  transiently in memory and are kept as **salted hashes**. Logs store
  aggregate metrics and clearly-labeled *synthetic* candidate strings, never
  real passwords or tokens.
* **Local simulation** — "authentication" is a local salted-hash comparison
  against an in-memory synthetic account set.

---

## Features

* Dark terminal aesthetic with an **animated ASCII startup sequence** (core,
  security, generation, testing, and logging modules initialize in turn).
* **Interactive research-session setup** — all questions optional/skippable.
* **Generation engine** capable of **~100,000 categorized candidates per
  session** in a fraction of a second.
* **Local authentication simulator** with configurable synthetic accounts.
* **Pattern analysis**: complexity scoring, predictable-substitution and
  repeated-sequence detection, pattern diversity, and category distribution.
* **Live terminal dashboard**: generation counter, progress bar, candidates
  evaluated, match counter, pattern distribution, and session timer.
* **Automatic research logging** with **JSON, TXT, and CSV** exports plus a
  session **history index**.
* **Zero third-party dependencies** — Python standard library only.

---

## Installation

Requires **Python 3.9+**. No packages to install. Runs on **macOS, Linux, and
Windows**.

```bash
git clone <this-repo>
cd cgt-enterprise-st
python3 --version        # confirm 3.9+
```

That's it — CIPHERHOUND runs directly from the source tree.

### Running on macOS

macOS includes `python3` once the Xcode Command Line Tools are present (run
`xcode-select --install` once if `python3 --version` is missing). The default
**Terminal.app** and **iTerm2** both render the ANSI colors, animated startup,
and live dashboard correctly.

```bash
cd cgt-enterprise-st
./run.sh --demo              # convenience launcher (chmod already set)
# ...equivalently:
python3 -m cipherhound --demo
```

If colors look wrong in an unusual terminal, add `--no-color` (or set
`NO_COLOR=1`); for a static, scroll-friendly view use `--no-animation`.

### Running on Windows

Use **Windows Terminal** or PowerShell (both support ANSI). Run
`python -m cipherhound --demo`. In the legacy `cmd.exe` console, pass
`--no-animation` if the live redraw looks jumpy.

---

## Quick start

Run an **interactive** research session (prompts for synthetic inputs, then
shows the live dashboard and writes logs):

```bash
python3 -m cipherhound
```

Run a **non-interactive demo** (fully synthetic data, great for a first look or
for CI):

```bash
python3 -m cipherhound --demo
```

Generate the full 100,000-candidate session against 20 synthetic accounts:

```bash
python3 -m cipherhound --demo --count 100000 --accounts 20
```

Review past sessions:

```bash
python3 -m cipherhound --history
```

---

## Command-line options

| Option | Description |
| --- | --- |
| `--demo` | Non-interactive run using synthetic demo data. |
| `--count N` | Target number of candidates to generate (default `100000`). |
| `--accounts N` | Number of synthetic accounts to build (default `8`). |
| `--target LABEL` | Label for the synthetic research target (demo mode). |
| `--log-dir DIR` | Directory for logs/exports (default `./logs`). |
| `--seed N` | Deterministic RNG seed for reproducible simulations. |
| `--lab-target IP` | Loopback IP of a local lab auth server to test against (`127.0.0.1`/`::1` only). |
| `--lab-port PORT` | Port of the local lab auth server (default `9099`). |
| `--lab-confirm` | Acknowledge you own/are authorized to test the loopback target (required with `--lab-target`). |
| `--no-color` | Disable ANSI colors. |
| `--no-animation` | Disable animations / live redraws. |
| `--no-startup` | Skip the animated startup sequence. |
| `--history` | Print recent session history and exit. |
| `--version` | Print version and exit. |

Environment variables: `NO_COLOR` / `CIPHERHOUND_NOCOLOR` disable color;
`CIPHERHOUND_LOG_DIR` overrides the default log directory.

---

## Live lab target (loopback-only)

In addition to the in-memory simulation, CIPHERHOUND can run candidates against
a **local lab authentication server over a real TCP socket** — the full "enter
an IP, connect, and test the login" workflow.

> **Safety boundary (enforced in code, not just docs):** the target must be a
> **loopback IP** (`127.0.0.0/8` or `::1`). Domains and remote/public/LAN
> addresses are **refused** — by `netsim.validate_loopback_target`, by the
> `NetworkTargetSimulator` constructor, and by the lab server's own bind check.
> This keeps live testing confined to a sandbox you run on your own machine.
> CIPHERHOUND will not test systems it does not control.

**1. Start the bundled lab server** (one terminal):

```bash
python3 -m cipherhound.labserver --port 9099 --accounts 8 --seed 1
```

It binds to `127.0.0.1` only, creates synthetic accounts (salted-hash stored,
no plaintext), and prints the exact command to point a session at it.

**2. Run a session against it** (another terminal):

```bash
python3 -m cipherhound --demo --lab-target 127.0.0.1 --lab-port 9099 --lab-confirm
```

Interactively, the setup questionnaire ends with a **Live Lab Target** step
that asks whether to connect, takes a loopback IP and port, and requires you to
type `I AM AUTHORIZED` before any live run. The CLI equivalent of that
confirmation is `--lab-confirm`.

Results from the live run are reported alongside the offline simulation and are
included in the JSON/TXT research logs under `network_target`.

---

## Architecture

CIPHERHOUND follows a clean, modular pipeline. Each stage is an independent,
testable module; `app.py` wires them together.

```
          ┌─────────────┐
 operator │ collector   │  interactive / demo input  (SessionConfig)
   input  └──────┬──────┘
                 ▼
          ┌─────────────┐
          │  engine     │  synthesize ~100k categorized candidates (lazy)
          └──────┬──────┘
                 ▼
     ┌───────────┴───────────┐
     ▼                       ▼
┌─────────────┐        ┌─────────────┐
│ simulator   │        │ analysis    │  complexity, habits, diversity
│ (synthetic  │        └──────┬──────┘
│  accounts)  │               │
└──────┬──────┘               │
       │   ┌──────────────────┘
       ▼   ▼
   ┌─────────────┐     drives    ┌─────────────┐
   │   app       │ ────────────▶ │ dashboard   │  live terminal UI
   └──────┬──────┘               └─────────────┘
          ▼
   ┌─────────────┐     ┌─────────────┐
   │  report     │────▶│  storage    │  JSON/TXT/CSV + history index
   └─────────────┘     └─────────────┘
```

Data flows one way. The only shared mutable state is `GenerationStats`, which
the engine updates as it streams candidates so the dashboard can render live
counters without buffering the whole candidate set twice.

---

## Research module reference

| Module | Responsibility |
| --- | --- |
| `cipherhound/branding.py` | ANSI palette, ASCII art, typewriter effects, and the multi-stage startup sequence. |
| `cipherhound/collector.py` | `SessionConfig` model; interactive questionnaire (all optional); synthetic `demo_config()`. |
| `cipherhound/engine.py` | `PasswordEngine` — lazily synthesizes categorized candidates from fictional seeds, de-duplicates, and tracks per-category stats. |
| `cipherhound/analysis.py` | Complexity scoring, leet/repeat/digit-run detection, pattern diversity (normalized entropy), and recommendation generation. |
| `cipherhound/simulator.py` | `AuthSimulator` — builds synthetic salted-hash accounts and tests candidates locally; attributes matches to habits. |
| `cipherhound/netsim.py` | Loopback-only live-target client (`NetworkTargetSimulator`) + `validate_loopback_target` enforcement. |
| `cipherhound/labserver.py` | Bundled local lab auth server (loopback-bind only) for the live-target workflow. |
| `cipherhound/dashboard.py` | In-place live terminal dashboard (counters, progress bar, distribution, timer) with a non-TTY fallback. |
| `cipherhound/report.py` | Assembles the credential-free research record and writes JSON/TXT/CSV. |
| `cipherhound/storage.py` | Local, restrictive-permission history index; never stores secrets. |
| `cipherhound/app.py` | Orchestrates a full session end to end. |
| `cipherhound/__main__.py` | CLI entry point / argument parsing. |

### How the generation engine works

The engine models how people actually build passwords, layering habits:

1. **Base tokens** from seed categories (colors, teams, names, words, custom)
   plus always-present **keyboard walks** (`qwerty`, `asdf`, …).
2. **Capitalization** variants (lower, Title, UPPER, aLtErNaTe).
3. **Leet substitutions** (`a→@`, `e→3`, `o→0`, `s→$`, …), applied as
   first-class stems so they also receive affixes.
4. **Affixes** — numeric suffixes, year suffixes, special characters, and the
   very common **number × special** cross-products, plus prefixes.
5. **Token pairing** with separators (`vaultcipher`, `vault.cipher`, …).
6. **Date patterns**, **repeated sequences**, and verbatim **custom patterns**.

Candidates are produced by a generator and de-duplicated with a set, stopping
as soon as the target count of unique candidates is reached — so 100k entries
generate in well under a second with bounded memory. Each candidate carries the
construction **category** responsible for it, which powers both the pattern
distribution chart and match attribution.

### How the simulator works

The simulator builds configurable synthetic accounts: ~75% use weak,
seed-derived passwords and ~25% use strong random passwords (which should
resist the engine). Every password is stored only as a **salted SHA-256 hash**;
plaintext is discarded immediately. Candidates are tested locally, each account
is matched at most once, and the winning candidate's category is recorded so
the report can say *which habit* broke each account.

> A fast salted hash is used so the simulator can evaluate ~100k candidates
> against many accounts quickly. Production systems should use a **slow,
> memory-hard KDF** (bcrypt/scrypt/Argon2) precisely to make this kind of
> high-volume guessing infeasible — which is itself a core finding CIPHERHOUND
> is built to demonstrate.

---

## Research logs & exports

After every session, CIPHERHOUND writes to `./logs/` (configurable):

* `CH-YYYYMMDD-HHMMSS.json` — full machine-readable record.
* `CH-YYYYMMDD-HHMMSS.txt` — human-readable research log.
* `CH-YYYYMMDD-HHMMSS.csv` — tabular export (metrics + matches + recommendations).
* `research_history.jsonl` — append-only index of session summaries (metrics
  only; **no** candidate strings or secrets).

Each record includes the session date/time, application name, research target
label, input categories, counts generated/evaluated, simulation results,
pattern analysis, and security recommendations.

---

## Testing

The suite uses the standard-library `unittest` (so no extra install needed):

```bash
python3 -m unittest discover -s tests -v
# or, if you prefer pytest:
pytest -q
```

It verifies 100k generation volume, uniqueness/de-duplication, categorization,
the local simulator (including that strong accounts resist and no plaintext is
retained), analysis metrics, and JSON/TXT/CSV export integrity.

---

## Responsible use

CIPHERHOUND exists to **strengthen** defenses. Use it only for authorized,
private research with synthetic data. Do not use it, or any passwords it
generates, against real accounts or systems you are not explicitly authorized
to test. Findings should drive defensive improvements: stronger password
policies, breached-password blocklists, MFA, and rate limiting / lockout.

_© CGT Enterprises — internal research tooling._
