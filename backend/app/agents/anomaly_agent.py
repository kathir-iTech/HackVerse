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
    """
    score = 0
    missing_for_next_tier = []

    # Photos (+15)
    if vision_result is not None and "error" not in vision_result:
        score += 15
    else:
        missing_for_next_tier.append("Shop photos — add photos to reach Partial tier")

    # Voice note (+15)
    if voice_result is not None and "error" not in voice_result:
        score += 15
    else:
        missing_for_next_tier.append("Voice note — add voice note to reach Partial tier")

    # Transaction records (+20)
    if transaction_result is not None and "error" not in transaction_result:
        score += 20
    else:
        missing_for_next_tier.append("Transaction records — add transactions to reach Substantial tier")

    # Vendor has savings account (+20)
    has_savings = vendor_formal_status.get("has_savings_account") if vendor_formal_status else None
    if has_savings == "yes" or has_savings == "Yes":
        score += 20
    else:
        missing_for_next_tier.append("Savings account verification — confirm vendor has savings account to reach Substantial tier")

    # GST certificate (+10)
    doc_extracted = document_result.get("extracted", {}) if document_result else {}
    if document_result and document_result.get("verification_signals", {}).get("has_gst"):
        score += 10
    else:
        missing_for_next_tier.append("GST certificate — add GST certificate to reach Comprehensive tier")

    # Udyam certificate (+10)
    if document_result and document_result.get("verification_signals", {}).get("has_udyam"):
        score += 10
    else:
        missing_for_next_tier.append("Udyam/MSME certificate — add Udyam certificate to reach Comprehensive tier")

    # Bank statement (+10)
    if document_result and document_result.get("verification_signals", {}).get("has_bank_account"):
        score += 10
    else:
        missing_for_next_tier.append("Bank statement — add bank statement to reach Comprehensive tier")

    # Trade license or rent agreement (+5, capped)
    doc_verification = document_result.get("verification_signals", {}) if document_result else {}
    has_trade_or_rent = doc_verification.get("has_trade_license", False)
    if has_trade_or_rent:
        score += 5

    # Location verified (+5)
    if location_verification and location_verification.get("location_found"):
        score += 5
    else:
        missing_for_next_tier.append("Location verification — pin location to reach Comprehensive tier")

    # Discrepancy bonus/penalty (±5)
    flags = discrepancy_flags or []
    if not flags:
        score += 5
    else:
        score -= 5

    # Cap score at 0-100
    score = max(0, min(100, score))

    # Determine tier
    if score <= 30:
        tier = "Minimal"
    elif score <= 60:
        tier = "Partial"
    elif score <= 80:
        tier = "Substantial"
    else:
        tier = "Comprehensive"

    # Compute missing_for_next_tier for current tier
    if tier == "Minimal":
        pass
    elif tier == "Partial":
        missing_for_next_tier = [m for m in missing_for_next_tier if "transactions" in m or "Savings account" in m or "location" in m.lower()]
    elif tier == "Substantial":
        missing_for_next_tier = [m for m in missing_for_next_tier if "GST" in m or "Udyam" in m or "Bank" in m or "location" in m.lower()]

    return {
        "completeness_score": score,
        "completeness_tier": tier,
        "missing_for_next_tier": missing_for_next_tier,
        "label": "Profile Completeness Index — reflects evidence gathered, not creditworthiness",
    }
