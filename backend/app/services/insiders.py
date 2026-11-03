"""Insider transactions from SEC Form 4 filings."""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from datetime import date, timedelta
from typing import Any

from app.providers.sec import SEC_SOURCE, filing_index_url

TRANSACTION_CODES = {
    "P": "Open-market purchase",
    "S": "Open-market sale",
    "A": "Grant or award",
    "M": "Option exercise",
    "F": "Shares withheld for tax",
    "G": "Gift",
    "C": "Conversion",
    "D": "Disposition to the issuer",
    "J": "Other",
}
MAX_FILINGS = 60


def _text(element: ElementTree.Element | None, path: str) -> str | None:
    if element is None:
        return None
    found = element.find(path)
    if found is None:
        return None
    value = (found.text or "").strip()
    return value or None


def _number(element: ElementTree.Element | None, path: str) -> float | None:
    value = _text(element, path)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true"}


def parse_form4(xml_text: str) -> dict[str, Any]:
    """Extract reporting owners and non-derivative transactions from a Form 4 XML document."""
    root = ElementTree.fromstring(xml_text.strip())
    footnotes = {
        footnote.get("id"): " ".join("".join(footnote.itertext()).split())
        for footnote in root.iter("footnote")
        if footnote.get("id")
    }
    owners = []
    for owner in root.findall("reportingOwner"):
        relationship = owner.find("reportingOwnerRelationship")
        roles = []
        if _flag(_text(relationship, "isDirector")):
            roles.append("Director")
        if _flag(_text(relationship, "isOfficer")):
            roles.append(_text(relationship, "officerTitle") or "Officer")
        if _flag(_text(relationship, "isTenPercentOwner")):
            roles.append("10% owner")
        if _flag(_text(relationship, "isOther")):
            roles.append(_text(relationship, "otherText") or "Other")
        owners.append({"name": _text(owner, "reportingOwnerId/rptOwnerName") or "Unknown", "roles": roles})

    plan_checkbox = _text(root, "aff10b5One")
    transactions = []
    for row in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        footnote_text = " ".join(
            footnotes.get(reference.get("id"), "") for reference in row.iter("footnoteId")
        ).lower()
        transactions.append(
            {
                "date": (_text(row, "transactionDate/value") or "")[:10] or None,
                "code": _text(row, "transactionCoding/transactionCode"),
                "shares": _number(row, "transactionAmounts/transactionShares/value"),
                "price": _number(row, "transactionAmounts/transactionPricePerShare/value"),
                "acquired_disposed": _text(row, "transactionAmounts/transactionAcquiredDisposedCode/value"),
                "shares_after": _number(row, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
                "ownership": _text(row, "ownershipNature/directOrIndirectOwnership/value"),
                "footnote_mentions_plan": "10b5-1" in footnote_text,
            }
        )
    return {
        "issuer_symbol": _text(root, "issuer/issuerTradingSymbol"),
        "period": _text(root, "periodOfReport"),
        # The 10b5-1 checkbox exists on filings since April 2023; older filings may cite it in footnotes.
        "plan_checkbox": _flag(plan_checkbox) if plan_checkbox is not None else None,
        "owners": owners,
        "transactions": transactions,
    }


class InsiderService:
    def __init__(self, sec: Any, market: Any) -> None:
        self.sec = sec
        self.market = market

    def activity(self, symbol: str, *, days: int = 90, today: date | None = None) -> dict[str, Any]:
        meta, bars, _ = self.market.ensure_history(symbol)
        base = {"symbol": meta["symbol"], "days": days, "source": f"{SEC_SOURCE} Form 4 filings"}
        if meta["asset_type"] == "ETF":
            return {**base, "applicable": False, "reason": "ETFs have no corporate insiders filing Form 4."}
        company = self.sec.company(meta["symbol"])
        submissions, fetched_at, stale = self.sec.submissions(company["cik"])
        recent = (submissions.get("filings") or {}).get("recent") or {}
        effective_today = today or (date.fromisoformat(bars[-1]["date"]) if bars else date.today())
        cutoff = (effective_today - timedelta(days=days)).isoformat()
        filings = [
            (recent["filingDate"][index], recent["accessionNumber"][index], recent["primaryDocument"][index])
            for index, form in enumerate(recent.get("form") or [])
            if form in {"4", "4/A"} and recent["filingDate"][index] >= cutoff
        ]
        truncated = len(filings) > MAX_FILINGS
        rows: list[dict[str, Any]] = []
        failed = 0
        for filed, accession, document in filings[:MAX_FILINGS]:
            try:
                # The primary document is the XSL-rendered view; the raw XML has the same file name.
                parsed = self.sec.form4(company["cik"], accession, document.rsplit("/", 1)[-1])
            except Exception:
                failed += 1
                continue
            owner = parsed["owners"][0] if parsed["owners"] else {"name": "Unknown", "roles": []}
            for transaction in parsed["transactions"]:
                planned = parsed["plan_checkbox"] or transaction["footnote_mentions_plan"]
                shares = transaction["shares"]
                price = transaction["price"]
                rows.append(
                    {
                        "filed": filed,
                        "date": transaction["date"],
                        "owner": owner["name"],
                        "role": ", ".join(owner["roles"]) or "Not stated",
                        "code": transaction["code"],
                        "description": TRANSACTION_CODES.get(transaction["code"] or "", "Other"),
                        "shares": shares,
                        "price": price,
                        "value": round(shares * price, 2) if shares is not None and price else None,
                        "acquired_disposed": transaction["acquired_disposed"],
                        "planned_10b5_1": planned,
                        "shares_after": transaction["shares_after"],
                        "url": filing_index_url(company["cik"], accession),
                    }
                )
        rows.sort(key=lambda row: (row["date"] or "", row["filed"]), reverse=True)
        purchases = [row for row in rows if row["code"] == "P"]
        sales = [row for row in rows if row["code"] == "S"]
        bought = sum(row["value"] or 0 for row in purchases)
        sold = sum(row["value"] or 0 for row in sales)
        planned = sum(row["value"] or 0 for row in sales if row["planned_10b5_1"])
        warnings = []
        if truncated:
            warnings.append(f"Only the latest {MAX_FILINGS} of {len(filings)} Form 4 filings were read.")
        if failed:
            warnings.append(f"{failed} Form 4 filing(s) could not be read and are excluded.")
        return {
            **base,
            "applicable": True,
            "since": cutoff,
            "filings": len(filings),
            "summary": {
                "purchase_value": round(bought, 2),
                "sale_value": round(sold, 2),
                "net_value": round(bought - sold, 2),
                "buyers": len({row["owner"] for row in purchases}),
                "sellers": len({row["owner"] for row in sales}),
                "planned_sale_value": round(planned, 2),
                "other_transactions": len(rows) - len(purchases) - len(sales),
            },
            "transactions": rows,
            "latest_filing": filings[0][0] if filings else None,
            "fetched_at": fetched_at,
            "stale": stale,
            "warnings": warnings,
        }
