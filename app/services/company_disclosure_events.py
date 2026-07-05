from typing import Any


DISCLOSURE_EVENT_LABELS = {
    "periodic": "정기보고서",
    "ownership": "지분/최대주주",
    "executive": "임원",
    "capital": "자본",
    "dividend": "배당",
    "audit": "감사/회계",
    "other": "기타",
}


def classify_disclosure_event(report_name: str) -> str:
    name = str(report_name or "")
    if any(keyword in name for keyword in ["사업보고서", "반기보고서", "분기보고서"]):
        return "periodic"
    if any(
        keyword in name
        for keyword in ["최대주주", "대량보유", "임원ㆍ주요주주", "임원·주요주주"]
    ):
        return "ownership"
    if any(keyword in name for keyword in ["대표이사", "사외이사", "임원"]):
        return "executive"
    if any(
        keyword in name
        for keyword in ["유상증자", "무상증자", "전환사채", "신주인수권", "자본"]
    ):
        return "capital"
    if any(keyword in name for keyword in ["배당", "현금ㆍ현물배당", "현금·현물배당"]):
        return "dividend"
    if any(keyword in name for keyword in ["감사", "회계", "감사보고서"]):
        return "audit"
    return "other"


def normalize_disclosure_events(disclosures: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = (disclosures or {}).get("list") or []
    if not isinstance(items, list):
        return []

    events: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("report_nm") or item.get("title") or "")
        category = classify_disclosure_event(title)
        events.append(
            {
                "date": item.get("rcept_dt") or item.get("date"),
                "title": title,
                "category": category,
                "category_label": DISCLOSURE_EVENT_LABELS[category],
                "corp_name": item.get("corp_name") or item.get("flr_nm"),
                "receipt_no": item.get("rcept_no"),
                "viewer_url": item.get("viewer_url"),
            }
        )
    return events
