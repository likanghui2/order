from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
TASK_DIR = APP_DIR / "task"


def normalize_source(source: str) -> str:
    return str(source or "").strip().upper()


def source_modules() -> dict[str, str]:
    modules = {}
    if not TASK_DIR.exists():
        return modules
    for item in TASK_DIR.iterdir():
        if not item.is_dir() or item.name.startswith((".", "_")):
            continue
        if not (item / "sham_booking.py").is_file():
            continue
        source = normalize_source(item.name)
        modules[source] = f"task.{item.name}.sham_booking"
    return modules


def supported_sources() -> list[str]:
    return sorted(source_modules())


def module_for_source(source: str) -> str:
    return source_modules().get(normalize_source(source), "")
