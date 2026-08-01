import hashlib
import json
from pathlib import Path
from typing import Protocol

from us_intraday_lab.contracts.hypotheses import HypothesisProposal

MAX_FIXTURE_BYTES = 1_000_000


class ProposalProvider(Protocol):
    def load(self) -> HypothesisProposal: ...


class FixtureProposalProvider:
    """Load a local test/research fixture through the public proposal contract."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("fixture path must be a Path")
        self._path = path

    def load(self) -> HypothesisProposal:
        if not self._path.is_file() or self._path.is_symlink():
            raise ValueError("proposal fixture must be a regular non-symlink file")
        if self._path.stat().st_size > MAX_FIXTURE_BYTES:
            raise ValueError("proposal fixture exceeds the bounded read size")
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if type(payload) is not dict:
            raise ValueError("proposal fixture root must be a JSON object")
        return HypothesisProposal.model_validate(payload)


def proposal_hash(proposal: HypothesisProposal) -> str:
    if type(proposal) is not HypothesisProposal:
        raise TypeError("proposal must be an exact HypothesisProposal")
    canonical = json.dumps(
        proposal.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
