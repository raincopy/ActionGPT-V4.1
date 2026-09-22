from __future__ import annotations

from pathlib import Path

from .config import ACTGPT_ROOT, EXCLUDED_NAMES, PROJECT_ROOT, ROOTS_CFG
from .root_config import RootConfig


class PathService:
    def __init__(self, root: Path | None = None, *, block_actgpt: bool = True) -> None:
        self.root_config = RootConfig(ROOTS_CFG, PROJECT_ROOT) if root is None else None
        self._fixed_roots = (root.resolve(),) if root is not None else ()
        self.block_actgpt = block_actgpt

    @property
    def roots(self) -> tuple[Path, ...]:
        return self.root_config.roots if self.root_config else self._fixed_roots

    @property
    def root(self) -> Path:
        return self.roots[0]

    def add_root(self, value: str | Path) -> Path:
        if not self.root_config:
            raise RuntimeError("고정 루트 PathService에서는 루트를 변경할 수 없다")
        return self.root_config.add(value)

    def update_root(self, old_value: str | Path, new_value: str | Path) -> Path:
        if not self.root_config:
            raise RuntimeError("고정 루트 PathService에서는 루트를 변경할 수 없다")
        return self.root_config.update(old_value, new_value)

    def remove_root(self, value: str | Path) -> Path:
        if not self.root_config:
            raise RuntimeError("고정 루트 PathService에서는 루트를 변경할 수 없다")
        return self.root_config.remove(value)

    def is_allowed(self, path: str | Path) -> bool:
        candidate = Path(path).expanduser().resolve()
        return any(candidate == root or root in candidate.parents for root in self.roots)

    def resolve(self, value: str, *, must_exist: bool = False, allow_actgpt: bool = False) -> Path:
        raw = Path(value or ".")
        path = (raw if raw.is_absolute() else self.root / raw).resolve()
        if not self.is_allowed(path):
            raise ValueError(f"프로젝트 루트 밖의 경로는 허용하지 않는다: {path}")
        if not allow_actgpt and self.block_actgpt:
            if path == ACTGPT_ROOT or ACTGPT_ROOT in path.parents:
                raise ValueError("서버 자신의 경로에는 작업할 수 없다")
            containing_root = next(root for root in self.roots if path == root or root in path.parents)
            relative = path.relative_to(containing_root)
            if any(part in EXCLUDED_NAMES for part in relative.parts):
                raise ValueError(f"제외된 경로이다: {path}")
        if must_exist and not path.exists():
            raise FileNotFoundError(str(path))
        return path

    def relative(self, path: Path) -> str:
        resolved = path.resolve()
        if resolved == self.root:
            return "."
        if self.root in resolved.parents:
            return str(resolved.relative_to(self.root)).replace("\\", "/")
        if self.is_allowed(resolved):
            return str(resolved)
        raise ValueError(f"프로젝트 루트 밖의 경로는 허용하지 않는다: {resolved}")
