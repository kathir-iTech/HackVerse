def compute_risk_indicators(
    vision_result,
    voice_result,
    transaction_result,
    discrepancy_flags,
    location_verification,
    photo_reuse_flag,
) -> dict:
    high_transaction_volatility = bool(
        transaction_result
        and not transaction_result.get("error")
        and transaction_result.get("volatility") == "high"
    )
    unverifiable_location = bool(
        location_verification
        and location_verification.get("location_found") is False
    )
    cross_source_conflicts = bool(discrepancy_flags and len(discrepancy_flags) > 0)
    possible_photo_reuse = photo_reuse_flag is not None

    present = 0
    if vision_result is not None and "error" not in vision_result:
        present += 1
    if voice_result is not None and "error" not in voice_result:
        present += 1
    if transaction_result is not None and "error" not in transaction_result:
        present += 1
    incomplete_evidence = present < 2

    indicators = {
        "high_transaction_volatility": high_transaction_volatility,
        "unverifiable_location": unverifiable_location,
        "cross_source_conflicts": cross_source_conflicts,
        "possible_photo_reuse": possible_photo_reuse,
        "incomplete_evidence": incomplete_evidence,
    }

    indicators_triggered = sum(1 for v in indicators.values() if v)

    if indicators_triggered <= 1:
        risk_summary = "No significant risk indicators detected."
    elif indicators_triggered == 2:
        risk_summary = "A few factors warrant a closer look during review."
    else:
        risk_summary = "Multiple factors suggest this case needs careful manual review before proceeding."

    return {
        "indicators": indicators,
        "indicators_triggered": indicators_triggered,
        "risk_summary": risk_summary,
    }


def _extract_vision_inventory_level(vision_result) -> str | None:
    if not vision_result or "error" in vision_result:
        return None
    summary = vision_result.get("summary", "") or ""
    if not summary:
        return None
    lower = summary.lower()
    if any(k in lower for k in ("minimal", "low stock", "barely any", "empty shelf", "sparse")):
        return "low"
    if any(k in lower for k in ("well-stocked", "full", "abundant", "high inventory", "well stocked")):
        return "high"
    return "moderate"


def compute_cross_verification(
    vision_result,
    voice_result,
    transaction_result,
    document_result,
) -> list[str]:
    flags = []
    if not transaction_result or "error" in transaction_result:
        return flags

    total_inflow = transaction_result.get("total_inflow", 0) or 0
    transaction_count = transaction_result.get("transaction_count", 0) or 0
    txn_trend = transaction_result.get("trend", "") or ""

    vision_inventory = _extract_vision_inventory_level(vision_result)
    if vision_inventory == "low" and total_inflow > 500000:
        flags.append(
            "Transaction inflow is high (₹{:,.0f}) but photos show minimal inventory — "
            "verify whether the reported sales volume matches visible stock levels.".format(total_inflow)
        )
    if vision_inventory == "high" and total_inflow < 50000:
        flags.append(
            "Photos show well-stocked inventory but transaction inflow is very low (₹{:,.0f}) — "
            "verify whether the business is actively trading.".format(total_inflow)
        )

    if document_result and document_result.get("extracted"):
        doc_extracted = document_result["extracted"]
        gst_cert = doc_extracted.get("gst_certificate", {})
        kf_gst = gst_cert.get("key_fields", {}) if isinstance(gst_cert, dict) else {}
        gst_turnover_str = kf_gst.get("annual_turnover") or kf_gst.get("turnover") or ""
        if gst_turnover_str:
            try:
                gst_turnover = float(str(gst_turnover_str).replace(",", "").replace("₹", "").strip())
                if gst_turnover > 0 and total_inflow > 0:
                    ratio = total_inflow / gst_turnover
                    if ratio > 5:
                        flags.append(
                            "Transaction inflow (₹{:,.0f}) appears disproportionately high compared to "
                            "GST-registered turnover (₹{:,.0f}) — verify turnover declaration.".format(
                                total_inflow, gst_turnover
                            )
                        )
                    elif ratio < 0.1:
                        flags.append(
                            "Transaction inflow (₹{:,.0f}) appears very low compared to "
                            "GST-registered turnover (₹{:,.0f}) — verify if this is a partial statement.".format(
                                total_inflow, gst_turnover
                            )
                        )
            except (ValueError, TypeError):
                pass

    voice_extracted = voice_result.get("extracted", {}) if voice_result else {}
    claimed_tenure = voice_extracted.get("years_operating") if isinstance(voice_extracted, dict) else None
    if claimed_tenure and transaction_result.get("date_range_days"):
        try:
            claimed_days = float(claimed_tenure) * 365
            actual_days = float(transaction_result["date_range_days"])
            if claimed_days > actual_days * 1.5:
                flags.append(
                    "Voice note claims ~{:.0f} years of operation but transaction records only span {} days — "
                    "ask for older ledger entries or passbook to verify tenure.".format(
                        float(claimed_tenure), actual_days
                    )
                )
        except (ValueError, TypeError):
            pass

    return flags


def compute_profile_completeness(
    vision_result,
    voice_result,
    transaction_result,
    document_result,
    vendor_formal_status,
    location_verification=None,
    discrepancy_flags=None,
) -> dict:
    """
    Profile Completeness Index — measures how much evidence was gathered, NOT creditworthiness.
    Score 0-100 based on evidence availability. Higher score = more evidence collected.
    Location is informational only and does not contribute to the score.
    """
    score = 0
    missing_for_next_tier = []

    if vision_result is not None and "error" not in vision_result:
        score += 15
    else:
        missing_for_next_tier.append("Shop photos — add photos to reach Partial tier")

    if voice_result is not None and "error" not in voice_result:
        score += 15
    else:
        missing_for_next_tier.append("Voice note — add voice note to reach Partial tier")

    if transaction_result is not None and "error" not in transaction_result:
        score += 20
    else:
        missing_for_next_tier.append("Transaction records — add transactions to reach Substantial tier")

    has_savings = vendor_formal_status.get("has_savings_account") if vendor_formal_status else None
    if has_savings == "yes" or has_savings == "Yes":
        score += 20
    else:
        missing_for_next_tier.append("Savings account verification — confirm vendor has savings account to reach Substantial tier")

    doc_extracted = document_result.get("extracted", {}) if document_result else {}
    doc_verification = document_result.get("verification_signals", {}) if document_result else {}
    if doc_verification.get("has_gst"):
        score += 10
    else:
        missing_for_next_tier.append("GST certificate — add GST certificate to reach Comprehensive tier")

    if doc_verification.get("has_udyam"):
        score += 10
    else:
        missing_for_next_tier.append("Udyam/MSME certificate — add Udyam certificate to reach Comprehensive tier")

    if doc_verification.get("has_bank_account"):
        score += 10
    else:
        missing_for_next_tier.append("Bank statement — add bank statement to reach Comprehensive tier")

    has_trade_or_rent = doc_verification.get("has_trade_license", False)
    if has_trade_or_rent:
        score += 5

    flags = discrepancy_flags or []
    if not flags:
        score += 5
    else:
        score -= 5

    score = max(0, min(100, score))

    if score <= 30:
        tier = "Minimal"
    elif score <= 60:
        tier = "Partial"
    elif score <= 80:
        tier = "Substantial"
    else:
        tier = "Comprehensive"

    if tier == "Minimal":
        pass
    elif tier == "Partial":
        missing_for_next_tier = [m for m in missing_for_next_tier if "transactions" in m or "Savings account" in m]
    elif tier == "Substantial":
        missing_for_next_tier = [m for m in missing_for_next_tier if "GST" in m or "Udyam" in m or "Bank" in m]

    return {
        "completeness_score": score,
        "completeness_tier": tier,
        "missing_for_next_tier": missing_for_next_tier,
        "label": "Profile Completeness Index — reflects evidence gathered, not creditworthiness",
    }
