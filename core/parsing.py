from datetime import date

from .api import ApiError


def parse_iso_date(value, field, *, default=None):
    if value in (None, "") and default is not None:
        return default
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ApiError(
            f"{field}은(는) YYYY-MM-DD 형식이어야 합니다.",
            fields={field: "잘못된 날짜입니다."},
        ) from exc
