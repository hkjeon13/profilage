from typing import Any


def _items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    item = (payload or {}).get("list", [])
    if isinstance(item, list):
        return [row for row in item if isinstance(row, dict)]
    return [item] if isinstance(item, dict) else []


def _first_value(row: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _number(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def normalize_ownership(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    rows = _items(payload)
    if not rows:
        return None
    holders = []
    for row in rows:
        ratio = _first_value(
            row,
            ["bsis_posesn_stock_qota_rt", "posesn_stock_qota_rt", "stock_qota_rt"],
        )
        ratio_number = _number(ratio)
        if ratio_number is None:
            continue
        holders.append(
            {
                "name": _first_value(row, ["nm", "holder_nm", "stockholdr_nm"]),
                "relation": _first_value(row, ["relate", "relate_nm"]),
                "ratio": ratio,
                "ratio_number": ratio_number,
            }
        )
    holders.sort(key=lambda holder: holder["ratio_number"], reverse=True)
    largest_holder = holders[0] if holders else {}
    first = rows[0]
    return {
        "largest_holder_name": largest_holder.get("name")
        or _first_value(first, ["nm", "holder_nm", "stockholdr_nm"]),
        "largest_holder_relation": largest_holder.get("relation")
        or _first_value(first, ["relate", "relate_nm"]),
        "largest_holder_ratio": largest_holder.get("ratio")
        or _first_value(
            first,
            ["bsis_posesn_stock_qota_rt", "posesn_stock_qota_rt", "stock_qota_rt"],
        ),
        "holders": holders,
        "rows": rows,
    }


def normalize_dividend(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    rows = _items(payload)
    if not rows:
        return None
    dividend_per_share = None
    payout_ratio = None
    for row in rows:
        label = str(row.get("se") or row.get("name") or "")
        if "주당" in label and "배당" in label:
            dividend_per_share = _first_value(row, ["thstrm", "thstrm_amount", "value"])
        if "배당성향" in label:
            payout_ratio = _first_value(row, ["thstrm", "thstrm_amount", "value"])
    return {
        "dividend_per_share": dividend_per_share,
        "payout_ratio": payout_ratio,
        "rows": rows,
    }


def normalize_audit(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    rows = _items(payload)
    if not rows:
        return None
    first = rows[0]
    return {
        "auditor": _first_value(first, ["adtor", "auditor", "auditor_nm", "account_nm"]),
        "opinion": _first_value(first, ["adt_opinion", "audit_opinion", "opinion"]),
        "rows": rows,
    }


def normalize_ratios(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    rows = _items(payload)
    wanted = ["부채비율", "영업이익률", "ROE", "ROA", "자기자본이익률", "총자산이익률"]
    items = []
    for label in wanted:
        match = next(
            (
                row
                for row in rows
                if label in str(row.get("idx_nm") or row.get("account_nm") or "")
            ),
            None,
        )
        if match:
            items.append(
                {
                    "name": _first_value(match, ["idx_nm", "account_nm"]),
                    "value": _first_value(match, ["idx_val", "thstrm_amount", "value"]),
                }
            )
    return {"items": items, "rows": rows} if items or rows else None


def normalize_dart_insights(raw: dict[str, Any], *, basis: dict[str, Any]) -> dict[str, Any]:
    return {
        "basis": basis,
        "ownership": normalize_ownership(raw.get("major_shareholders")),
        "dividend": normalize_dividend(raw.get("dividends")),
        "audit": normalize_audit(raw.get("audit_opinion")),
        "ratios": normalize_ratios(raw.get("financial_ratios")),
    }


def normalize_capital_detail(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "capital",
        "total_stock": _items(raw.get("total_stock")),
        "treasury_stock": _items(raw.get("treasury_stock")),
    }


def normalize_people_detail(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "people",
        "executives": _items(raw.get("executives")),
        "employees": _items(raw.get("employees")),
    }
