from pathlib import Path

from core.config import settings


def workspace_root() -> Path:
    if settings.workspace_root:
        return Path(settings.workspace_root).resolve()
    return Path(__file__).resolve().parents[2] / "data" / "workspace"


def search_roots() -> list[Path]:
    raw = settings.file_search_roots.strip()
    if raw:
        roots = [Path(part.strip()) for part in raw.replace(",", ";").split(";") if part.strip()]
    else:
        home = Path.home()
        roots = [home / "Documents", home / "Desktop", home / "Downloads", home / "OneDrive"]
    roots.append(workspace_root())
    unique: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved not in unique:
            unique.append(resolved)
    return unique


def safe_path(relative: str) -> Path:
    root = workspace_root()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise PermissionError("Path is outside the workspace.")
    return candidate


def allowed_file(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(path)
    if any(resolved.is_relative_to(root) for root in search_roots()):
        return resolved
    raise PermissionError("Path is outside the allowed search folders.")
