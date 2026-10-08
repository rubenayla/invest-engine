"""Public, read-only private-company directory; never renders research dossiers."""

from __future__ import annotations

from html import escape
from urllib.parse import urlsplit


def safe_url(value: object) -> str:
    """Accept absolute web links only, including after leading whitespace."""
    url = str(value or "").strip()
    try:
        parts = urlsplit(url)
        if parts.scheme in {"https", "http"} and parts.hostname and not parts.username:
            return url
    except ValueError:
        pass
    return ""


def public_company(company: dict) -> dict | None:
    """Explicit opt-in and field allowlisting protect the public dashboard."""
    if company.get("public_visibility") is not True or company.get("listing_status") == "public":
        return None
    fields = (
        "id",
        "legal_name",
        "company_type",
        "registration_number",
        "jurisdiction",
        "country",
        "website",
        "sector",
        "listing_status",
    )
    result = {key: company.get(key) for key in fields}
    result["website"] = safe_url(company.get("website"))
    # Only checklist states are published. Observations, offers, source documents,
    # free-text conclusions and dossier references remain private.
    screening = company.get("screening") or {}
    result["screening"] = {
        "evidence_status": (screening.get("evidence_summary") or {}).get("confidence", "unknown"),
        "investment_status": screening.get("investment_availability", "unknown"),
        "checks": [
            {"criterion": item.get("label"), "status": item.get("status")}
            for item in screening.get("criteria", [])
            if isinstance(item, dict)
        ],
    }
    return result


def add_navigation(html: str, *, mobile: bool = False) -> str:
    link = (
        '<a href="/private-companies" class="'
        + ("pill" if mobile else "btn btn-docs")
        + '">Private companies</a>'
    )
    marker = '<div class="toolbar-meta">' if mobile else '<div class="header-actions">'
    return html.replace(marker, marker + link, 1)


def render_directory(
    companies: list[dict], *, state: str = "ready", company_type: str = "all", query: str = ""
) -> str:
    """Render a filtered directory using escaped text and validated links."""

    def text(value):
        return escape(str(value if value is not None else "Unknown"))

    rows = []
    for company in companies:
        if company_type != "all" and company.get("company_type") != company_type:
            continue
        searchable = " ".join(
            str(company.get(k) or "")
            for k in ("legal_name", "country", "jurisdiction", "sector", "registration_number")
        )
        if query.casefold() not in searchable.casefold():
            continue
        screening = company.get("screening") or {}
        website = safe_url(company.get("website"))
        name = text(company.get("legal_name"))
        listing = (
            "<small>Private listing status unconfirmed</small>"
            if company.get("listing_status") != "confirmed_private"
            else ""
        )
        if website:
            name = f'<a href="{escape(website, quote=True)}" rel="noopener noreferrer">{name}</a>'
        checks = screening.get("checks") or []
        details = "".join(
            f"<li>{text(item.get('criterion'))}: {text(item.get('status'))}</li>" for item in checks
        )
        detail_html = (
            f"<details><summary>Evidence checklist</summary><ul>{details}</ul></details>"
            if details
            else '<span class="muted">Checklist not assessed</span>'
        )
        rows.append(
            f"<tr><td>{name}{listing}<small>{text(company.get('sector'))}</small></td>"
            f"<td>{text(company.get('company_type'))}</td>"
            f"<td>{text(company.get('country') or company.get('jurisdiction'))}</td>"
            f"<td>{text(screening.get('evidence_status', 'unknown'))}<br>{detail_html}</td>"
            f"<td>{text(screening.get('investment_status', 'research_candidate'))}</td></tr>"
        )
    messages = {
        "not_initialized": "Private-company storage is not initialized. Run the private-company setup command before importing records.",
        "unavailable": "Private-company database is unavailable. Check database configuration and connectivity.",
    }
    message = messages.get(state)
    if message is None and not rows:
        message = (
            "No companies match these filters."
            if companies
            else "No companies have been explicitly approved for public display. Private research remains private."
        )
    options = "".join(
        f'<option value="{key}"'
        + (" selected" if company_type == key else "")
        + f">{label}</option>"
        for key, label in [
            ("all", "All private companies"),
            ("startup", "Startups"),
            ("established", "Established businesses"),
            ("unclassified", "Unclassified"),
        ]
    )
    status = f'<p role="status" class="notice">{text(message)}</p>' if message else ""
    table = (
        (
            '<div class="table-wrap"><table><thead><tr><th scope="col">Company</th><th scope="col">Type</th>'
            '<th scope="col">Country / jurisdiction</th><th scope="col">Evidence</th><th scope="col">Investment status</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        )
        if rows
        else ""
    )
    return (
        """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Private companies · Invest</title><style>
:root{color-scheme:light dark;--bg:#f7f8f3;--fg:#183d32;--muted:#51675d;--line:#ccd5ca;--surface:#fff}*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:20px}
header{display:flex;align-items:center;gap:18px;flex-wrap:wrap}h1{font-size:23px;margin:0}a{color:inherit;text-underline-offset:3px}
form{display:flex;align-items:end;gap:12px;flex-wrap:wrap;margin:20px 0}label{display:flex;flex-direction:column;gap:4px}
input,select,button{font:inherit;padding:8px;border:1px solid var(--line);border-radius:5px;background:var(--surface);color:var(--fg)}
button{cursor:pointer}a:focus-visible,input:focus-visible,select:focus-visible,button:focus-visible,summary:focus-visible{outline:3px solid #518c70;outline-offset:3px}
.muted,small{color:var(--muted)}small{display:block}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;text-align:left}
th,td{padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:13px}summary{cursor:pointer;font-size:13px}
.notice{padding:15px;border:1px solid var(--line);background:var(--surface)}ul{padding-left:20px}details{min-width:180px}
@media(prefers-color-scheme:dark){:root{--bg:#101a16;--fg:#dce9df;--muted:#abc0b0;--line:#3e5045;--surface:#1a2820}}
@media(max-width:600px){main{padding:14px}h1{font-size:20px}form{gap:8px}input{max-width:100%}th,td{padding:9px 7px}}
</style></head><body><main><header><h1>Private companies</h1><a href="/">Public stocks</a><a href="/m">Mobile stocks</a></header>
<p class="muted">Startups and established businesses use separate evidence checklists. Unknown means unverified. Public display requires explicit approval.</p>
<form method="get"><label>Opportunity type<select name="type">"""
        + options
        + '''</select></label>
<label>Search companies<input type="search" name="q" value="'''
        + escape(query, quote=True)
        + """" placeholder="Name, sector or country"></label>
<button type="submit">Apply filters</button></form>"""
        + status
        + table
        + "</main></body></html>"
    )
