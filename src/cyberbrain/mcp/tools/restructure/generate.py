"""Content generation phase for cb_restructure — LLM content creation."""

import json
import re
from pathlib import Path

from fastmcp.exceptions import ToolError

from cyberbrain.mcp.shared import _load_tool_prompt as _load_prompt
from cyberbrain.mcp.tools.restructure.decide import (
    _gate_generated_content,
    _is_gate_enabled,
)
from cyberbrain.mcp.tools.restructure.format import (
    _format_action_description,
    _format_cluster_block,
)


def _call_generate_cluster(
    decision: dict,
    cluster_notes: list[dict],
    prefs_section: str,
    vault: Path,
    config: dict,
) -> dict:
    """Phase 2 LLM call: generate content for a single cluster decision."""
    from cyberbrain.extractors.backends import (
        BackendError,
        call_model,
        get_model_for_tool,
    )

    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    generate_system = _load_prompt("restructure-generate-system.md")
    action_desc = _format_action_description(decision)
    source_block = _format_cluster_block([cluster_notes], vault)
    user_msg = (
        _load_prompt("restructure-generate-user.md")
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{action_description}", action_desc)
        .replace("{source_notes_block}", source_block)
    )
    try:
        raw = call_model(generate_system, user_msg, tool_config)
    except BackendError as e:
        raise ToolError(
            f"Backend error during generation for cluster {decision.get('cluster_index', '?')}: {e}"
        )
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise json.JSONDecodeError("expected object", raw, 0)
        return result
    except json.JSONDecodeError as e:
        raise ToolError(
            f"LLM returned invalid JSON in generation phase (cluster {decision.get('cluster_index', '?')}): "
            f"{e}\n\nRaw: {raw[:500]}"
        )


def _call_generate_split(
    decision: dict,
    split_note: dict,
    prefs_section: str,
    vault: Path,
    config: dict,
) -> dict:
    """Phase 2 LLM call: generate content for a single split decision."""
    from cyberbrain.extractors.backends import (
        BackendError,
        call_model,
        get_model_for_tool,
    )

    tool_config = {**config, "model": get_model_for_tool(config, "restructure")}
    generate_system = _load_prompt("restructure-generate-system.md")
    action_desc = _format_action_description(decision)
    source_block = _format_cluster_block([[split_note]], vault)
    user_msg = (
        _load_prompt("restructure-generate-user.md")
        .replace("{vault_prefs_section}", prefs_section)
        .replace("{action_description}", action_desc)
        .replace("{source_notes_block}", source_block)
    )
    try:
        raw = call_model(generate_system, user_msg, tool_config)
    except BackendError as e:
        raise ToolError(
            f"Backend error during generation for split note {decision.get('note_index', '?')}: {e}"
        )
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise json.JSONDecodeError("expected object", raw, 0)
        return result
    except json.JSONDecodeError as e:
        raise ToolError(
            f"LLM returned invalid JSON in generation phase (split note {decision.get('note_index', '?')}): "
            f"{e}\n\nRaw: {raw[:500]}"
        )


def _generate_all_parallel(
    decisions: list[dict],
    clusters: list[list[dict]],
    split_candidates: list[dict],
    prefs_section: str,
    vault: Path,
    config: dict,
) -> None:
    """Run all Phase 2 generation calls in parallel. Modifies decisions in-place.

    When the quality gate is enabled, generated content is validated. On FAIL,
    a single retry is attempted (with a stronger model if suggested). On
    UNCERTAIN, the gate verdict is attached to the decision for surfacing.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    gate_enabled = _is_gate_enabled(config)

    def _gen_one(decision: dict) -> None:
        action = decision.get("action", "")
        if "cluster_index" in decision and action in (
            "merge",
            "hub-spoke",
            "subfolder",
        ):
            cidx = decision.get("cluster_index", -1)
            if 0 <= cidx < len(clusters):
                content = _call_generate_cluster(
                    decision, clusters[cidx], prefs_section, vault, config
                )
                decision.update(content)
        elif "note_index" in decision and action in ("split", "split-subfolder"):
            nidx = decision.get("note_index", -1)
            if 0 <= nidx < len(split_candidates):
                content = _call_generate_split(
                    decision, split_candidates[nidx], prefs_section, vault, config
                )
                decision.update(content)

        # Quality gate on generated content
        if gate_enabled:
            gate_result = _gate_generated_content(decision, config)
            if gate_result and not gate_result["passed"]:
                # Retry once on FAIL with stronger model if suggested
                if gate_result["verdict"] == "fail" and gate_result.get(
                    "suggest_retry"
                ):
                    retry_config = dict(config)
                    if gate_result.get("suggested_model"):
                        retry_config["model"] = gate_result["suggested_model"]
                    # Re-generate
                    if "cluster_index" in decision and action in (
                        "merge",
                        "hub-spoke",
                        "subfolder",
                    ):
                        cidx = decision.get("cluster_index", -1)
                        if 0 <= cidx < len(clusters):
                            try:
                                content = _call_generate_cluster(
                                    decision,
                                    clusters[cidx],
                                    prefs_section,
                                    vault,
                                    retry_config,
                                )
                                decision.update(content)
                                # Re-check
                                gate_result = _gate_generated_content(decision, config)
                            except Exception:  # intentional: retry generation failure is non-fatal; decision proceeds with original content
                                pass
                    elif "note_index" in decision and action in (
                        "split",
                        "split-subfolder",
                    ):
                        nidx = decision.get("note_index", -1)
                        if 0 <= nidx < len(split_candidates):
                            try:
                                content = _call_generate_split(
                                    decision,
                                    split_candidates[nidx],
                                    prefs_section,
                                    vault,
                                    retry_config,
                                )
                                decision.update(content)
                                gate_result = _gate_generated_content(decision, config)
                            except Exception:  # intentional: retry split generation failure is non-fatal; decision proceeds with original
                                pass

                # Attach gate info to the decision for surfacing
                if gate_result and not gate_result["passed"]:
                    decision["_gate_gen_verdict"] = gate_result["verdict"]
                    decision["_gate_gen_confidence"] = gate_result["confidence"]
                    decision["_gate_gen_rationale"] = gate_result["rationale"]
                    decision["_gate_gen_issues"] = gate_result["issues"]

    actionable = [
        d
        for d in decisions
        if d.get("action")
        not in (
            "keep",
            "keep-separate",
            "move-cluster",
            "flag-misplaced",
            "flag-low-quality",
        )
    ]
    if not actionable:
        return
    with ThreadPoolExecutor(max_workers=min(len(actionable), 6)) as executor:
        futures = {executor.submit(_gen_one, d): d for d in actionable}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:  # intentional: individual generation future failure is non-fatal; other decisions continue
                pass
