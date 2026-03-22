"""Decision phase for cb_restructure — LLM action selection and quality gate."""

import json
import re

from fastmcp.exceptions import ToolError

from cyberbrain.mcp.shared import _load_tool_prompt as _load_prompt
from cyberbrain.mcp.tools.restructure.format import (
    _build_cluster_summary_block,
    _build_split_summary_block,
    _build_standalone_notes_block,
)
from cyberbrain.mcp.tools.restructure.utils import _repair_json


def _call_decisions(
    clusters: list[list[dict]],
    splits: list[dict],
    prefs_section: str,
    folder_context: str,
    config: dict,
    standalone: list[dict] | None = None,
    vault_structure: str = "",
    folder_note_count: int = 0,
) -> list[dict]:
    """Phase 1 LLM call: decide actions for all clusters and splits (no content generation)."""
    from cyberbrain.extractors.backends import (
        BackendError,
        call_model,
        get_model_for_tool,
    )

    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    _standalone = standalone or []
    decide_system = _load_prompt("restructure-decide-system.md")
    clusters_block = _build_cluster_summary_block(clusters)
    splits_block = _build_split_summary_block(splits)
    standalone_block = _build_standalone_notes_block(_standalone)
    user_msg = (
        _load_prompt("restructure-decide-user.md")
        .replace("{cluster_count}", str(len(clusters)))
        .replace("{split_count}", str(len(splits)))
        .replace("{standalone_count}", str(len(_standalone)))
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{vault_structure}", vault_structure)
        .replace("{folder_context}", folder_context)
        .replace("{standalone_notes_block}", standalone_block)
        .replace("{clusters_summary_block}", clusters_block)
        .replace("{split_candidates_summary_block}", splits_block)
        .replace("{folder_note_count}", str(folder_note_count))
    )
    try:
        raw = call_model(decide_system, user_msg, tool_config)
    except BackendError as e:
        raise ToolError(f"Backend error during decision phase: {e}")
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        return _repair_json(raw)
    except json.JSONDecodeError as e:
        raise ToolError(
            f"LLM returned invalid JSON in decision phase: {e}\n\nRaw: {raw[:500]}"
        )


def _is_gate_enabled(config: dict) -> bool:
    """Check if quality gate is enabled (default: True)."""
    return config.get("quality_gate_enabled", True)


def _gate_decisions(
    decisions: list[dict],
    clusters: list[list[dict]],
    split_candidates: list[dict],
    config: dict,
) -> list[dict]:
    """Run quality gate on proposed decisions. Returns gate verdicts for each non-trivial decision.

    Each verdict dict has: decision_index, verdict, confidence, rationale, issues.
    Decisions that are simple (keep, keep-separate) skip the gate.
    """
    if not _is_gate_enabled(config):
        return []

    try:
        from cyberbrain.extractors.quality_gate import quality_gate
    except ImportError:
        return []

    gate_results = []

    for i, decision in enumerate(decisions):
        action = decision.get("action", "")
        # Simple/no-op actions don't need gating
        if action in ("keep", "keep-separate", "flag-misplaced", "flag-low-quality"):
            continue

        # Build context describing what the decision proposes
        if "cluster_index" in decision:
            cidx = decision.get("cluster_index", -1)
            if cidx < 0 or cidx >= len(clusters):
                continue
            cluster = clusters[cidx]
            titles = [n["title"] for n in cluster]
            summaries = [n.get("summary", "") for n in cluster]
            input_ctx = (
                f"Cluster of {len(cluster)} notes proposed for action '{action}':\n"
                + "\n".join(f"- {t}: {s}" for t, s in zip(titles, summaries))
            )
        elif "note_index" in decision:
            nidx = decision.get("note_index", -1)
            if nidx < 0 or nidx >= len(split_candidates):
                continue
            note = split_candidates[nidx]
            input_ctx = (
                f"Large note proposed for action '{action}':\n"
                f"- {note['title']}: {note.get('summary', '')}\n"
                f"- Size: {len(note.get('content', ''))} chars"
            )
        else:
            continue

        output_text = json.dumps(decision, indent=2, default=str)
        if "cluster_index" in decision:
            op_action = decision.get("action", "merge")
            operation = (
                "restructure_hub"
                if op_action in ("hub-spoke", "subfolder")
                else "restructure_merge"
            )
        else:
            operation = "restructure_split"
        verdict = quality_gate(operation, input_ctx, output_text, config)

        gate_result = {
            "decision_index": i,
            "action": action,
            "verdict": verdict.verdict.value,
            "confidence": verdict.confidence,
            "rationale": verdict.rationale,
            "issues": verdict.issues,
            "passed": verdict.passed,
        }

        # If below threshold and not passed, mark the decision with gate info
        if not verdict.passed:
            decision["_gate_verdict"] = verdict.verdict.value
            decision["_gate_confidence"] = verdict.confidence
            decision["_gate_rationale"] = verdict.rationale
            decision["_gate_issues"] = verdict.issues
            if verdict.verdict.value == "uncertain":
                decision["_gate_needs_confirmation"] = True
            elif verdict.verdict.value == "fail":
                # Downgrade failed decisions to keep-separate/keep
                original_action = decision["action"]
                if "cluster_index" in decision:
                    decision["action"] = "keep-separate"
                else:
                    decision["action"] = "keep"
                decision["_gate_original_action"] = original_action
                decision["rationale"] = (
                    f"Quality gate failed (confidence: {verdict.confidence:.2f}): "
                    f"{verdict.rationale}. Original action was '{original_action}'."
                )

        gate_results.append(gate_result)

    return gate_results


def _gate_generated_content(decision: dict, config: dict) -> dict | None:
    """Run quality gate on generated content. Returns GateVerdict-like dict or None if skipped.

    On FAIL, returns the verdict with suggest_retry=True.
    """
    if not _is_gate_enabled(config):
        return None

    try:
        from cyberbrain.extractors.quality_gate import quality_gate
    except ImportError:
        return None

    action = decision.get("action", "")

    # Determine the content to evaluate and the operation type
    if action in ("merge",):
        content = decision.get("merged_content", "")
        if not content:
            return None
        operation = "restructure_merge"
        input_ctx = f"Merge action for cluster {decision.get('cluster_index', '?')}"
    elif action in ("hub-spoke", "subfolder"):
        content = decision.get("hub_content", "")
        if not content:
            return None
        operation = "restructure_hub"
        input_ctx = f"{action} action for cluster {decision.get('cluster_index', '?')}"
    elif action in ("split", "split-subfolder"):
        notes = decision.get("output_notes", [])
        if not notes:
            return None
        content = "\n---\n".join(n.get("content", "") for n in notes)
        operation = "restructure_split"
        input_ctx = f"Split action for note {decision.get('note_index', '?')}"
    else:
        return None

    verdict = quality_gate(operation, input_ctx, content, config)
    return {
        "verdict": verdict.verdict.value,
        "confidence": verdict.confidence,
        "rationale": verdict.rationale,
        "issues": verdict.issues,
        "passed": verdict.passed,
        "suggest_retry": verdict.suggest_retry,
        "suggested_model": verdict.suggested_model,
    }
