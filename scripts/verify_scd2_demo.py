"""Verify the controlled SCD Type 2 product changes in DuckDB.

Run this script after the second pipeline execution:

    python scripts/verify_scd2_demo.py

The command prints the product history created by the SCD2 demo and exits
with status 1 when any validation fails.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb


# =========================================================
# CONFIGURATION
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
DEFAULT_DW_PATH = BASE_DIR / "db" / "DW_Online_Retail.db"
LOG_PATH = BASE_DIR / "logs" / "scd2_verification.log"

DEMO_INVOICE_PREFIX = "SCD2DEMO"
DEMO_DESCRIPTION_SUFFIX = " [SCD2 DEMO UPDATE]"
DEFAULT_EXPECTED_PRODUCTS = 2

REQUIRED_COLUMNS = {
    "dim_product": {
        "product_key",
        "stockcode",
        "description",
        "effective_from",
        "effective_to",
        "is_current",
    },
    "fact_sales": {
        "product_key",
        "stockcode",
        "invoiceno",
        "invoicedate",
    },
}


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description="Verify the SCD Type 2 demo results in DuckDB."
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="Optional path to DW_Online_Retail.db.",
    )
    parser.add_argument(
        "--expected-products",
        type=int,
        default=DEFAULT_EXPECTED_PRODUCTS,
        help="Minimum number of demo products expected (default: 2).",
    )
    return parser.parse_args()


def setup_logger() -> None:
    """Configure the verification log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def load_database_path(argument_path: Path | None) -> Path:
    """Resolve the Data Warehouse path from CLI, config, or the default."""
    if argument_path is not None:
        return (
            argument_path
            if argument_path.is_absolute()
            else BASE_DIR / argument_path
        )

    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config: dict[str, Any] = json.load(config_file)

        configured_path = config.get("paths", {}).get("database")
        if configured_path:
            path = Path(configured_path)
            return path if path.is_absolute() else BASE_DIR / path

    return DEFAULT_DW_PATH


def validate_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Validate that the required tables and columns exist."""
    table_names = {
        row[0]
        for row in connection.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main';
        """).fetchall()
    }

    missing_tables = set(REQUIRED_COLUMNS) - table_names
    if missing_tables:
        raise RuntimeError(
            "Missing required DW tables: "
            + ", ".join(sorted(missing_tables))
        )

    for table_name, required_columns in REQUIRED_COLUMNS.items():
        actual_columns = {
            row[1]
            for row in connection.execute(
                f"PRAGMA table_info('{table_name}');"
            ).fetchall()
        }
        missing_columns = required_columns - actual_columns
        if missing_columns:
            raise RuntimeError(
                f"Table {table_name} is missing columns: "
                + ", ".join(sorted(missing_columns))
            )


def load_demo_facts(
    connection: duckdb.DuckDBPyConnection,
) -> list[tuple[Any, ...]]:
    """Return demo facts and their assigned product-version attributes."""
    return connection.execute("""
        SELECT
            fact.stockcode,
            fact.invoiceno,
            fact.invoicedate,
            fact.product_key,
            product.product_key AS matched_product_key,
            product.description,
            product.effective_from,
            product.effective_to,
            product.is_current
        FROM fact_sales AS fact
        LEFT JOIN dim_product AS product
            ON fact.product_key = product.product_key
        WHERE fact.invoiceno LIKE ?
        ORDER BY fact.stockcode, fact.invoicedate;
    """, [f"{DEMO_INVOICE_PREFIX}%"]).fetchall()


def load_demo_history(
    connection: duckdb.DuckDBPyConnection,
) -> list[tuple[Any, ...]]:
    """Return all product versions belonging to demo products."""
    return connection.execute("""
        WITH demo_products AS (
            SELECT DISTINCT stockcode
            FROM fact_sales
            WHERE invoiceno LIKE ?
        )
        SELECT
            product.product_key,
            product.stockcode,
            product.description,
            product.effective_from,
            product.effective_to,
            product.is_current
        FROM dim_product AS product
        INNER JOIN demo_products AS demo
            ON product.stockcode = demo.stockcode
        ORDER BY product.stockcode, product.effective_from;
    """, [f"{DEMO_INVOICE_PREFIX}%"]).fetchall()


def validate_demo(
    demo_facts: list[tuple[Any, ...]],
    demo_history: list[tuple[Any, ...]],
    expected_products: int,
) -> list[str]:
    """Return all detected SCD2 validation failures."""
    failures: list[str] = []

    if expected_products < 1:
        failures.append("expected-products must be at least 1")
        return failures

    if not demo_facts:
        failures.append(
            f"No facts with invoice prefix '{DEMO_INVOICE_PREFIX}' were found"
        )
        return failures

    fact_products = {str(row[0]) for row in demo_facts}
    if len(fact_products) < expected_products:
        failures.append(
            f"Expected at least {expected_products} demo products, "
            f"but found {len(fact_products)}"
        )

    facts_by_product: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in demo_facts:
        facts_by_product[str(row[0])].append(row)

        if row[4] is None:
            failures.append(
                f"Demo fact {row[1]} / {row[0]} has an orphan product_key"
            )
            continue

        if row[3] != row[4]:
            failures.append(
                f"Demo fact {row[1]} / {row[0]} has a product-key mismatch"
            )

        if row[2] < row[6] or (row[7] is not None and row[2] >= row[7]):
            failures.append(
                f"Demo fact {row[1]} / {row[0]} is outside its "
                "product-version validity period"
            )

    history_by_product: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in demo_history:
        history_by_product[str(row[1])].append(row)

    for stockcode in sorted(fact_products):
        versions = history_by_product.get(stockcode, [])
        if len(versions) < 2:
            failures.append(
                f"Product {stockcode} has {len(versions)} version(s); "
                "at least 2 are required"
            )
            continue

        current_versions = [row for row in versions if row[5] is True]
        if len(current_versions) != 1:
            failures.append(
                f"Product {stockcode} has {len(current_versions)} current "
                "versions; exactly 1 is required"
            )
            continue

        current = current_versions[0]
        if current != versions[-1]:
            failures.append(
                f"Product {stockcode} current version is not the latest one"
            )

        if current[4] is not None:
            failures.append(
                f"Product {stockcode} current version has effective_to"
            )

        if not str(current[2]).endswith(DEMO_DESCRIPTION_SUFFIX):
            failures.append(
                f"Product {stockcode} current description does not contain "
                "the SCD2 demo suffix"
            )

        previous = versions[-2]
        if previous[4] != current[3]:
            failures.append(
                f"Product {stockcode} previous effective_to does not match "
                "the current effective_from"
            )

        if previous[5] is not False:
            failures.append(
                f"Product {stockcode} previous version is still current"
            )

        if previous[2] == current[2]:
            failures.append(
                f"Product {stockcode} description did not change"
            )

        first_demo_date = min(row[2] for row in facts_by_product[stockcode])
        if current[3] != first_demo_date:
            failures.append(
                f"Product {stockcode} current effective_from does not match "
                "the first demo transaction date"
            )

        for fact in facts_by_product[stockcode]:
            if fact[3] != current[0]:
                failures.append(
                    f"Demo fact {fact[1]} / {stockcode} does not reference "
                    "the current demo product version"
                )

    return failures


def print_report(
    demo_facts: list[tuple[Any, ...]],
    demo_history: list[tuple[Any, ...]],
    failures: list[str],
) -> None:
    """Print a recruiter-friendly SCD2 verification report."""
    products = {str(row[0]) for row in demo_facts}
    invoices = {str(row[1]) for row in demo_facts}

    print("\n" + "=" * 90)
    print("SCD TYPE 2 DEMO VERIFICATION — DIM_PRODUCT")
    print("=" * 90)
    print(f"Demo invoices:           {len(invoices):,}")
    print(f"Demo products:           {len(products):,}")
    print(f"Demo fact rows:          {len(demo_facts):,}")
    print(f"Product history rows:    {len(demo_history):,}")
    print(f"Validation failures:     {len(failures):,}")
    print(f"Validation status:       {'PASSED' if not failures else 'FAILED'}")

    print("-" * 90)
    print("DEMO PRODUCT VERSION HISTORY")
    print("-" * 90)
    for row in demo_history:
        status = "CURRENT" if row[5] else "HISTORICAL"
        effective_to = row[4] if row[4] is not None else "OPEN"
        print(
            f"Key: {row[0]} | Stock: {row[1]} | {status} | "
            f"From: {row[3]} | To: {effective_to}"
        )
        print(f"Description: {row[2]}")

    if failures:
        print("-" * 90)
        print("VALIDATION FAILURES")
        print("-" * 90)
        for failure in failures:
            print(f"- {failure}")

    print("=" * 90)
    print(f"Log file: {LOG_PATH}")


def main() -> None:
    """Execute the SCD2 demo verification."""
    setup_logger()
    args = parse_args()
    database_path = load_database_path(args.database)

    logging.info("=" * 78)
    logging.info("Starting SCD2 demo verification")
    logging.info("Data Warehouse: %s", database_path)

    if not database_path.exists():
        raise FileNotFoundError(
            f"Data Warehouse database not found: {database_path}"
        )

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        validate_schema(connection)
        demo_facts = load_demo_facts(connection)
        demo_history = load_demo_history(connection)
        failures = validate_demo(
            demo_facts=demo_facts,
            demo_history=demo_history,
            expected_products=args.expected_products,
        )
    finally:
        connection.close()

    print_report(demo_facts, demo_history, failures)

    logging.info(
        "SCD2 verification completed. Demo facts: %s, demo history rows: %s, "
        "failures: %s, status: %s",
        len(demo_facts),
        len(demo_history),
        len(failures),
        "PASSED" if not failures else "FAILED",
    )

    if failures:
        raise RuntimeError(
            "SCD Type 2 demo verification failed. Review the report above "
            "and logs/scd2_verification.log."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        logging.exception("SCD2 demo verification failed: %s", error)
        print(f"\nVerification error: {error}", file=sys.stderr)
        print(f"Review the log file: {LOG_PATH}", file=sys.stderr)
        sys.exit(1)
