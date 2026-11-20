# Graph Report - murakha  (2026-11-20)

## Corpus Check
- 51 files · ~27,981 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: .toml 2)

## Summary
- 534 nodes · 904 edges · 24 communities (16 shown, 8 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 30 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `28850add`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- tests/server.rs
- src/secure.rs
- Class
- src/server.rs
- src/heal.rs
- src/discovery.rs
- heart_net.rs
- tests/life.rs
- CoordMessage
- src/order.rs
- Throttle
- src/heart.rs
- tests/heart.rs
- src/flash.rs
- tests/scout.rs
- server-ref.rs
- order.rs
- consent.rs
- murakha

## God Nodes (most connected - your core abstractions)
1. `CoordMessage` - 20 edges
2. `TaskQueue` - 17 edges
3. `TaskQueue` - 15 edges
4. `heal()` - 14 edges
5. `hex_decode()` - 14 edges
6. `Class` - 10 edges
7. `Server` - 10 edges
8. `AntMessage` - 10 edges
9. `handle_connection()` - 10 edges
10. `handle_connection()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `send_line()` --references--> `Channel`  [INFERRED]
  pending/server-ref.rs → src/secure.rs
- `snapshot_from()` --references--> `Snapshot`  [INFERRED]
  tests/cli_heal.rs → src/heal.rs
- `snap_of()` --references--> `Snapshot`  [INFERRED]
  tests/replicate_server.rs → src/heal.rs
- `snapshot_from()` --calls--> `hex_decode()`  [INFERRED]
  tests/cli_heal.rs → src/protocol.rs
- `handle_connection()` --calls--> `hex_decode()`  [INFERRED]
  pending/server-ref.rs → src/protocol.rs

## Import Cycles
- None detected.

## Communities (24 total, 8 thin omitted)

### Community 0 - "tests/server.rs"
Cohesion: 0.13
Nodes (9): Coordinator, handle_connection(), empty_queue_says_wait_and_garbage_is_ignored(), raw(), real_exit_code_is_stored(), task_of_a_vanished_ant_comes_back(), three_ants_do_three_tasks(), two_hundred_ants_at_once() (+1 more)

### Community 1 - "src/secure.rs"
Cohesion: 0.06
Nodes (14): ant_proof(), Channel, coord_proof(), eq_ct(), hmac_hex(), hmac_raw(), HmacSha256, session_key() (+6 more)

### Community 2 - "Class"
Cohesion: 0.12
Nodes (20): Class, Flaky, Stable, Weak, classify(), mean_session_s(), outages(), sessions() (+12 more)

### Community 3 - "src/server.rs"
Cohesion: 0.13
Nodes (9): handle_connection(), InstantPlaceholder, send_line(), Server, Task, TaskQueue, TaskQueueInner, TaskResult (+1 more)

### Community 4 - "src/heal.rs"
Cohesion: 0.14
Nodes (19): Choice, Follow, TakeOver, Wait, choose(), decode(), encode(), heal() (+11 more)

### Community 5 - "src/discovery.rs"
Cohesion: 0.08
Nodes (10): default_targets(), discover(), DISCOVERY_PORT, is_retryable(), make_reply(), make_request(), parse_reply(), spawn_responder() (+2 more)

### Community 6 - "heart_net.rs"
Cohesion: 0.06
Nodes (24): patrol(), pause_s(), tcp_probe(), MAX_OUTPUT_SIZE, run_command(), run_command_code(), test_run_command_success(), ant_process_takes_over_when_coordinator_process_dies() (+16 more)

### Community 7 - "tests/life.rs"
Cohesion: 0.15
Nodes (11): choose_rules(), free_addr(), p(), snapshot_roundtrip(), swarm_heals_after_coordinator_is_destroyed(), ants_heal_the_swarm_after_the_coordinator_is_destroyed(), doomed_coordinator(), free_addr() (+3 more)

### Community 8 - "CoordMessage"
Cohesion: 0.06
Nodes (30): generate_ant_id(), IO_TIMEOUT, MAX_BACKOFF, next_delay(), run_ant_loop(), run_session(), run_session_snap(), run_session_timeout() (+22 more)

### Community 9 - "src/order.rs"
Cohesion: 0.10
Nodes (9): ArchantKey, Obedience, Order, OrderError, BadSignature, Expired, Malformed, Replay (+1 more)

### Community 10 - "Throttle"
Cohesion: 0.19
Nodes (7): combine(), cpu_share(), ThermalGuard, Throttle, Careful, Pause, Run

### Community 11 - "src/heart.rs"
Cohesion: 0.07
Nodes (25): Assembler, EXT, list(), MAGIC, MAX_BYTES, NEVER, pack(), parse() (+17 more)

### Community 13 - "tests/heart.rs"
Cohesion: 0.12
Nodes (11): damaged_or_evil_bundles_write_nothing(), make_dante(), pack_list_unpack_roundtrip_without_secrets(), tmp(), checkpoints(), results_survive_and_are_delivered_once(), tmpdir(), broken_snapshot_is_detected_and_skipped() (+3 more)

### Community 15 - "src/flash.rs"
Cohesion: 0.10
Nodes (7): FlashError, NotFlash, WrongPassOrDamaged, KdfParams, MAGIC, open(), seal()

### Community 16 - "tests/scout.rs"
Cohesion: 0.36
Nodes (4): patrol_finds_late_answer_within_budget(), patrol_gives_up_when_budget_is_spent(), routes_order_and_dedup(), v()

### Community 18 - "server-ref.rs"
Cohesion: 0.12
Nodes (9): handle_connection(), InstantPlaceholder, send_line(), Server, Task, TaskQueue, TaskQueueInner, TaskResult (+1 more)

## Knowledge Gaps
- **26 isolated node(s):** `murakha`, `NotFlash`, `WrongPassOrDamaged`, `Careful`, `Pause` (+21 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 228 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Channel` connect `src/secure.rs` to `server-ref.rs`, `src/server.rs`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **What connects `murakha`, `NotFlash`, `WrongPassOrDamaged` to the rest of the system?**
  _26 weakly-connected nodes found - possible missing edges._
- **Should `tests/server.rs` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._
- **Why does `CoordMessage` connect `CoordMessage` to `server-ref.rs`, `src/server.rs`, `heart_net.rs`, `tests/life.rs`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Should `src/secure.rs` be split into smaller, more focused modules?**
  _Cohesion score 0.06477732793522267 - nodes in this community are weakly interconnected._
- **Why does `TaskQueue` connect `src/server.rs` to `src/heal.rs`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Should `Class` be split into smaller, more focused modules?**
  _Cohesion score 0.12433862433862433 - nodes in this community are weakly interconnected._