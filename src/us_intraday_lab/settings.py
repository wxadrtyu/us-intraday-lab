from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LabPaths:
    root: Path
    raw: Path
    canonical: Path
    catalog: Path
    manifests: Path

    @classmethod
    def from_root(cls, root: Path) -> "LabPaths":
        resolved = root.resolve()
        return cls(
            root=resolved,
            raw=resolved / "data" / "raw",
            canonical=resolved / "data" / "lake" / "canonical",
            catalog=resolved / "data" / "catalog" / "research.duckdb",
            manifests=resolved / "data" / "manifests",
        )
