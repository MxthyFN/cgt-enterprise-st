# CIPHERHOUND — Architecture Notes

This document complements the high-level overview in the project `README.md`
with implementation detail, data models, and extension points.

## Design goals

1. **Local-only & safe** — no network I/O, no real credentials, no persisted
   secrets. Safety is a structural property, not a runtime check.
2. **Zero dependencies** — standard library only, so the tool is portable and
   auditable with nothing to install.
3. **Modular & testable** — each stage is an independent module with a narrow
   interface; `app.py` is the only orchestrator.
4. **Efficient at scale** — ~100k candidates generated and evaluated in well
   under a second, with bounded memory.

## Data models

| Type | Module | Purpose |
| --- | --- | --- |
| `SessionConfig` | `collector` | All fictional inputs + target volume. Dataclass; `to_dict()` for logging. |
| `GenerationStats` | `engine` | Live counters: `generated`, `unique`, `duplicates`, `by_category`. Mutated during streaming. |
| `SyntheticAccount` | `simulator` | `username`, `salt`, `password_hash`, `seed_category`, `complexity`. **No plaintext field exists.** |
| `SimulationResult` | `simulator` | Evaluated count, accounts cracked, `MatchRecord`s, per-category tallies, elapsed time. |
| `PatternReport` | `analysis` | Aggregate structural metrics + distributions. |

## Candidate stream contract

`PasswordEngine.generate()` yields `(candidate: str, category: str)` tuples.
`category` is always a member of `engine.CATEGORIES`. The stream is:

* **Lazy** — a generator; callers decide how much to materialize.
* **De-duplicated** — a `set` guarantees uniqueness; duplicates are counted but
  not yielded.
* **Bounded** — generation stops at `target_count` unique candidates.
* **Ordered by realism** — most-likely habits first (keyboard walks, repeats,
  dates) before the large combinatorial body, so early-terminating consumers
  still see high-value candidates.

## Live stats sharing

The dashboard needs generation counters *and* simulation counters updating in
one frame. Rather than buffer candidates twice, the engine mutates a single
`GenerationStats` instance as it streams. `app.py` materializes the candidate
list once (cheap for 100k strings), feeds it to the simulator, and the
simulator's `progress` callback re-renders the dashboard from both the shared
`GenerationStats` and the running `SimulationResult`.

## Extension points

* **New construction habits** — add a category to `engine.CATEGORIES` and emit
  it from `PasswordEngine._raw_stream`. Analysis and reporting pick it up
  automatically via the category distribution.
* **New analysis metrics** — add a field to `PatternReport`, populate it in
  `analyze_candidates`, and surface it in `report.export_txt/csv`.
* **New export formats** — add an `export_<fmt>()` to `report.py` and include
  it in `export_all()`.
* **Alternative hashing** — `simulator._hash` is the single choke point for the
  (deliberately fast) salted hash; swap it to model a different scheme.

## Safety invariants (enforced by tests)

* Synthetic accounts expose no `password` / `plaintext` attribute
  (`test_no_plaintext_persisted_in_accounts`).
* The history index contains only aggregate metrics — no match candidate
  strings (`test_record_has_no_real_credentials_field`).
* Strong random accounts resist the engine, proving the simulator is a genuine
  comparison and not a rubber stamp (`test_strong_accounts_resist`).
