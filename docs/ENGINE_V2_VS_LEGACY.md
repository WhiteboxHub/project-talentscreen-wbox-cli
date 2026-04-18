# Engine v2 (LangGraph) vs legacy engine

## Multi-page forms and URL changes

The **legacy** [`ApplicationEngine`](../jobcli/core/engine.py) runs an LLM loop that compares successive accessibility snapshots. It treats **URL changes** and **form field set/value changes** as signals that another automation pass is needed (for example after clicking **Next** or **Continue** on a multi-step application).

The **v2** [`EnhancedApplicationEngine`](../jobcli/core/engine_v2.py) uses [`ApplicationStateMachine`](../jobcli/core/state_machine.py). As of the current design, **phase 2 (`_phase_2_llm`) implements the same idea**: after executing LLM actions, it waits, re-extracts the AX tree, and continues for up to **five** “waves” when the URL or form snapshot changes, or when uploads require a re-scan.

## Redirects and stored URLs

Both paths should persist the **post-redirect** URL when it differs from the job link:

- v2 stores it in the `jobs.resolved_url` column via [`JobRepository.update_resolved_url`](../jobcli/storage/repositories.py) and [`normalize_job_url`](../jobcli/core/url_normalize.py).
- New jobs are inserted with a **normalized** canonical `url` to reduce duplicate rows from tracking query parameters.

## LangGraph “nodes”

Phases (`phase_0_memory`, `phase_2_llm`, `phase_1_rules`, `phase_3_human`, `finalize`) are **LangGraph nodes**. This is an internal execution graph only; it is not related to OpenClaw hardware/device nodes.
