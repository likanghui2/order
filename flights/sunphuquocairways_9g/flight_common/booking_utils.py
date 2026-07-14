from datetime import datetime
from typing import Optional


def app_date(value: Optional[str]) -> Optional[str]:
    """Normalize task dates to the format required by the 9G App API."""
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
