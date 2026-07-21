import os
import sys
import numpy as np
import pandas as pd

from dotenv import load_dotenv
load_dotenv()

DATE_VARIANTS = {"date", "transaction_date", "txn_date", "dt", "timestamp"}
TYPE_VARIANTS = {"type", "transaction_type", "txn_type", "credit_debit", "nature", "debit_credit"}
AMOUNT_VARIANTS_SET = {"amount", "amt", "value", "transaction_amount", "txn_amount", "amount_usd"}
DEBIT_COL_VARIANTS = {"debit", "dr", "debit_amount", "withdrawal", "withdrawals"}
CREDIT_COL_VARIANTS = {"credit", "cr", "credit_amount", "deposit", "deposits"}


def _find_amount_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        lower = col.lower().strip()
        if lower in AMOUNT_VARIANTS_SET:
            return col
    for col in df.columns:
        lower = col.lower().strip()
        if "amount" in lower or "value" in lower:
            return col
    return None


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    lower = {c: c.lower().strip() for c in df.columns}
    df = df.rename(columns=lower)
    for col in df.columns:
        if col in DATE_VARIANTS:
            df = df.rename(columns={col: "date"})
        elif col in TYPE_VARIANTS:
            df = df.rename(columns={col: "type"})
        elif col in DEBIT_COL_VARIANTS:
            df = df.rename(columns={col: "debit"})
        elif col in CREDIT_COL_VARIANTS:
            df = df.rename(columns={col: "credit"})
    # amount is handled separately via _find_amount_col
    return df


def analyze_transactions(csv_path: str) -> dict:
    if not os.path.isfile(csv_path):
        return {"error": "transaction data unavailable"}

    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return {"error": "transaction data unavailable"}

    if df.empty:
        return {"error": "transaction data unavailable"}

    original_cols = list(df.columns)
    df = _normalise_columns(df)

    if "date" not in df.columns:
        print(f"[transaction_agent] no date column found; saw columns: {original_cols}", file=sys.stderr)
        return {"error": "transaction data unavailable"}

    amount_col = _find_amount_col(df)
    if amount_col:
        df = df.rename(columns={amount_col: "amount"})

    has_amount = "amount" in df.columns
    has_type = "type" in df.columns
    has_debit = "debit" in df.columns
    has_credit = "credit" in df.columns

    assumptions = []

    # Separate debit/credit columns → single amount + type
    if has_debit and has_credit and not (has_amount and has_type):
        rows = []
        for _, r in df.iterrows():
            d = pd.to_numeric(r.get("debit", 0), errors="coerce")
            c = pd.to_numeric(r.get("credit", 0), errors="coerce")
            if pd.notna(d) and d > 0:
                rows.append({"date": r["date"], "type": "debit", "amount": d})
            if pd.notna(c) and c > 0:
                rows.append({"date": r["date"], "type": "credit", "amount": c})
        if not rows:
            print(f"[transaction_agent] separate debit/credit columns found but all values were null/zero; saw columns: {original_cols}", file=sys.stderr)
            return {"error": "transaction data unavailable"}
        df = pd.DataFrame(rows)
        has_type = True
    elif has_amount and not has_type and not has_debit and not has_credit:
        # Only amount column — infer direction from sign
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df = df.dropna(subset=["amount"])
        if df.empty:
            return {"error": "transaction data unavailable"}
        has_neg = (df["amount"] < 0).any()
        has_pos = (df["amount"] > 0).any()
        if has_neg and has_pos:
            df["type"] = np.where(df["amount"] >= 0, "credit", "debit")
            df["amount"] = df["amount"].abs()
            has_type = True
        elif has_neg and not has_pos:
            df["type"] = "debit"
            df["amount"] = df["amount"].abs()
            has_type = True
        else:
            assumptions.append("all transactions treated as inflow — no direction indicator found in source data")
    elif not has_amount and not has_debit and not has_credit:
        print(f"[transaction_agent] no amount-like column found; saw columns: {original_cols}", file=sys.stderr)
        return {"error": "transaction data unavailable"}

    if "amount" not in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df = df.dropna(subset=["amount"])

    if df.empty:
        return {"error": "transaction data unavailable"}

    if "type" in df.columns:
        type_col = df["type"].astype(str).str.lower().str.strip()
        inflow = df[type_col.isin({"credit", "cr", "inflow", "deposit"})]["amount"].sum()
        outflow = df[type_col.isin({"debit", "dr", "outflow", "withdrawal"})]["amount"].sum()
    else:
        inflow = float(df["amount"].sum())
        outflow = 0.0

    total_inflow = round(float(inflow), 2)
    total_outflow = round(float(outflow), 2)
    transaction_count = int(len(df))
    avg_txn = round(float(df["amount"].mean()), 2)

    # compute date range
    try:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])
        earliest_date = df["date"].min().strftime("%Y-%m-%d")
        latest_date = df["date"].max().strftime("%Y-%m-%d")
        date_range_days = (df["date"].max() - df["date"].min()).days
    except Exception:
        earliest_date = None
        latest_date = None
        date_range_days = None

    # daily net amounts for volatility
    try:
        daily = df.copy()
        if "type" in df.columns:
            daily["net"] = np.where(type_col.isin({"credit", "cr", "inflow", "deposit"}), daily["amount"], -daily["amount"])
        else:
            daily["net"] = daily["amount"]
        daily_net = daily.groupby(daily["date"].dt.date)["net"].sum()
        cv = float(daily_net.std() / daily_net.mean()) if daily_net.mean() != 0 else 0.0
    except Exception:
        cv = 0.0

    if cv < 0.5:
        volatility = "low"
    elif cv < 1.0:
        volatility = "moderate"
    else:
        volatility = "high"

    # month-over-month trend via linear slope
    try:
        df["month"] = df["date"].dt.to_period("M")
        monthly = df.copy()
        if "type" in df.columns:
            monthly["net"] = np.where(type_col.isin({"credit", "cr", "inflow", "deposit"}), monthly["amount"], -monthly["amount"])
        else:
            monthly["net"] = monthly["amount"]
        monthly_totals = monthly.groupby("month")["net"].sum().reset_index()
        monthly_totals["month_num"] = range(len(monthly_totals))
        if len(monthly_totals) >= 2:
            slope = np.polyfit(monthly_totals["month_num"], monthly_totals["net"], 1)[0]
            if slope > 0.05 * monthly_totals["net"].abs().mean():
                trend = "increasing"
            elif slope < -0.05 * monthly_totals["net"].abs().mean():
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"
    except Exception:
        trend = "stable"

    result = {
        "total_inflow": total_inflow,
        "total_outflow": total_outflow,
        "transaction_count": transaction_count,
        "average_transaction": avg_txn,
        "volatility": volatility,
        "trend": trend,
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "date_range_days": date_range_days,
    }
    if assumptions:
        result["assumptions"] = assumptions
    return result
