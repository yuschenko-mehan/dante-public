# Graph Report - murakha  (2026-11-20)

## Corpus Check
- 38 files · ~19,800 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 325 nodes · 622 edges · 18 communities (15 shown, 3 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 20 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `373c390c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- duration
- ant.rs
- Class
- src/server.rs
- src/heal.rs
- src/discovery.rs
- heart_net.rs
- tests/life.rs
- CoordMessage
- tests/survive.rs
- replicate_ant.rs
- src/survive.rs
- tests/server.rs
- cli_heal.rs
- murakha
- src/mailbag.rs

## God Nodes (most connected - your core abstractions)
1. `CoordMessage` - 18 edges
2. `TaskQueue` - 15 edges
3. `heal()` - 14 edges
4. `hex_decode()` - 12 edges
5. `handle_connection()` - 11 edges
6. `Class` - 10 edges
7. `Server` - 10 edges
8. `AntMessage` - 9 edges
9. `hex_encode()` - 9 edges
10. `Healed` - 8 edges

## Surprising Connections (you probably didn't know these)
- `server_hands_out_heart_chunks_in_order()` --calls--> `hex_decode()`  [INFERRED]
  tests/heart_net.rs → src/protocol.rs
- `snapshot_from()` --references--> `Snapshot`  [INFERRED]
  tests/cli_heal.rs → src/heal.rs
- `snap_of()` --references--> `Snapshot`  [INFERRED]
  tests/replicate_server.rs → src/heal.rs
- `snapshot_from()` --calls--> `hex_decode()`  [INFERRED]
  tests/cli_heal.rs → src/protocol.rs
- `snap_of()` --calls--> `hex_decode()`  [INFERRED]
  tests/replicate_server.rs → src/protocol.rs

## Import Cycles
- None detected.

## Communities (18 total, 3 thin omitted)

### Community 0 - "duration"
Cohesion: 0.11
Nodes (4): Coordinator, handle_connection(), main(), print_usage_and_exit()

### Community 1 - "ant.rs"
Cohesion: 0.08
Nodes (23): generate_ant_id(), IO_TIMEOUT, MAX_BACKOFF, next_delay(), run_ant_loop(), run_session(), run_session_snap(), run_session_timeout() (+15 more)

### Community 2 - "Class"
Cohesion: 0.12
Nodes (20): Class, Flaky, Stable, Weak, classify(), mean_session_s(), outages(), sessions() (+12 more)

### Community 3 - "src/server.rs"
Cohesion: 0.14
Nodes (8): handle_connection(), InstantPlaceholder, Server, Task, TaskQueue, TaskQueueInner, TaskResult, wants_snapshots()

### Community 4 - "src/heal.rs"
Cohesion: 0.15
Nodes (18): Choice, Follow, TakeOver, Wait, choose(), decode(), encode(), heal() (+10 more)

### Community 5 - "src/discovery.rs"
Cohesion: 0.08
Nodes (11): default_targets(), discover(), DISCOVERY_PORT, is_retryable(), make_reply(), make_request(), parse_reply(), spawn_responder() (+3 more)

### Community 6 - "heart_net.rs"
Cohesion: 0.14
Nodes (9): damaged_or_evil_bundles_write_nothing(), make_dante(), Client, coordinator_process_gives_heart_and_ant_restores_dante(), fake_dante(), server_hands_out_heart_chunks_in_order(), tmp(), pack_list_unpack_roundtrip_without_secrets() (+1 more)

### Community 7 - "tests/life.rs"
Cohesion: 0.14
Nodes (12): HealCfg, choose_rules(), free_addr(), p(), snapshot_roundtrip(), swarm_heals_after_coordinator_is_destroyed(), ants_heal_the_swarm_after_the_coordinator_is_destroyed(), doomed_coordinator() (+4 more)

### Community 8 - "CoordMessage"
Cohesion: 0.17
Nodes (8): CoordMessage, Bye, Snap, Task, Wait, Client, new_ants_get_the_swarm_snapshot(), snap_of()

### Community 9 - "tests/survive.rs"
Cohesion: 0.18
Nodes (7): checkpoints(), results_survive_and_are_delivered_once(), tmpdir(), broken_snapshot_is_detected_and_skipped(), keep_zero_counts_as_one(), keeps_only_newest_and_restores(), tmpdir()

### Community 10 - "replicate_ant.rs"
Cohesion: 0.19
Nodes (9): ant_saves_snapshot_then_works(), bad_snapshot_is_ignored(), fake(), old_session_says_old_version(), tmpdir(), patrol_finds_late_answer_within_budget(), patrol_gives_up_when_budget_is_spent(), routes_order_and_dedup() (+1 more)

### Community 11 - "src/survive.rs"
Cohesion: 0.17
Nodes (5): checksum(), latest(), load(), SNAPSHOT_COUNTER, store()

### Community 13 - "tests/server.rs"
Cohesion: 0.38
Nodes (7): empty_queue_says_wait_and_garbage_is_ignored(), raw(), real_exit_code_is_stored(), task_of_a_vanished_ant_comes_back(), three_ants_do_three_tasks(), two_hundred_ants_at_once(), wait_until()

### Community 14 - "cli_heal.rs"
Cohesion: 0.13
Nodes (6): MAX_OUTPUT_SIZE, run_command(), test_run_command_success(), ant_process_takes_over_when_coordinator_process_dies(), free_port(), snapshot_from()

### Community 16 - "src/mailbag.rs"
Cohesion: 0.39
Nodes (7): done(), drop_checkpoint(), get(), load_checkpoint(), put(), safe_id(), save_checkpoint()

## Knowledge Gaps
- **16 isolated node(s):** `Ask`, `Beat`, `Hello`, `Result`, `murakha` (+11 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 101 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CoordMessage` connect `CoordMessage` to `ant.rs`, `src/server.rs`, `heart_net.rs`, `tests/life.rs`, `replicate_ant.rs`, `cli_heal.rs`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `hex_decode()` (e.g. with `run_session_snap()` and `handle_connection()`) actually correct?**
  _`hex_decode()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Ask`, `Beat`, `Hello` to the rest of the system?**
  _16 weakly-connected nodes found - possible missing edges._
- **Should `duration` be split into smaller, more focused modules?**
  _Cohesion score 0.1076923076923077 - nodes in this community are weakly interconnected._
- **Why does `TaskQueue` connect `src/server.rs` to `src/heal.rs`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **Should `ant.rs` be split into smaller, more focused modules?**
  _Cohesion score 0.08108108108108109 - nodes in this community are weakly interconnected._
- **Why does `AntMessage` connect `ant.rs` to `src/server.rs`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._