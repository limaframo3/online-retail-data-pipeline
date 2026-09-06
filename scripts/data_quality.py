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