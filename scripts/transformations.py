from pathlib import Path
import argparse
import json
import logging
import os

import duckdb

try:
 from .data_quality import (
    EXCLUDED_DESCRIPTION_PATTERNS,
    EXCLUDED_EXACT_DESCRIPTIONS,
    MIN_VALID_QUANTITY,
    MIN_VALID_UNITPRICE,
    CANCELLATION_INVOICE_PREFIX,
)
except ImportError:
    from data_quality import (
        EXCLUDED_DESCRIPTION_PATTERNS,
        EXCLUDED_EXACT_DESCRIPTIONS,
        MIN_VALID_QUANTITY,
        MIN_VALID_UNITPRICE,
        CANCELLATION_INVOICE_PREFIX,
    )


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"


def load_config() -> dict:
    """Load pipeline configuration from config.json."""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as config_file:
        return json.load(config_file)


def get_environment_config(
    config: dict,
    environment: str,
) -> dict:
    """Return configuration for the selected environment."""

    environments = config.get(
        "environments",
        {},
    )

    if environment not in environments:
        raise RuntimeError(
            f"Invalid environment: {environment}"
        )

    return environments[environment]


CONFIG = load_config()

ENVIRONMENT = os.getenv(
    "ONLINE_RETAIL_ENV",
    CONFIG["pipeline"]["environment"],
)

ENV_CONFIG = get_environment_config(
    CONFIG,
    ENVIRONMENT,
)

INPUT_PATH = (
    BASE_DIR
    / ENV_CONFIG["processed_parquet"]
)

DB_PATH = (
    BASE_DIR
    / ENV_CONFIG["staging_database"]
)

LOG_PATH = (
    BASE_DIR
    / CONFIG["paths"]["log"]
)

LOG_LEVEL = ENV_CONFIG["log_level"]


# =========================================================
# LOGGER
# =========================================================

def setup_logger() -> None:
    """Configure logging for the transformation process."""

    LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    log_level = getattr(
        logging,
        LOG_LEVEL.upper(),
        logging.INFO,
    )

    logging.basicConfig(
        filename=str(LOG_PATH),
        level=log_level,
        format=(
            "%(asctime)s - "
            "%(levelname)s - "
            "%(message)s"
        ),
    )


# =========================================================
# LOAD DATA
# =========================================================
def load_raw_data(con):
    """Load cleaned parquet data into DuckDB raw table."""
    logging.info("Loading Parquet into sales_raw")

    con.execute(f"""
    CREATE OR REPLACE TABLE sales_raw AS
    SELECT *
    FROM read_parquet('{str(INPUT_PATH)}');
    """)


# =========================================================
# BASE TABLE
# =========================================================
def create_base_table(con):
    """Create base table with standardized data types."""
    logging.info("Creating sales_base table")

    con.execute("""
    CREATE OR REPLACE TABLE sales_base AS
    SELECT
        CAST(invoiceno AS VARCHAR) AS invoiceno,
        CAST(stockcode AS VARCHAR) AS stockcode,
        COALESCE(NULLIF(TRIM(CAST(description AS VARCHAR)), ''), 'Unknown') AS description,
        TRY_CAST(quantity AS INTEGER) AS quantity,
        TRY_CAST(unitprice AS DECIMAL(12,2)) AS unitprice,
        TRY_CAST(invoicedate AS TIMESTAMP) AS invoicedate,
        COALESCE(NULLIF(TRIM(CAST(customerid AS VARCHAR)), ''), 'N/A') AS customerid,
        COALESCE(NULLIF(TRIM(CAST(country AS VARCHAR)), ''), 'Unknown') AS country
    FROM sales_raw;
    """)


# =========================================================
# VALIDATION
# =========================================================
def validate_nulls(con):
    """Run a basic null check after type casting."""
    logging.info("Running null validation")

    result = con.execute("""
    SELECT
        COUNT(*) AS total_rows,
        SUM(CASE WHEN quantity IS NULL THEN 1 ELSE 0 END) AS null_quantity,
        SUM(CASE WHEN unitprice IS NULL THEN 1 ELSE 0 END) AS null_unitprice,
        SUM(CASE WHEN invoicedate IS NULL THEN 1 ELSE 0 END) AS null_invoicedate
    FROM sales_base;
    """).fetchdf()

    logging.info(f"Null validation:\n{result}")


# =========================================================
# TIME TABLE
# =========================================================
def create_time_table(con):
    """Create time staging table from invoice date."""
    logging.info("Creating stg_time")

    con.execute("""
    CREATE OR REPLACE TABLE stg_time AS
    SELECT DISTINCT
        CAST(invoicedate AS DATE) AS invoice_date,
        YEAR(invoicedate) AS invoice_year,
        QUARTER(invoicedate) AS invoice_quarter,
        MONTH(invoicedate) AS invoice_month,
        MONTHNAME(invoicedate) AS month_name,
        WEEK(invoicedate) AS invoice_week,
        DAY(invoicedate) AS invoice_day,
        DAYNAME(invoicedate) AS day_name,
        HOUR(invoicedate) AS invoice_hour
    FROM sales_base
    WHERE invoicedate IS NOT NULL;
    """)

def build_description_exclusion_sql() -> str:
    """Build SQL conditions for excluded commercial descriptions."""

    pattern_conditions = [
        f"UPPER(description) LIKE '%{pattern}%'"
        for pattern in EXCLUDED_DESCRIPTION_PATTERNS
    ]

    exact_conditions = [
        f"TRIM(description) = '{value}'"
        for value in EXCLUDED_EXACT_DESCRIPTIONS
    ]

    return "\n            OR ".join(
        pattern_conditions + exact_conditions
    )


# =========================================================
# SALES STAGING
# =========================================================

def create_sales_staging(con):
    """Create sales staging table with valid commercial transactions only."""
    logging.info("Creating sales_staging")

    description_exclusions = build_description_exclusion_sql()

    con.execute(f"""
    CREATE OR REPLACE TABLE sales_staging AS
    SELECT
        invoiceno,
        stockcode,
        description,
        quantity,
        unitprice,
        invoicedate,
        customerid,
        country,
        CAST(quantity * unitprice AS DECIMAL(14,2)) AS total_venta
    FROM sales_base
    WHERE quantity >= {MIN_VALID_QUANTITY}
    AND unitprice > {MIN_VALID_UNITPRICE}
    AND invoicedate IS NOT NULL
    AND invoiceno NOT LIKE '{CANCELLATION_INVOICE_PREFIX}%'
    AND NOT (
            {description_exclusions}
        );
    """)

# =========================================================
# COMMAND LINE ARGUMENTS
# =========================================================

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Run Online Retail transformations."
    )

    parser.add_argument(
        "--run-id",
        required=False,
        default=None,
        help="Global pipeline execution identifier.",
    )

    return parser.parse_args()


# =========================================================
# MAIN
# =========================================================

def main():
    """Execute DuckDB transformation workflow."""

    args = parse_args()

    setup_logger()
    logging.info(
        "Starting transformations - run_id=%s",
        args.run_id,
    )

    con = None

    try:
        con = duckdb.connect(str(DB_PATH))

        load_raw_data(con)
        create_base_table(con)
        validate_nulls(con)
        create_time_table(con)
        create_sales_staging(con)

        logging.info("Pipeline completed successfully")

    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        raise

    finally:
        if con:
            con.close()


if __name__ == "__main__":
    main()