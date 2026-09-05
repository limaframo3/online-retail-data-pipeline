from pathlib import Path
import duckdb
import logging


# =========================================================
# CONFIGURATION
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_PATH = BASE_DIR / "data" / "processed" / "cleaned_sales.parquet"
OUTPUT_PATH = BASE_DIR / "output" / "sales_staging.parquet"
DB_PATH = BASE_DIR / "db" / "retail.db"
LOG_PATH = BASE_DIR / "logs" / "pipeline.log"


# =========================================================
# LOGGER
# =========================================================

def setup_logger():
    """Configure logging for the transformation process."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Reset logging (important)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

# =========================================================
# LOAD DATA
# =========================================================
def load_raw_data(con):
    """Load cleaned parquet data into DuckDB raw table."""
    logging.info("Loading CSV into sales_raw")

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


# =========================================================
# SALES STAGING
# =========================================================
def create_sales_staging(con):
    """Create sales staging table with valid commercial transactions only."""
    logging.info("Creating sales_staging")

    con.execute("""
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
    WHERE quantity > 0
      AND unitprice > 0
      AND invoicedate IS NOT NULL
      AND invoiceno NOT LIKE 'C%'
      AND NOT (
            UPPER(description) LIKE '%POSTAGE%'
            OR UPPER(description) LIKE '%TEST%'
            OR UPPER(description) LIKE '%SAMPLE%'
            OR UPPER(description) LIKE '%ADJUST%'
            OR UPPER(description) LIKE '%DISCOUNT%'
            OR UPPER(description) LIKE '%CHARGES%'
            OR UPPER(description) LIKE '%CARRIAGE%'
            OR UPPER(description) LIKE '%GIFT%'
            OR UPPER(description) LIKE '%MANUAL%'
            OR TRIM(description) = '?'
            OR UPPER(description) LIKE '%UNKNOWN%'
            OR UPPER(description) LIKE '%CHECK%'
            OR UPPER(description) LIKE '%DAMAGED%'
        );
    """)


# =========================================================
# EXPORT
# =========================================================
def export_data(con):
    """Export staging table to Parquet."""
    logging.info("Exporting sales_staging to Parquet")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    con.execute(f"""
    COPY (
        SELECT *
        FROM sales_staging
    )
    TO '{str(OUTPUT_PATH)}'
    (FORMAT PARQUET, COMPRESSION ZSTD);
    """)


# =========================================================
# MAIN
# =========================================================
def main():
    """Execute DuckDB transformation workflow."""
    setup_logger()
    logging.info("Starting transformation pipeline")

    con = None

    try:
        con = duckdb.connect(str(DB_PATH))

        load_raw_data(con)
        create_base_table(con)
        validate_nulls(con)
        create_time_table(con)
        create_sales_staging(con)
        export_data(con)

        logging.info("Pipeline completed successfully")

    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        raise

    finally:
        if con:
            con.close()


if __name__ == "__main__":
    main()