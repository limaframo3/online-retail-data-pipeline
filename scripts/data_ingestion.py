from pathlib import Path
import argparse
import json
import logging
import os

import duckdb
import pandas as pd
import pycountry


try:
    from .data_quality import (
            CANCELLATION_INVOICE_PREFIX,
            DQ_CRITICAL_RULES,
            MIN_VALID_QUANTITY,
            MIN_VALID_UNITPRICE,
            REQUIRED_COLUMNS,
            evaluate_rule,
            has_critical_failure,
        )
except ImportError:
    from data_quality import (
            CANCELLATION_INVOICE_PREFIX,
            DQ_CRITICAL_RULES,
            MIN_VALID_QUANTITY,
            MIN_VALID_UNITPRICE,
            REQUIRED_COLUMNS,
            evaluate_rule,
            has_critical_failure,
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

EXCEL_PATH = BASE_DIR / CONFIG["paths"]["excel"]

RAW_PARQUET_PATH = (
    BASE_DIR
    / CONFIG["paths"]["raw_parquet"]
)

PROCESSED_PARQUET_PATH = (
    BASE_DIR
    / ENV_CONFIG["processed_parquet"]
)

QUARANTINE_PARQUET_PATH = (
    BASE_DIR
    / ENV_CONFIG["quarantine_parquet"]
)

LOG_PATH = BASE_DIR / CONFIG["paths"]["log"]

DW_DB_PATH = (
    BASE_DIR
    / ENV_CONFIG["database"]
)

LOG_LEVEL = ENV_CONFIG["log_level"]


# =========================================================
# LOGGER
# =========================================================

def setup_logger() -> None:
    """Configure logging for the ingestion process."""


    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE_PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)

    DW_DB_PATH.parent.mkdir(
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
# EXTRACT
# =========================================================

def load_data(excel_path: Path, parquet_output_path: Path) -> pd.DataFrame:
    """
    Load Online Retail Excel dataset,
    convert it to raw Parquet,
    and return the Parquet DataFrame.
    """

    logging.info(f"Reading Excel file: {excel_path}")

    # Read source Excel file
    df = pd.read_excel(
        excel_path,
        dtype={
            "InvoiceNo": "string",
            "StockCode": "string",
            "Description": "string",
            "Country": "string"
        }
    )

    logging.info("Excel file loaded successfully.")

    # Export raw dataset to Parquet
    df.to_parquet(
        parquet_output_path,
        index=False,
        engine="pyarrow"
    )

    logging.info(f"Raw Parquet created at: {parquet_output_path}")

    # Read raw Parquet file
    df = pd.read_parquet(
        parquet_output_path,
        engine="pyarrow"
    )

    logging.info("Raw Parquet loaded successfully.")

    return df

# =========================================================
# TRANSFORM
# =========================================================
def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names."""
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    return df


def validate_schema(df: pd.DataFrame) -> None:
    """Validate that the dataset contains all required columns."""

    actual_columns = set(df.columns)
    missing_columns = REQUIRED_COLUMNS - actual_columns
    unexpected_columns = actual_columns - REQUIRED_COLUMNS

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        logging.error(f"Schema validation failed. Missing columns: {missing}")
        raise ValueError(
            f"Schema validation failed. Missing required columns: {missing}"
        )

    if unexpected_columns:
        unexpected = ", ".join(sorted(unexpected_columns))
        logging.warning(
            f"Schema validation warning. Unexpected columns: {unexpected}"
        )

    logging.info("Schema contract validation passed.")


def trim_text_values(df: pd.DataFrame) -> pd.DataFrame:
    """Remove leading and trailing spaces from text columns."""
    df = df.copy()

    for col in df.columns:
        if df[col].dtype == "object" or str(df[col].dtype).startswith("string"):
            df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

    return df


def normalize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and standardize selected text columns."""
    df = df.copy()

    text_cols = ["invoiceno", "stockcode", "description", "country"]

    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype("string")
            df[col] = df[col].str.strip()
            df[col] = df[col].str.replace(r"\s+", " ", regex=True)
            df[col] = df[col].fillna("N/A")

    if "description" in df.columns:
        df["description"] = df["description"].str.title()

    return df


def standardize_country(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize country values and remove invalid entries."""
    df = df.copy()
    invalid = ["unspecified", "european community", "channel islands"]

    def normalize_country(country):
        try:
            return pycountry.countries.lookup(str(country)).name
        except Exception:
            return country

    if "country" in df.columns:
        df["country"] = df["country"].apply(normalize_country)
        df["country"] = df["country"].astype("string").str.strip()
        df = df[~df["country"].str.lower().isin(invalid)]
        df["country"] = df["country"].fillna("N/A").str.title()

    return df


def convert_data_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert core columns to expected data types."""
    df = df.copy()

    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")

    if "unitprice" in df.columns:
        df["unitprice"] = pd.to_numeric(df["unitprice"], errors="coerce")

    if "customerid" in df.columns:
        df["customerid"] = (
            pd.to_numeric(df["customerid"], errors="coerce")
            .astype("Int64")
            .astype("string")
            .fillna("N/A")
        )

    if "invoicedate" in df.columns:
        df["invoicedate"] = pd.to_datetime(df["invoicedate"], errors="coerce")

    return df

def split_valid_and_quarantine(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split technically valid records from records
    that must be sent to quarantine.
    """

    df = df.copy()

    invalid_mask = (
        df["quantity"].isna()
        | df["unitprice"].isna()
        | df["invoicedate"].isna()
    )

    quarantine_df = df[invalid_mask].copy()
    valid_df = df[~invalid_mask].copy()

    logging.info(f"Valid records: {len(valid_df):,}")
    logging.info(f"Quarantined records: {len(quarantine_df):,}")

    return valid_df, quarantine_df


def remove_exact_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove fully duplicated rows."""
    df = df.copy()
    return df.drop_duplicates()


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Reorder columns for a cleaner final dataset."""
    preferred_order = [
        "invoiceno",
        "stockcode",
        "description",
        "quantity",
        "unitprice",
        "invoicedate",
        "customerid",
        "country",
    ]

    existing_cols = [col for col in preferred_order if col in df.columns]
    remaining_cols = [col for col in df.columns if col not in existing_cols]

    return df[existing_cols + remaining_cols]

def calculate_data_quality_metrics(
    df: pd.DataFrame,
) -> list[dict]:
    """Calculate production-style data quality metrics."""

    total_rows = len(df)

    quantity = pd.to_numeric(
        df["quantity"],
        errors="coerce",
    )

    unitprice = pd.to_numeric(
        df["unitprice"],
        errors="coerce",
    )

    invoicedate = pd.to_datetime(
        df["invoicedate"],
        errors="coerce",
    )

    invoiceno = df["invoiceno"].astype("string")

    cancellation_mask = invoiceno.str.startswith(
        CANCELLATION_INVOICE_PREFIX,
        na=False,
    )

    quantity_failures = (
        quantity.isna()
        | (
            (quantity < MIN_VALID_QUANTITY)
            & ~cancellation_mask
        )
    ).sum()

    unitprice_failures = (
        unitprice.isna()
        | (unitprice <= MIN_VALID_UNITPRICE)
    ).sum()

    def missing_text(column: str) -> int:
        series = df[column].astype("string")

        return int(
            (
                series.isna()
                | series.str.strip().eq("")
            ).sum()
        )

    metrics = [
        evaluate_rule(
            "quantity_positive",
            int(quantity_failures),
            total_rows,
        ),
        evaluate_rule(
            "unitprice_positive",
            int(unitprice_failures),
            total_rows,
        ),
        evaluate_rule(
            "invoicedate_not_null",
            int(invoicedate.isna().sum()),
            total_rows,
        ),
        evaluate_rule(
            "invoiceno_not_null",
            missing_text("invoiceno"),
            total_rows,
        ),
        evaluate_rule(
            "stockcode_not_null",
            missing_text("stockcode"),
            total_rows,
        ),
        evaluate_rule(
            "country_not_null",
            missing_text("country"),
            total_rows,
        ),
        evaluate_rule(
            "customerid_not_null",
            missing_text("customerid"),
            total_rows,
        ),
    ]

    return metrics


def log_quality_metrics(metrics: list[dict]) -> None:
    """Write data quality rule metrics to the pipeline log."""

    logging.info("Data Quality rule metrics:")

    for metric in metrics:
        logging.info(
            "Rule=%s | Failed rows=%s | "
            "Failure percentage=%.4f%% | "
            "Threshold=%.4f%% | Status=%s",
            metric["rule"],
            metric["failed_rows"],
            metric["failure_percentage"],
            metric["threshold_percentage"],
            metric["status"],
        )


def save_quality_metrics(
    metrics: list[dict],
    run_id: str | None,
) -> None:
    """Persist data quality metrics in the warehouse database."""

    if not run_id:
        logging.warning(
            "Data quality metrics were not persisted because run_id is missing."
        )
        return

    con = duckdb.connect(str(DW_DB_PATH))

    try:
        con.execute("""
            
        CREATE TABLE IF NOT EXISTS data_quality_metrics (
        run_id VARCHAR NOT NULL,
        rule VARCHAR NOT NULL,
        failed_rows BIGINT NOT NULL,
        failure_percentage DOUBLE NOT NULL,
        threshold_percentage DOUBLE NOT NULL,
        status VARCHAR NOT NULL,
        executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (run_id, rule)
        );
        """)


        records = [
            (
                run_id,
                metric["rule"],
                int(metric["failed_rows"]),
                float(metric["failure_percentage"]),
                float(metric["threshold_percentage"]),
                metric["status"],
            )
            for metric in metrics
        ]

        con.execute(
            """
            DELETE FROM data_quality_metrics
            WHERE run_id = ?;
            """,
            [run_id],
        )

        con.executemany(
            """
            INSERT INTO data_quality_metrics (
                run_id,
                rule,
                failed_rows,
                failure_percentage,
                threshold_percentage,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            records,
        )

        logging.info(
            "Persisted %s data quality metrics for run_id=%s",
            len(records),
            run_id,
        )

    finally:
        con.close()

def enforce_quality_gate(metrics: list[dict]) -> None:
    """Stop the pipeline when a critical data quality rule fails."""

    if not has_critical_failure(metrics):
        return

    failed_critical_rules = [
        metric["rule"]
        for metric in metrics
        if metric["status"] == "FAIL"
        and metric["rule"] in DQ_CRITICAL_RULES
    ]

    raise RuntimeError(
        "Critical data quality rules failed: "
        + ", ".join(failed_critical_rules)
    )

# =========================================================
# VALIDATION
# =========================================================
def log_data_quality(df: pd.DataFrame) -> None:
    """Log a concise data quality summary."""
    logging.info("Generating data quality summary")
    logging.info(f"Rows: {len(df):,}")
    logging.info(f"Columns: {df.shape[1]}")
    logging.info(f"Data types:\n{df.dtypes}")
    logging.info(f"Missing values:\n{df.isna().sum()}")
    logging.info(f"Exact duplicates: {df.duplicated().sum()}")

    if "quantity" in df.columns:
        logging.info(f"Negative quantity rows: {int((df['quantity'] < 0).sum())}")
        logging.info(f"Zero quantity rows: {int((df['quantity'] == 0).sum())}")

    if "unitprice" in df.columns:
        logging.info(f"Negative unitprice rows: {int((df['unitprice'] < 0).sum())}")
        logging.info(f"Zero unitprice rows: {int((df['unitprice'] == 0).sum())}")

    if "country" in df.columns:
        logging.info(f"Unique countries: {df['country'].nunique(dropna=False)}")


# =========================================================
# LOAD
# =========================================================

def save_data(df: pd.DataFrame, output_path: Path) -> None:
    """Save cleaned dataset to Parquet."""
    df.to_parquet(
        output_path,
        index=False,
        engine="pyarrow"
    )
    logging.info(f"Cleaned Parquet saved to: {output_path}")

def save_quarantine(df: pd.DataFrame, output_path: Path) -> None:
    """Save quarantined records to Parquet."""

    if df.empty:
        if output_path.exists():
            output_path.unlink()
            logging.info(f"Previous quarantine file removed: {output_path}")

        logging.info("No quarantined records found.")
        return

    df.to_parquet(
        output_path,
        index=False,
        engine="pyarrow"
    )

    logging.info(f"Quarantine Parquet saved to: {output_path}")

# =========================================================
# COMMAND LINE ARGUMENTS
# =========================================================

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for ingestion."""

    parser = argparse.ArgumentParser(
        description="Run Online Retail ingestion."
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
def main() -> None:
    """Execute ingestion and cleaning workflow."""

    args = parse_args()
    setup_logger()
    logging.info(
        "Starting ingestion pipeline - run_id=%s",
        args.run_id,
    )

    try:
        df = load_data(EXCEL_PATH, RAW_PARQUET_PATH)
        df = standardize_column_names(df)
        validate_schema(df)
        df = trim_text_values(df)

        quality_metrics = calculate_data_quality_metrics(df)
        log_quality_metrics(quality_metrics)

        save_quality_metrics(
            quality_metrics,
            args.run_id,
        )

        enforce_quality_gate(quality_metrics)

        df = normalize_text_columns(df)
        df = standardize_country(df)
        df = convert_data_types(df)
        df, quarantine_df = split_valid_and_quarantine(df)
        df = remove_exact_duplicates(df)
        df = reorder_columns(df)

        log_data_quality(df)
        save_quarantine(quarantine_df, QUARANTINE_PARQUET_PATH)
        save_data(df, PROCESSED_PARQUET_PATH)

        logging.info("Ingestion pipeline completed successfully")

    except Exception as e:
        logging.error(f"Ingestion pipeline failed: {e}")
        raise

if __name__ == "__main__":
    main()