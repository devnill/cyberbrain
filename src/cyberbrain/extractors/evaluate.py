"""
evaluate.py — Evaluation framework for comparing curation tool outputs.

Runs a curation operation (restructure, enrichment, extraction) with multiple
configurations and presents results side-by-side with optional LLM-as-judge scoring.

Usage as CLI:
    python3 extractors/evaluate.py --operation enrich --notes path1.md path2.md \
        --variants '{"model":"claude-haiku-4-5"}' '{"model":"claude-sonnet-4-5"}'

This is a standalone dev tool. It is not called by any MCP tool or production code path.
"""

import argparse
import difflib
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cyberbrain.extractors.backends import call_model
from cyberbrain.extractors.config import load_prompt


@dataclass
class Variant:
    """A configuration variant to evaluate."""
    name: str
    overrides: dict = field(default_factory=dict)
    # overrides can include: model, prompt_path, params (dict of tool-specific params)


@dataclass
class VariantOutput:
    """Output from running a single variant."""
    variant: Variant
    raw_output: str = ""
    duration_ms: int = 0
    error: Optional[str] = None


@dataclass
class Score:
    """Quality score from LLM-as-judge or manual evaluation."""
    variant_index: int = 0
    accuracy: Optional[int] = None
    structure: Optional[int] = None
    discoverability: Optional[int] = None
    signal_to_noise: Optional[int] = None
    grouping_quality: Optional[int] = None
    overall: Optional[int] = None
    notes: str = ""


@dataclass
class EvalResult:
    """Complete evaluation result."""
    operation: str
    timestamp: str = ""
    input_notes: list = field(default_factory=list)
    outputs: list = field(default_factory=list)  # list of VariantOutput (serialized)
    diffs: list = field(default_factory=list)  # pairwise diffs between variants
    scores: list = field(default_factory=list)  # list of Score (serialized)
    metadata: dict = field(default_factory=dict)


def _build_config_with_overrides(base_config: dict, overrides: dict) -> dict:
    """Merge variant overrides into a copy of the base config."""
    merged = dict(base_config)
    for key, value in overrides.items():
        if key == "params":
            # params are tool-specific, stored separately
            continue
        merged[key] = value
    return merged


def _compute_diff(text_a: str, text_b: str, label_a: str, label_b: str) -> str:
    """Compute unified diff between two text outputs."""
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    diff = difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b)
    return "".join(diff)


def _run_operation(operation: str, notes_content: list, config: dict,
                   params: dict) -> str:
    """Run a curation operation and return raw output.

    This is the integration point — each operation type calls the appropriate
    curation function in dry-run / non-destructive mode.
    """
    if operation == "enrich":
        return _run_enrich(notes_content, config, params)
    elif operation == "extract":
        return _run_extract(notes_content, config, params)
    elif operation == "restructure":
        return _run_restructure(notes_content, config, params)
    else:
        raise ValueError(f"Unknown operation: {operation}. Supported: enrich, extract, restructure")


def _run_enrich(notes_content: list, config: dict, params: dict) -> str:
    """Run enrichment on notes content and return raw LLM output."""
    system_template = load_prompt("enrich-system.md")
    user_template = load_prompt("enrich-user.md")

    # Build notes block
    notes_block_parts = []
    for idx, (path, content) in enumerate(notes_content):
        notes_block_parts.append(f"--- Note {idx}: {path} ---\n{content[:3000]}")
    notes_block = "\n\n".join(notes_block_parts)

    vault_type_context = params.get("vault_type_context", "Use default types: decision, insight, problem, reference.")
    system_prompt = system_template.replace("{vault_type_context}", vault_type_context)
    user_message = (
        user_template
        .replace("{count}", str(len(notes_content)))
        .replace("{notes_block}", notes_block)
    )

    return call_model(system_prompt, user_message, config)


def _run_extract(notes_content: list, config: dict, params: dict) -> str:
    """Run extraction on transcript content and return raw LLM output."""
    system_prompt = load_prompt("extract-beats-system.md")
    user_template = load_prompt("extract-beats-user.md")

    # For extraction, notes_content is [(path, transcript_text)]
    transcript = "\n\n".join(content for _, content in notes_content)
    user_message = user_template.replace("{transcript}", transcript[:150000])

    return call_model(system_prompt, user_message, config)


def _run_restructure(notes_content: list, config: dict, params: dict) -> str:
    """Run restructure decision on notes and return raw LLM output."""
    system_prompt = load_prompt("restructure-decide-system.md")
    user_template = load_prompt("restructure-decide-user.md")

    notes_block_parts = []
    for idx, (path, content) in enumerate(notes_content):
        notes_block_parts.append(f"--- Note {idx}: {path} ---\n{content[:3000]}")
    notes_block = "\n\n".join(notes_block_parts)

    user_message = user_template.replace("{notes_block}", notes_block)
    return call_model(system_prompt, user_message, config)


def _score_with_llm(operation: str, notes_content: list,
                    outputs: list, config: dict) -> list:
    """Use LLM-as-judge to score variant outputs."""
    system_prompt = load_prompt("evaluate-system.md")

    # Build user message with inputs and all variant outputs
    parts = ["## Input Notes\n"]
    for path, content in notes_content:
        parts.append(f"### {path}\n```\n{content[:2000]}\n```\n")

    parts.append(f"\n## Operation: {operation}\n")

    for i, output in enumerate(outputs):
        variant_name = output.get("variant", {}).get("name", f"variant_{i}")
        raw = output.get("raw_output", "(error)")
        parts.append(f"### Variant {i}: {variant_name}\n```\n{raw[:3000]}\n```\n")

    user_message = "\n".join(parts)

    try:
        raw = call_model(system_prompt, user_message, config)
        # Strip code fences if present
        import re
        stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        stripped = re.sub(r"\s*```$", "", stripped).strip()
        scores_data = json.loads(stripped)
        if isinstance(scores_data, list):
            return scores_data
        return []
    except Exception as e:
        return [{"error": str(e)}]


def evaluate(
    operation: str,
    notes: list,
    variants: list,
    base_config: dict,
    judge: bool = False,
    judge_config: Optional[dict] = None,
) -> EvalResult:
    """Run an evaluation comparing multiple variants of a curation operation.

    Args:
        operation: One of 'enrich', 'extract', 'restructure'
        notes: List of (path, content) tuples
        variants: List of Variant objects
        base_config: Base configuration dict
        judge: Whether to run LLM-as-judge scoring
        judge_config: Optional separate config for the judge model

    Returns:
        EvalResult with all outputs, diffs, and optional scores
    """
    result = EvalResult(
        operation=operation,
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        input_notes=[{"path": p, "content": c[:500] + "..." if len(c) > 500 else c}
                      for p, c in notes],
    )

    # Run each variant
    variant_outputs = []
    for variant in variants:
        config = _build_config_with_overrides(base_config, variant.overrides)
        params = variant.overrides.get("params", {})

        start = time.time()
        try:
            raw = _run_operation(operation, notes, config, params)
            duration = int((time.time() - start) * 1000)
            output = VariantOutput(variant=variant, raw_output=raw, duration_ms=duration)
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            output = VariantOutput(variant=variant, error=str(e), duration_ms=duration)

        variant_outputs.append(output)

    # Serialize outputs
    result.outputs = [
        {
            "variant": {"name": vo.variant.name, "overrides": vo.variant.overrides},
            "raw_output": vo.raw_output,
            "duration_ms": vo.duration_ms,
            "error": vo.error,
        }
        for vo in variant_outputs
    ]

    # Compute pairwise diffs
    for i in range(len(variant_outputs)):
        for j in range(i + 1, len(variant_outputs)):
            if variant_outputs[i].raw_output and variant_outputs[j].raw_output:
                diff = _compute_diff(
                    variant_outputs[i].raw_output,
                    variant_outputs[j].raw_output,
                    variant_outputs[i].variant.name,
                    variant_outputs[j].variant.name,
                )
                result.diffs.append({
                    "a": variant_outputs[i].variant.name,
                    "b": variant_outputs[j].variant.name,
                    "diff": diff,
                })

    # Optional LLM scoring
    if judge and any(vo.raw_output for vo in variant_outputs):
        jc = judge_config or base_config
        result.scores = _score_with_llm(operation, notes, result.outputs, jc)

    return result


def save_result(result: EvalResult, output_dir: str) -> tuple:
    """Save evaluation result as JSON and markdown summary.

    Returns (json_path, md_path).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ts = result.timestamp.replace(":", "-").replace("Z", "")
    basename = f"eval-{result.operation}-{ts}"

    # JSON (full data)
    json_path = out / f"{basename}.json"
    json_path.write_text(
        json.dumps(asdict(result), indent=2, default=str),
        encoding="utf-8",
    )

    # Markdown summary
    md_path = out / f"{basename}.md"
    md_lines = [
        f"# Evaluation: {result.operation}",
        f"**Timestamp:** {result.timestamp}",
        f"**Variants:** {len(result.outputs)}",
        "",
        "## Input Notes",
    ]
    for note in result.input_notes:
        md_lines.append(f"- `{note['path']}`")

    md_lines.append("")
    md_lines.append("## Variant Outputs")

    for i, output in enumerate(result.outputs):
        name = output["variant"]["name"]
        overrides = output["variant"].get("overrides", {})
        duration = output.get("duration_ms", 0)
        error = output.get("error")

        md_lines.append(f"### {name}")
        md_lines.append(f"- Overrides: `{json.dumps(overrides)}`")
        md_lines.append(f"- Duration: {duration}ms")

        if error:
            md_lines.append(f"- **Error:** {error}")
        else:
            raw = output.get("raw_output", "")
            preview = raw[:500] + "..." if len(raw) > 500 else raw
            md_lines.append(f"\n```\n{preview}\n```")
        md_lines.append("")

    if result.diffs:
        md_lines.append("## Diffs")
        for d in result.diffs:
            md_lines.append(f"### {d['a']} vs {d['b']}")
            diff_text = d.get("diff", "")
            if diff_text:
                md_lines.append(f"```diff\n{diff_text[:2000]}\n```")
            else:
                md_lines.append("(identical)")
            md_lines.append("")

    if result.scores:
        md_lines.append("## Scores")
        for score in result.scores:
            if isinstance(score, dict):
                idx = score.get("variant_index", "?")
                overall = score.get("overall", "?")
                notes = score.get("notes", "")
                md_lines.append(f"- Variant {idx}: overall={overall} — {notes}")
        md_lines.append("")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return str(json_path), str(md_path)


def format_summary(result: EvalResult) -> str:
    """Format a concise text summary of an evaluation result."""
    lines = [
        f"Evaluation: {result.operation} ({result.timestamp})",
        f"Variants: {len(result.outputs)}",
        "",
    ]

    for i, output in enumerate(result.outputs):
        name = output["variant"]["name"]
        duration = output.get("duration_ms", 0)
        error = output.get("error")
        if error:
            lines.append(f"  [{name}] ERROR ({duration}ms): {error}")
        else:
            raw_len = len(output.get("raw_output", ""))
            lines.append(f"  [{name}] OK ({duration}ms, {raw_len} chars)")

    if result.scores:
        lines.append("")
        lines.append("Scores:")
        for score in result.scores:
            if isinstance(score, dict):
                idx = score.get("variant_index", "?")
                overall = score.get("overall", "?")
                lines.append(f"  Variant {idx}: overall={overall}")

    return "\n".join(lines)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluate curation tool outputs across multiple configurations"
    )
    parser.add_argument(
        "--operation", required=True, choices=["enrich", "extract", "restructure"],
        help="Curation operation to evaluate"
    )
    parser.add_argument(
        "--notes", nargs="+", required=True,
        help="Paths to vault notes (or transcript files for extract)"
    )
    parser.add_argument(
        "--variants", nargs="+", required=True,
        help="JSON strings defining variant overrides, e.g. '{\"model\":\"claude-haiku-4-5\"}'"
    )
    parser.add_argument(
        "--judge", action="store_true",
        help="Run LLM-as-judge scoring on outputs"
    )
    parser.add_argument(
        "--judge-model", default=None,
        help="Model to use for LLM-as-judge (defaults to base config model)"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory for saving results (default: ~/.claude/cyberbrain/evaluations/)"
    )

    args = parser.parse_args()

    # Load base config
    from config import resolve_config
    base_config = resolve_config(os.getcwd())

    # Read note files
    notes = []
    for note_path in args.notes:
        p = Path(note_path)
        if not p.exists():
            print(f"Error: file not found: {note_path}", file=sys.stderr)
            sys.exit(1)
        content = p.read_text(encoding="utf-8")
        notes.append((str(p), content))

    # Parse variants
    variants = []
    for i, v_json in enumerate(args.variants):
        try:
            overrides = json.loads(v_json)
        except json.JSONDecodeError as e:
            print(f"Error parsing variant {i}: {e}", file=sys.stderr)
            sys.exit(1)
        name = overrides.pop("name", f"variant_{i}")
        variants.append(Variant(name=name, overrides=overrides))

    # Judge config
    judge_config = None
    if args.judge and args.judge_model:
        judge_config = dict(base_config)
        judge_config["model"] = args.judge_model

    # Run evaluation
    result = evaluate(
        operation=args.operation,
        notes=notes,
        variants=variants,
        base_config=base_config,
        judge=args.judge,
        judge_config=judge_config,
    )

    # Save results
    output_dir = args.output_dir or str(
        Path.home() / ".claude" / "cyberbrain" / "evaluations"
    )
    json_path, md_path = save_result(result, output_dir)

    # Print summary
    print(format_summary(result))
    print(f"\nResults saved to:\n  JSON: {json_path}\n  Markdown: {md_path}")


if __name__ == "__main__":
    main()
