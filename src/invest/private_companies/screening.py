"""Evidence checklists: coverage is not a business-quality recommendation."""

from collections import Counter

from .models import CompanyBundle

CHECKLISTS = {
    "startup": [
        ("customer_retention", "Customer retention"),
        ("revenue", "Revenue and product demand"),
        ("gross_margin", "Gross margin"),
        ("cash_runway_months", "Cash runway"),
        ("funding_needs", "Future funding needs"),
        ("dilution", "Ownership dilution"),
    ],
    "established": [
        ("revenue", "Revenue history"),
        ("operating_cash_flow", "Operating cash generation"),
        ("debt", "Debt"),
        ("customer_concentration", "Customer concentration"),
        ("owner_dependence", "Dependence on the owner"),
    ],
}


def screen_company(bundle: CompanyBundle) -> dict:
    """Expose evidence coverage and access; never infer quality from missing data."""
    criteria = []
    for metric, label in CHECKLISTS.get(bundle.company.company_type, []):
        matching = [item for item in bundle.observations if item.metric == metric]
        # Compare only assertions with the same period, unit and currency.
        groups = {}
        for item in matching:
            key = (item.period_end, item.unit, item.currency)
            # Numeric assertions compare by value, while booleans remain distinct.
            value_key = (
                ("number", item.value)
                if isinstance(item.value, (int, float)) and not isinstance(item.value, bool)
                else (type(item.value).__name__, item.value)
            )
            groups.setdefault(key, set()).add(value_key)
        conflict = any(len(values) > 1 for values in groups.values())
        criteria.append(
            {
                "metric": metric,
                "label": label,
                "status": "conflicting" if conflict else "documented" if matching else "unknown",
                "observation_count": len(matching),
                "assessment": "Requires analyst review" if matching else "No evidence recorded",
            }
        )
    counts = Counter(item.evidence_type for item in bundle.observations)
    complete_offers = [
        item
        for item in bundle.offers
        if item.status == "available" and item.minimum_investment is not None and item.terms_summary
    ]
    availability = (
        "available"
        if complete_offers
        else (
            "closed"
            if bundle.offers and all(item.status == "closed" for item in bundle.offers)
            else "unknown"
        )
    )
    return {
        "company_type": bundle.company.company_type,
        "criteria": criteria,
        "business_assessment": "classification_required"
        if bundle.company.company_type == "unclassified"
        else "unassessed",
        "evidence_summary": {
            "observation_count": len(bundle.observations),
            "source_count": len({str(item.source_url) for item in bundle.observations}),
            "reported": counts["reported"],
            "estimated": counts["estimated"],
            "verified": counts["verified"],
            "confidence": "unassessed" if bundle.observations else "unknown",
        },
        "investment_availability": availability,
        "availability_note": "Recorded offer terms require eligibility and availability checks; no purchase recommendation.",
    }
