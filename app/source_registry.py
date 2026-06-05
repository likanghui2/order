SOURCE_MODULES = {
    "5JWEB": "task.5Jweb.sham_booking",
    "TGWEB": "task.TGweb.sham_booking",
    "VJWEB": "task.VJweb.sham_booking",
    "VZWEB": "task.VZweb.sham_booking",
}


def normalize_source(source: str) -> str:
    return str(source or "").strip().upper()


def supported_sources() -> list[str]:
    return sorted(SOURCE_MODULES)
