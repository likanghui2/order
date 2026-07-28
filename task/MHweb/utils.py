from datetime import datetime
from typing import Optional


def web_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).strip()
    if len(normalized) == 8 and normalized.isdigit():
        parsed = datetime.strptime(normalized, "%Y%m%d")
    elif len(normalized) >= 10 and normalized[4] == "-":
        parsed = datetime.strptime(normalized[:10], "%Y-%m-%d")
    else:
        return normalized
    return parsed.strftime("%Y-%m-%dT00:00:00.000")
