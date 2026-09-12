# Architecture decision 0001: deterministic core first

Status: accepted for foundation.

Use a small Python standard-library execution kernel before network services or
LLM agents. Task IDs and dependencies define a directed acyclic graph. Validate
the entire graph before running any task, so malformed input cannot partially run.
Among ready tasks, choose lexicographic ID order for reproducibility.

A task succeeds when its trusted callable returns, fails when it raises Exception,
and is blocked when any dependency did not succeed. Independent tasks continue.
KeyboardInterrupt and SystemExit propagate to the caller. A task with a failing
assertion is a failure, not a successful return of a false-looking value.
Dependencies order execution; they do not currently pass data between callables.

Results remain in memory. A subsequent version will add schema-versioned evidence,
timestamps, requirement IDs, artifact hashes, and persistence before retries.
The callable interface allows future engineering adapters and bounded AI workers.
Untrusted code requires a separate isolated execution design.

Tradeoff: sequential execution is simple to reason about and test, but slow for
large workloads. Determinism applies to scheduling, not arbitrary task behavior.
