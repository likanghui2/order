from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
TASK_DIR = APP_DIR / "task"


def normalize_source(source: str) -> str:
    return str(source or "").strip().upper()


def source_modules(module_file: str = "sham_booking.py") -> dict[str, str]:
    modules = {}
    if not TASK_DIR.exists():
        return modules
    for item in TASK_DIR.iterdir():
        if not item.is_dir() or item.name.startswith((".", "_")):
            continue
        if not (item / module_file).is_file():
            continue
        source = normalize_source(item.name)
        modules[source] = f"task.{item.name}.{module_file[:-3]}"
    return modules


def supported_sources() -> list[str]:
    return sorted(source_modules())


def module_for_source(source: str, task_type: str = "shamBooking") -> str:
    module_file = {
        "search": "search.py",
        "verify": "search.py",
        "booking": "booking.py",
        "orderDetail": "order_detail.py",
        "shamBooking": "sham_booking.py",
    }.get(str(task_type or "").strip(), "sham_booking.py")
    return source_modules(module_file).get(normalize_source(source), "")
