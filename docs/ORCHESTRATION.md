# BhajanForge — Orchestration (LangGraph)

Defines the state machine: shared state, nodes, edges, and the quality-gate loop.

## 1. Shared State (`state.py`)
`BhajanState` (Pydantic / TypedDict for LangGraph). Full field types in
`DATA_MODELS.md`. Summary:

```python
class BhajanState(TypedDict, total=False):
    run_id: str
    request: ProductionRequest          # intake
    rules: RulesConfig                  # loaded thresholds
    learning: dict                      # learning.yaml snapshot
    lyrics: LyricsDoc
    music: MusicResult
    voice: VoiceResult
    mix: MixResult
    quality: QualityReport
    publish: PublishResult
    # control
    gate_passed: bool
    next_stage_on_fail: str | None      # "composer" | "voice" | "mixing"
    loop_counts: dict                   # per-stage attempt counters
    total_loops: int
    halted: bool                        # hard-stop (ethics) flag
    halt_reason: str | None
    artifacts: dict                     # name -> path
    errors: list
```

## 2. Nodes
| Node id | Agent | Reads | Writes |
|---------|-------|-------|--------|
| `intake` | (orchestrator) | request | validates, inits run dir, rules, learning |
| `lyricist` | Lyricist | request, learning, RAG | lyrics |
| `composer` | Composer | request, lyrics, learning | music (stems) |
| `voice` | Voice | music, learning | voice (my_voice.wav) |
| `mixing` | Mixing | voice, music, learning | mix, master.wav |
| `judge` | Quality Judge | master, reference | quality, gate_passed, next_stage_on_fail |
| `packager` | Packager | master, lyrics, request | publish (local save) |
| `memory` | (orchestrator) | quality, settings | updates learning.yaml, manifest |

## 3. Edges (control flow)

```
START
  → intake
  → (halted? → END_FAIL)            # ethics hard stop
  → lyricist
  → composer
  → voice
  → mixing
  → judge
  → CONDITIONAL:
       if gate_passed:        → packager → memory → END_OK
       elif can_loop():       → route_to(next_stage_on_fail)   # composer|voice|mixing
       else (loops exhausted):→ memory(mark "needs_human") → END_HUMAN
```

### Conditional helpers
```python
def can_loop(state) -> bool:
    stage = state["next_stage_on_fail"]
    return (state["loop_counts"].get(stage,0) < rules.max_loop_attempts
            and state["total_loops"] < rules.max_total_loops)

def route_to(stage):  # returns the node id to jump back to
    return {"composer":"composer","voice":"voice","mixing":"mixing"}[stage]
```

### Loop semantics (rules §4)
- Before re-running a stage, increment `loop_counts[stage]` and `total_loops`.
- The judge's `QualityReport.fixes` are written into state so the re-run stage can
  apply them (e.g., new `index_ratio`, new reverb predelay, regenerate music).
- A re-run MUST differ from the last failed attempt for the same issue (R4.5);
  the stage consults `learning.yaml` to avoid known-bad settings.
- Re-running `composer` invalidates downstream (`voice`, `mixing`) — they re-run.
  Re-running `voice` invalidates `mixing`. The graph re-flows naturally to `judge`.

## 4. Hard Stops (ethics, rules §2)
Checked in `intake` and defensively in `voice`:
- third-party voice requested → `halted=True`, `halt_reason`, route to `END_FAIL`.
- non-devotional genre → same.

## 5. Resumability
- Use a LangGraph checkpointer (SQLite/file) keyed by `run_id`.
- `bhajanforge status --run-id` reads the checkpoint + `manifest.json` to report
  the current node and allow `--resume`.
- Nodes skip work whose output artifact already exists & is valid for the run
  (idempotency, NFR-3 / R8.1).

## 6. Draft vs Auto publish
- `packager` reads `PUBLISH_MODE` and `PUBLISH_TARGET`. Default
  `PUBLISH_TARGET=local`: it always saves the bundle to `OUTPUT_DIR/` and never
  uploads. `PUBLISH_MODE=draft` additionally gates on human review before
  packaging when desired.
- `bhajanforge publish --run-id` re-enters at `packager` (e.g., to (re)build a
  video or, only if explicitly `PUBLISH_TARGET=youtube`, perform an upload).

## 7. Pseudocode (graph wiring)
```python
g = StateGraph(BhajanState)
g.add_node("intake", intake_node)
g.add_node("lyricist", lyricist_node)
g.add_node("composer", composer_node)
g.add_node("voice", voice_node)
g.add_node("mixing", mixing_node)
g.add_node("judge", judge_node)
g.add_node("packager", packager_node)
g.add_node("memory", memory_node)

g.set_entry_point("intake")
g.add_conditional_edges("intake", lambda s: "END_FAIL" if s["halted"] else "lyricist",
                        {"END_FAIL": END, "lyricist": "lyricist"})
g.add_edge("lyricist", "composer")
g.add_edge("composer", "voice")
g.add_edge("voice", "mixing")
g.add_edge("mixing", "judge")
g.add_conditional_edges("judge", judge_router,
   {"packager":"packager","composer":"composer","voice":"voice",
    "mixing":"mixing","needs_human":"memory"})
g.add_edge("packager", "memory")
g.add_edge("memory", END)
app = g.compile(checkpointer=checkpointer)
```
`judge_router` returns `"packager"` on pass, the failing stage if `can_loop`,
else `"needs_human"`.
