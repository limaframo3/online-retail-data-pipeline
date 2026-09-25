from pathlib import Path
import json
import logging
import subprocess
import sys
import time
import argparse
import duckdb


# =========================================================
# CONFIGURATION
# =========================================================
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
SCRIPTS_DIR = BASE_DIR / "scripts"
DW_DB_PATH = BASE_DIR / "db" / "DW_Online_Retail.db"


def load_config() -> dict:
    """Load pipeline configuration from config.json."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


CONFIG = load_config()

LOG_PATH = BASE_DIR / CONFIG["paths"]["log"]
PIPELINE_VERSION = CONFIG["pipeline"]["version"]
ENVIRONMENT = CONFIG["pipeline"]["environment"]


PIPELINE_STEPS = [
    {
        "stage": "ingestion",
        "name": "Data Ingestion",
        "script": SCRIPTS_DIR / "data_ingestion.py",
    },
    {
        "stage": "transformation",
        "name": "Data Transformation",
        "script": SCRIPTS_DIR / "transformations.py",
    },
    {
        "stage": "warehouse",
        "name": "Build Data Warehouse",
        "script": SCRIPTS_DIR / "build_datawarehouse.py",
    },
    {
        "stage": "report",
        "name": "Generate Report",
        "script": SCRIPTS_DIR / "generate_report.py",
    },
]

# =========================================================
# COMMAND LINE ARGUMENTS
# =========================================================
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the pipeline."""

    parser = argparse.ArgumentParser(
        description="Run the Online Retail data pipeline."
    )

    parser.add_argument(
        "--stage",
        choices=[
            "all",
            "ingestion",
            "transformation",
            "warehouse",
            "report",
        ],
        default="all",
        help="Pipeline stage to execute. Default: all.",
    )

    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        default="full",
        help="Pipeline load mode. Default: full.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which pipeline steps would run without executing them.",
    )

    return parser.parse_args()

# =========================================================
# LOGGER
# =========================================================
def setup_logger() -> None:
    """Configure pipeline logging."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


# =========================================================
# PIPELINE EXECUTION
# =========================================================
def run_step(step_name: str, script_path: Path) -> None:
    """Run one pipeline step using a Python subprocess."""
    if not script_path.exists():
        raise FileNotFoundError(
            f"Script not found: {script_path}"
        )

    print("\n" + "=" * 70)
    print(f"STARTING STEP — {step_name}")
    print("=" * 70)

    logging.info("=" * 70)
    logging.info("Starting step: %s", step_name)
    logging.info("Running script: %s", script_path)

    start_time = time.perf_counter()

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        check=False,
    )

    duration = time.perf_counter() - start_time

    if result.stdout:
        logging.info(
            "%s stdout:\n%s",
            step_name,
            result.stdout.strip(),
        )

    if result.stderr:
        if result.returncode == 0:
            logging.warning(
                "%s stderr:\n%s",
                step_name,
                result.stderr.strip(),
            )
        else:
            logging.error(
                "%s stderr:\n%s",
                step_name,
                result.stderr.strip(),
            )

    if result.returncode != 0:
        print(f"FAILED — {step_name}")

        if result.stderr:
            print(result.stderr.strip())

        logging.error("Step failed: %s", step_name)
        logging.error(
            "Execution time before failure: %.2f seconds",
            duration,
        )

        raise RuntimeError(
            f"Pipeline stopped because '{step_name}' failed "
            f"with exit code {result.returncode}."
        )

    print(f"COMPLETED — {step_name} ({duration:.2f} seconds)")

    logging.info(
        "Step completed successfully: %s",
        step_name,
    )
    logging.info(
        "Execution time: %.2f seconds",
        duration,
    )


# =========================================================
# SCD TYPE 2 VALIDATION
# =========================================================
def display_scd2_summary() -> None:
    """
    Validate and display the SCD Type 2 implementation
    stored in dim_product.
    """
    if not DW_DB_PATH.exists():
        raise FileNotFoundError(
            f"Data Warehouse database not found: {DW_DB_PATH}"
        )

    connection = duckdb.connect(
        str(DW_DB_PATH),
        read_only=True,
    )

    try:
        table_exists = connection.execute("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = 'dim_product';
        """).fetchone()[0]

        if table_exists == 0:
            raise RuntimeError(
                "Table 'dim_product' was not found in the Data Warehouse."
            )

        metrics = connection.execute("""
            SELECT
                COUNT(DISTINCT stockcode) AS unique_products,
                COUNT(*) AS total_versions,
                COUNT(*) FILTER (
                    WHERE is_current = FALSE
                ) AS historical_versions,
                COUNT(DISTINCT stockcode) FILTER (
                    WHERE is_current = FALSE
                ) AS products_with_history
            FROM dim_product;
        """).fetchone()

        invalid_current_versions = connection.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT
                    stockcode
                FROM dim_product
                GROUP BY stockcode
                HAVING COUNT(*) FILTER (
                    WHERE is_current = TRUE
                ) <> 1
            ) AS invalid_products;
        """).fetchone()[0]

        invalid_periods = connection.execute("""
            SELECT COUNT(*)
            FROM dim_product
            WHERE effective_to IS NOT NULL
              AND effective_to <= effective_from;
        """).fetchone()[0]

        invalid_version_boundaries = connection.execute("""
            WITH ordered_versions AS (
                SELECT
                    stockcode,
                    effective_from,
                    effective_to,
                    LEAD(effective_from) OVER (
                        PARTITION BY stockcode
                        ORDER BY effective_from
                    ) AS next_effective_from
                FROM dim_product
            )
            SELECT COUNT(*)
            FROM ordered_versions
            WHERE (
                next_effective_from IS NOT NULL
                AND (
                    effective_to IS NULL
                    OR effective_to <> next_effective_from
                )
            )
            OR (
                next_effective_from IS NULL
                AND effective_to IS NOT NULL
            );
        """).fetchone()[0]

        duplicate_versions = connection.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT
                    stockcode,
                    effective_from
                FROM dim_product
                GROUP BY
                    stockcode,
                    effective_from
                HAVING COUNT(*) > 1
            ) AS duplicated_business_versions;
        """).fetchone()[0]

        null_scd2_values = connection.execute("""
            SELECT COUNT(*)
            FROM dim_product
            WHERE stockcode IS NULL
               OR effective_from IS NULL
               OR is_current IS NULL;
        """).fetchone()[0]

        validation_passed = (
            invalid_current_versions == 0
            and invalid_periods == 0
            and invalid_version_boundaries == 0
            and duplicate_versions == 0
            and null_scd2_values == 0
        )

        print("\n" + "=" * 75)
        print("SCD TYPE 2 VALIDATION — DIM_PRODUCT")
        print("=" * 75)
        print(f"Unique products:             {metrics[0]:,}")
        print(f"Total product versions:      {metrics[1]:,}")
        print(f"Historical versions:         {metrics[2]:,}")
        print(f"Products with history:       {metrics[3]:,}")
        print(f"Invalid current versions:    {invalid_current_versions:,}")
        print(f"Invalid validity periods:    {invalid_periods:,}")
        print(f"Invalid version boundaries:  {invalid_version_boundaries:,}")
        print(f"Duplicate business versions: {duplicate_versions:,}")
        print(f"Null SCD2 values:             {null_scd2_values:,}")
        print(
            "Validation status:           "
            f"{'PASSED' if validation_passed else 'FAILED'}"
        )

        sample = connection.execute("""
            SELECT
                product_key,
                stockcode,
                description,
                effective_from,
                effective_to,
                is_current
            FROM dim_product
            WHERE stockcode IN (
                SELECT stockcode
                FROM dim_product
                GROUP BY stockcode
                HAVING COUNT(*) > 1
                ORDER BY
                    COUNT(*) DESC,
                    stockcode
                LIMIT 1
            )
            ORDER BY
                stockcode,
                effective_from;
        """).fetchall()

        print("-" * 75)
        print("EXAMPLE — PRODUCT VERSION HISTORY")
        print("-" * 75)

        if sample:
            for row in sample:
                status = (
                    "CURRENT"
                    if row[5]
                    else "HISTORICAL"
                )

                effective_to = (
                    row[4]
                    if row[4] is not None
                    else "OPEN"
                )

                print(
                    f"Product key: {row[0]} | "
                    f"Stock code: {row[1]} | "
                    f"Description: {row[2]} | "
                    f"From: {row[3]} | "
                    f"To: {effective_to} | "
                    f"Status: {status}"
                )
        else:
            print(
                "No products with multiple versions were found."
            )

        print("=" * 75)

        logging.info(
            "SCD2 validation completed. "
            "Unique products: %s, "
            "total versions: %s, "
            "historical versions: %s, "
            "products with history: %s, "
            "invalid current versions: %s, "
            "invalid validity periods: %s, "
            "invalid version boundaries: %s, "
            "duplicate versions: %s, "
            "null SCD2 values: %s, "
            "status: %s",
            metrics[0],
            metrics[1],
            metrics[2],
            metrics[3],
            invalid_current_versions,
            invalid_periods,
            invalid_version_boundaries,
            duplicate_versions,
            null_scd2_values,
            "PASSED" if validation_passed else "FAILED",
        )

        if not validation_passed:
            raise RuntimeError(
                "SCD Type 2 validation failed. "
                "Review dim_product and pipeline.log."
            )

    finally:
        connection.close()


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    """Orchestrate the full pipeline in sequence."""
    args = parse_args()
    setup_logger()

    print("\n" + "=" * 70)
    print("ONLINE RETAIL DATA PIPELINE")
    print(f"Version:     {PIPELINE_VERSION}")
    print(f"Environment: {ENVIRONMENT}")
    print("=" * 70)
    print(f"Mode:        {args.mode}")
    print(f"Stage:       {args.stage}")
    print(f"Dry run:     {args.dry_run}")

    logging.info("=" * 70)
    logging.info("Starting Online Retail pipeline")
    logging.info("Pipeline version: %s", PIPELINE_VERSION)
    logging.info("Environment: %s", ENVIRONMENT)
    logging.info("Pipeline mode: %s", args.mode)
    logging.info("Pipeline stage: %s", args.stage)
    logging.info("Dry run: %s", args.dry_run)

    pipeline_start = time.perf_counter()

    try:
        for step in PIPELINE_STEPS:
            if args.stage != "all" and step["stage"] != args.stage:
                continue

            if args.dry_run:
                print(
                    f"[DRY RUN] Would execute: "
                    f"{step['name']} -> {step['script']}"
                )
                logging.info(
                    "[DRY RUN] Would execute: %s -> %s",
                    step["name"],
                    step["script"],
                )
                continue

            run_step(step["name"], step["script"])

            # Display and validate SCD2 immediately after
            # building the Data Warehouse.
            if step["script"].name == "build_datawarehouse.py":
                display_scd2_summary()

        total_duration = time.perf_counter() - pipeline_start

        logging.info("=" * 70)
        logging.info("Pipeline completed successfully")
        logging.info(
            "Total pipeline execution time: %.2f seconds",
            total_duration,
        )

        print("\n" + "=" * 70)
        if args.dry_run:
            print("\n" + "=" * 70)
            print("ONLINE RETAIL PIPELINE DRY RUN COMPLETED")
            print(f"Mode: {args.mode}")
            print("No pipeline steps were executed.")
            print("=" * 70)
        else:
            print("\n" + "=" * 70)
            print("ONLINE RETAIL PIPELINE COMPLETED SUCCESSFULLY")
            print(f"Total execution time: {total_duration:.2f} seconds")
            print(f"Log file: {LOG_PATH}")
            print("=" * 70)

    except Exception as error:
        total_duration = time.perf_counter() - pipeline_start

        logging.exception("=" * 70)
        logging.exception("Pipeline failed: %s", error)
        logging.error(
            "Total execution time before failure: %.2f seconds",
            total_duration,
        )

        print("\n" + "=" * 70)
        print("ONLINE RETAIL PIPELINE FAILED")
        print(f"Error: {error}")
        print(
            "Execution time before failure: "
            f"{total_duration:.2f} seconds"
        )
        print(f"Review the log file: {LOG_PATH}")
        print("=" * 70)

        raise


if __name__ == "__main__":
    main()