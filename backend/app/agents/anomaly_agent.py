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
