"""Render Chinese research reports strictly from persisted stage evidence."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_TEMPLATE_DIRECTORY = Path(__file__).with_name("templates")
_TEMPLATE_NAME = "research_run_zh.md.j2"


def _context(
    experiment_id: str,
    stage_payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    first = stage_payloads["PROPOSAL_ACCEPTED"]
    proposal = first["proposal"]
    dataset = first["dataset"]
    manifest = first["manifest"]
    variants = stage_payloads["VARIANTS_GENERATED"]["variants"]
    training = stage_payloads["TRAIN_COMPLETE"]["items"]
    validation = stage_payloads["VALIDATION_COMPLETE"]["items"]
    selection = stage_payloads["SELECTION_SEALED"]
    final_test = stage_payloads["FINAL_TEST_COMPLETE"]["items"]
    gates = stage_payloads["GATES_COMPLETE"]
    registry = stage_payloads["REGISTRY_COMPLETE"]
    validation_by_id = {item["strategy_id"]: item for item in validation}
    final_by_id = {item["strategy_id"]: item for item in final_test}
    phase_by_id = {**validation_by_id, **final_by_id}
    training_by_id = {item["strategy_id"]: item for item in training}
    robustness_by_id = {item["strategy_id"]: item for item in gates["robustness"]}
    evaluations = gates["evaluations"]
    rejected = [item for item in evaluations if not item["passed"]]
    passed = [item for item in evaluations if item["passed"]]
    return {
        "experiment_id": experiment_id,
        "proposal": proposal,
        "dataset": dataset,
        "manifest": manifest,
        "variants": variants,
        "training": training,
        "validation": validation,
        "selection": selection,
        "final_test": final_test,
        "evaluations": evaluations,
        "rejected": rejected,
        "passed": passed,
        "rankings": gates["rankings"],
        "registry": registry,
        "phase_by_id": phase_by_id,
        "robustness_by_id": robustness_by_id,
        "counts": {
            "generated": len(variants),
            "valid": len(validation),
            "tested": len(final_test),
            "rejected": len(rejected),
            "survived": len(passed),
        },
        "traceability": [
            {
                "strategy_id": variant["variant_id"],
                "content_sha256": variant["content_sha256"],
                "train_job_id": training_by_id[variant["variant_id"]]["job_id"],
                "validation_job_id": validation_by_id[variant["variant_id"]]["job_id"],
                "final_job_id": (
                    final_by_id[variant["variant_id"]]["job_id"]
                    if variant["variant_id"] in final_by_id
                    else None
                ),
                "state": registry["states"][variant["variant_id"]],
            }
            for variant in variants
        ],
    }


def render_research_report(
    *,
    root: Path,
    experiment_id: str,
    stage_payloads: Mapping[str, Mapping[str, Any]],
) -> Path:
    """Render stored evidence without recalculating research metrics."""

    if not isinstance(root, Path) or not root.is_dir():
        raise ValueError("root must be an existing directory")
    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIRECTORY),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    rendered = environment.get_template(_TEMPLATE_NAME).render(
        **_context(experiment_id, stage_payloads)
    )
    destination = root / "reports" / "generated" / "research" / f"{experiment_id}.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = rendered.encode("utf-8")
    if destination.exists():
        if destination.read_bytes() == content:
            return destination
        raise ValueError("existing research report content does not match stored evidence")
    temporary: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{experiment_id}-",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary = Path(raw_path)
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError as error:
            raise ValueError("research report was concurrently created") from error
        temporary.unlink()
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination
