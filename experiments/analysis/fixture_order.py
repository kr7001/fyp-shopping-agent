"""The order a market's results pages list its listings in, as its fixture records it (23 October
2026). One definition, read by claim.py, where a key's listings render (`key_positions`), and by
env/check_aplus_market.py, which checks the live shop against it before any run.

Standard library only, and nothing of the analysis imported: the checker's browser checks run
under the Playwright venv, .venv-naive, which holds no scipy. Until the auditor's check of
2df6dc3 this lived in claim.py, so the checker imported claim.py, and through compare_cells
scipy, and could not start under the venv (tests/test_aplus_market.py, TheVenvImports).
"""

from __future__ import annotations


def fixture_order(fixture: dict) -> tuple[list[str] | None, str]:
    """A fixture's listings, as lowercased SKUs, in the order its results pages list them, and
    which order that is: "accepted", the live order its seed search recorded when it accepted
    the market, which the fixture holds under `_generated.search`; else "predicted", the order
    the generator predicted (`_instance.predicted_order`); else (None, "none")."""
    tried = ((fixture.get("_generated") or {}).get("search") or {}).get("tried") or []
    accepted = [entry for entry in tried if entry.get("outcome") == "accepted" and entry.get("live_order")]
    if accepted:
        return [sku.lower() for sku in accepted[-1]["live_order"]], "accepted"
    predicted = (fixture.get("_instance") or {}).get("predicted_order")
    return ([sku.lower() for sku in predicted], "predicted") if predicted else (None, "none")
