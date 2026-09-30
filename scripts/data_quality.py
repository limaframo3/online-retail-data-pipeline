"""
Centralized data quality rules for the Online Retail pipeline.
"""


# =========================================================
# REQUIRED SCHEMA
# =========================================================

REQUIRED_COLUMNS = {
    "invoiceno",
    "stockcode",
    "description",
    "quantity",
    "invoicedate",
    "unitprice",
    "customerid",
    "country",
}


# =========================================================
# COMMERCIAL TRANSACTION RULES
# =========================================================

EXCLUDED_DESCRIPTION_PATTERNS = (
    "POSTAGE",
    "TEST",
    "SAMPLE",
    "ADJUST",
    "DISCOUNT",
    "CHARGES",
    "CARRIAGE",
    "GIFT",
    "MANUAL",
    "UNKNOWN",
    "CHECK",
    "DAMAGED",
)

EXCLUDED_EXACT_DESCRIPTIONS = {
    "?",
}

# =========================================================
# SALES VALIDATION RULES
# =========================================================

MIN_VALID_QUANTITY = 1
MIN_VALID_UNITPRICE = 0
CANCELLATION_INVOICE_PREFIX = "C"

# =========================================================
# DATA QUALITY THRESHOLDS
# =========================================================

DQ_THRESHOLDS = {
    "quantity_positive": 0.30,
    "unitprice_positive": 0.50,
    "invoicedate_not_null": 0.0,
    "invoiceno_not_null": 0.0,
    "stockcode_not_null": 0.0,
    "country_not_null": 0.0,
    "customerid_not_null": 30.0,
}

DQ_CRITICAL_RULES = {
    "invoicedate_not_null",
    "invoiceno_not_null",
    "stockcode_not_null",
}


def evaluate_rule(
    rule_name: str,
    failed_rows: int,
    total_rows: int,
) -> dict:
    """Evaluate one data quality rule against its configured threshold."""

    threshold = DQ_THRESHOLDS[rule_name]

    if total_rows == 0:
        failure_percentage = 0.0
    else:
        failure_percentage = (failed_rows / total_rows) * 100

    status = (
        "PASS"
        if failure_percentage <= threshold
        else "FAIL"
    )

    return {
        "rule": rule_name,
        "failed_rows": failed_rows,
        "failure_percentage": failure_percentage,
        "threshold_percentage": threshold,
        "status": status,
    }


def has_critical_failure(metrics: list[dict]) -> bool:
    """Return True when at least one critical rule has failed."""

    return any(
        metric["status"] == "FAIL"
        and metric["rule"] in DQ_CRITICAL_RULES
        for metric in metrics
    )

def evaluate_rule(
    rule_name: str,
    failed_rows: int,
    total_rows: int,
) -> dict:
    """Evaluate one data quality rule against its configured threshold."""

    threshold = DQ_THRESHOLDS[rule_name]

    if total_rows == 0:
        failure_percentage = 0.0
    else:
        failure_percentage = (failed_rows / total_rows) * 100

    status = (
        "PASS"
        if failure_percentage <= threshold
        else "FAIL"
    )

    return {
        "rule": rule_name,
        "failed_rows": failed_rows,
        "failure_percentage": failure_percentage,
        "threshold_percentage": threshold,
        "status": status,
    }

def has_critical_failure(metrics: list[dict]) -> bool:
    """Return True when at least one critical rule has failed."""

    return any(
        metric["status"] == "FAIL"
        and metric["rule"] in DQ_CRITICAL_RULES
        for metric in metrics
    )