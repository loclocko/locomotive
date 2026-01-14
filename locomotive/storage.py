from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from .utils import read_json, write_json, write_text, utc_now, ensure_dir


@dataclass
class Storage:
    root: Path

    @classmethod
    def from_root(cls, root: Union[str, Path]) -> "Storage":
        return cls(Path(root))

    def baseline_path(self) -> Path:
        return self.root / "baseline.json"

    def runs_dir(self) -> Path:
        return self.root / "runs"

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir() / run_id

    def raw_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "raw"

    def metrics_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "metrics.json"

    def analysis_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "analysis.json"

    def report_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "report.html"

    def run_meta_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def ensure_run(self, run_id: str) -> None:
        ensure_dir(self.raw_dir(run_id))

    def load_json(self, path: Path) -> Any:
        return read_json(path)

    def save_json(self, path: Path, data: Any) -> None:
        write_json(path, data)

    def save_text(self, path: Path, content: str) -> None:
        write_text(path, content)

    def set_baseline(self, run_id: str) -> None:
        payload = {"run_id": run_id, "set_at": utc_now()}
        self.save_json(self.baseline_path(), payload)

    def get_baseline(self) -> Optional[str]:
        path = self.baseline_path()
        if not path.exists():
            return None
        data = self.load_json(path)
        return data.get("run_id")
