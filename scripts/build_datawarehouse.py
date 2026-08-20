from pathlib import Path
import logging

import duckdb


# =========================================================
# CONFIGURATION
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent

SOURCE_DB_PATH = BASE_DIR / "db" / "retail.db"
DW_DB_PATH = BASE_DIR / "db" / "DW_Online_Retail.db"
LOG_PATH = BASE_DIR / "logs" / "pipeline.log"
DASHBOARD_OUTPUT_DIR = BASE_DIR / "output" / "powerbi"

REQUIRED_SCD2_COLUMNS = {
    "product_key",
    "stockcode",
    "description",
    "effective_from",
    "effective_to",
    "is_current",
}


# =========================================================
# LOGGER
# =========================================================
def setup_logger() -> None:
    """Configure logging for the data warehouse process."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DW_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


# =========================================================
# CONNECTION
# =========================================================
def connect_to_dw() -> duckdb.DuckDBPyConnection:
    """Create a connection to the target data warehouse."""
    logging.info("Connecting to target DW database: %s", DW_DB_PATH)
    return duckdb.connect(str(DW_DB_PATH))


def attach_source_database(con: duckdb.DuckDBPyConnection) -> None:
    """Attach the staging database as source_db."""
    logging.info("Attaching source database: %s", SOURCE_DB_PATH)
    con.execute(f"ATTACH '{SOURCE_DB_PATH}' AS source_db;")


# =========================================================
# SCHEMA
# =========================================================
def validate_existing_product_schema(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """
    Stop with a clear message when the database still has the old product
    dimension. SCD2 cannot keep stockcode as an individually unique column.
    """
    table_exists = con.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'main'
          AND table_name = 'dim_product';
    """).fetchone()[0]

    if not table_exists:
        return

    existing_columns = {
        row[1]
        for row in con.execute(
            "PRAGMA table_info('dim_product');"
        ).fetchall()
    }

    missing_columns = REQUIRED_SCD2_COLUMNS - existing_columns
    if missing_columns:
        columns = ", ".join(sorted(missing_columns))
        raise RuntimeError(
            "dim_product uses the previous schema. Back up and remove "
            f"{DW_DB_PATH.name}, then run the pipeline again. "
            f"Missing SCD2 columns: {columns}."
        )


def create_sequences(con: duckdb.DuckDBPyConnection) -> None:
    """Create sequences used to generate surrogate keys."""
    logging.info("Creating surrogate key sequences")

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_dim_tiempo START 1;
        CREATE SEQUENCE IF NOT EXISTS seq_dim_customer START 1;
        CREATE SEQUENCE IF NOT EXISTS seq_dim_product START 1;
        CREATE SEQUENCE IF NOT EXISTS seq_dim_country START 1;
        CREATE SEQUENCE IF NOT EXISTS seq_dim_invoice START 1;
        CREATE SEQUENCE IF NOT EXISTS seq_fact_sales START 1;
    """)


def create_dimensions(con: duckdb.DuckDBPyConnection) -> None:
    """Create all dimension tables."""
    logging.info("Creating dimension tables")

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_tiempo (
            date_key INTEGER PRIMARY KEY
                DEFAULT nextval('seq_dim_tiempo'),
            full_date DATE NOT NULL UNIQUE,
            year INTEGER,
            quarter INTEGER,
            month INTEGER,
            month_name VARCHAR,
            week_of_year INTEGER,
            day_of_month INTEGER,
            day_name VARCHAR,
            is_weekend INTEGER,
            year_month VARCHAR
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_customer (
            customer_key INTEGER PRIMARY KEY
                DEFAULT nextval('seq_dim_customer'),
            customerid VARCHAR NOT NULL UNIQUE
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_product (
            product_key INTEGER PRIMARY KEY
                DEFAULT nextval('seq_dim_product'),
            stockcode VARCHAR NOT NULL,
            description VARCHAR NOT NULL,
            effective_from TIMESTAMP NOT NULL,
            effective_to TIMESTAMP,
            is_current BOOLEAN NOT NULL DEFAULT TRUE,

            CONSTRAINT uq_dim_product_version
                UNIQUE (stockcode, effective_from),
            CONSTRAINT ck_dim_product_period
                CHECK (
                    effective_to IS NULL
                    OR effective_to > effective_from
                )
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_country (
            country_key INTEGER PRIMARY KEY
                DEFAULT nextval('seq_dim_country'),
            country VARCHAR NOT NULL UNIQUE
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS dim_invoice (
            invoice_key INTEGER PRIMARY KEY
                DEFAULT nextval('seq_dim_invoice'),
            invoiceno VARCHAR NOT NULL UNIQUE
        );
    """)


def create_fact_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create the sales fact table."""
    logging.info("Creating fact_sales table")

    con.execute("""
        CREATE TABLE IF NOT EXISTS fact_sales (
            sales_key INTEGER PRIMARY KEY
                DEFAULT nextval('seq_fact_sales'),

            date_key INTEGER NOT NULL,
            customer_key INTEGER NOT NULL,
            product_key INTEGER NOT NULL,
            country_key INTEGER NOT NULL,
            invoice_key INTEGER NOT NULL,

            invoiceno VARCHAR NOT NULL,
            stockcode VARCHAR NOT NULL,
            customerid VARCHAR NOT NULL,
            invoicedate TIMESTAMP NOT NULL,

            quantity INTEGER,
            unitprice DOUBLE,
            total_venta DOUBLE,
            line_count INTEGER DEFAULT 1,

            CONSTRAINT uq_fact_sales
                UNIQUE (
                    invoiceno,
                    stockcode,
                    customerid,
                    invoicedate
                ),

            FOREIGN KEY (date_key)
                REFERENCES dim_tiempo(date_key),
            FOREIGN KEY (customer_key)
                REFERENCES dim_customer(customer_key),
            -- product_key is validated logically instead of with a physical
            -- foreign key. DuckDB may reject SCD2 updates to dim_product when
            -- the referenced row already exists in fact_sales.
            FOREIGN KEY (country_key)
                REFERENCES dim_country(country_key),
            FOREIGN KEY (invoice_key)
                REFERENCES dim_invoice(invoice_key)
        );
    """)


# =========================================================
# LOAD STANDARD DIMENSIONS
# =========================================================
def load_dim_time(con: duckdb.DuckDBPyConnection) -> None:
    """Load new dates from source_db.stg_time."""
    logging.info("Loading dim_tiempo")

    con.execute("""
        INSERT INTO dim_tiempo (
            full_date,
            year,
            quarter,
            month,
            month_name,
            week_of_year,
            day_of_month,
            day_name,
            is_weekend,
            year_month
        )
        SELECT
            source.invoice_date,
            source.invoice_year,
            source.invoice_quarter,
            source.invoice_month,
            source.month_name,
            source.invoice_week,
            source.invoice_day,
            source.day_name,
            CASE
                WHEN source.day_name IN ('Saturday', 'Sunday') THEN 1
                ELSE 0
            END,
            strftime(source.invoice_date, '%Y-%m')
        FROM (
            SELECT DISTINCT
                invoice_date,
                invoice_year,
                invoice_quarter,
                invoice_month,
                month_name,
                invoice_week,
                invoice_day,
                day_name
            FROM source_db.stg_time
        ) AS source
        WHERE NOT EXISTS (
            SELECT 1
            FROM dim_tiempo AS target
            WHERE target.full_date = source.invoice_date
        );
    """)


def load_dim_customer(con: duckdb.DuckDBPyConnection) -> None:
    """Load new customers from the staging table."""
    logging.info("Loading dim_customer")

    con.execute("""
        INSERT INTO dim_customer (customerid)
        SELECT source.customerid
        FROM (
            SELECT DISTINCT customerid
            FROM source_db.sales_staging
            WHERE customerid IS NOT NULL
        ) AS source
        WHERE NOT EXISTS (
            SELECT 1
            FROM dim_customer AS target
            WHERE target.customerid = source.customerid
        );
    """)


def load_dim_country(con: duckdb.DuckDBPyConnection) -> None:
    """Load new countries from the staging table."""
    logging.info("Loading dim_country")

    con.execute("""
        INSERT INTO dim_country (country)
        SELECT source.country
        FROM (
            SELECT DISTINCT country
            FROM source_db.sales_staging
            WHERE country IS NOT NULL
        ) AS source
        WHERE NOT EXISTS (
            SELECT 1
            FROM dim_country AS target
            WHERE target.country = source.country
        );
    """)


def load_dim_invoice(con: duckdb.DuckDBPyConnection) -> None:
    """Load new invoices from the staging table."""
    logging.info("Loading dim_invoice")

    con.execute("""
        INSERT INTO dim_invoice (invoiceno)
        SELECT source.invoiceno
        FROM (
            SELECT DISTINCT invoiceno
            FROM source_db.sales_staging
            WHERE invoiceno IS NOT NULL
        ) AS source
        WHERE NOT EXISTS (
            SELECT 1
            FROM dim_invoice AS target
            WHERE target.invoiceno = source.invoiceno
        );
    """)


# =========================================================
# SCD TYPE 2 - DIM_PRODUCT
# =========================================================
def build_product_version_snapshot(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """
    Build the product history found in the full Excel snapshot.

    A new version starts whenever description changes for a stockcode.
    effective_to is an exclusive boundary: the next version starts exactly when the previous version stops being valid.
    """
    logging.info("Building product SCD2 version snapshot")

    con.execute("""
        CREATE OR REPLACE TEMP TABLE product_version_snapshot AS
        WITH product_events AS (
            SELECT
                stockcode,
                COALESCE(
                    NULLIF(TRIM(description), ''),
                    'Unknown'
                ) AS description,
                CAST(invoicedate AS TIMESTAMP) AS event_at
            FROM source_db.sales_staging
            WHERE stockcode IS NOT NULL
              AND invoicedate IS NOT NULL
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY stockcode, invoicedate
                ORDER BY
                    COALESCE(
                        NULLIF(TRIM(description), ''),
                        'Unknown'
                    )
            ) = 1
        ),
        change_flags AS (
            SELECT
                stockcode,
                description,
                event_at,
                CASE
                    WHEN LAG(description) OVER (
                        PARTITION BY stockcode
                        ORDER BY event_at
                    ) IS NULL
                    THEN 1
                    WHEN description <> LAG(description) OVER (
                        PARTITION BY stockcode
                        ORDER BY event_at
                    )
                    THEN 1
                    ELSE 0
                END AS starts_new_version
            FROM product_events
        ),
        change_groups AS (
            SELECT
                stockcode,
                description,
                event_at,
                SUM(starts_new_version) OVER (
                    PARTITION BY stockcode
                    ORDER BY event_at
                    ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
                ) AS version_group
            FROM change_flags
        ),
        versions AS (
            SELECT
                stockcode,
                description,
                MIN(event_at) AS effective_from
            FROM change_groups
            GROUP BY stockcode, version_group, description
        )
        SELECT
            stockcode,
            description,
            effective_from,
            LEAD(effective_from) OVER (
                PARTITION BY stockcode
                ORDER BY effective_from
            ) AS effective_to,
            LEAD(effective_from) OVER (
                PARTITION BY stockcode
                ORDER BY effective_from
            ) IS NULL AS is_current
        FROM versions;
    """)


def load_dim_product_scd2(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """
    Synchronize dim_product with the historical versions in the source.

    Existing surrogate keys are preserved. Re-running the pipeline with the
    same Excel file does not duplicate versions.
    """
    logging.info("Loading dim_product with SCD Type 2")

    build_product_version_snapshot(con)

    # Close or reopen existing versions according to the complete snapshot.
    con.execute("""
        UPDATE dim_product AS target
        SET
            description = source.description,
            effective_to = source.effective_to,
            is_current = source.is_current
        FROM product_version_snapshot AS source
        WHERE target.stockcode = source.stockcode
          AND target.effective_from = source.effective_from;
    """)

    # Insert only versions not loaded during a previous pipeline execution.
    con.execute("""
        INSERT INTO dim_product (
            stockcode,
            description,
            effective_from,
            effective_to,
            is_current
        )
        SELECT
            source.stockcode,
            source.description,
            source.effective_from,
            source.effective_to,
            source.is_current
        FROM product_version_snapshot AS source
        WHERE NOT EXISTS (
            SELECT 1
            FROM dim_product AS target
            WHERE target.stockcode = source.stockcode
              AND target.effective_from = source.effective_from
        )
        ORDER BY source.stockcode, source.effective_from;
    """)


# =========================================================
# LOAD FACT TABLE
# =========================================================
def refresh_fact_product_keys(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """
    Reassign previously loaded facts to the product version valid at the
    transaction timestamp. This also handles a corrected source snapshot.
    """
    logging.info("Refreshing historical product keys in fact_sales")

    con.execute("""
        UPDATE fact_sales AS fact
        SET product_key = product.product_key
        FROM dim_product AS product
        WHERE fact.stockcode = product.stockcode
          AND fact.invoicedate >= product.effective_from
          AND (
              product.effective_to IS NULL
              OR fact.invoicedate < product.effective_to
          )
          AND fact.product_key <> product.product_key;
    """)


def load_fact_sales(con: duckdb.DuckDBPyConnection) -> None:
    """Load new sales and assign the correct historical product version."""
    logging.info("Loading fact_sales")

    con.execute("""
        INSERT INTO fact_sales (
            date_key,
            customer_key,
            product_key,
            country_key,
            invoice_key,
            invoiceno,
            stockcode,
            customerid,
            invoicedate,
            quantity,
            unitprice,
            total_venta,
            line_count
        )
        WITH staging_dedup AS (
            SELECT
                invoiceno,
                stockcode,
                customerid,
                invoicedate,
                country,
                quantity,
                unitprice,
                total_venta,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        invoiceno,
                        stockcode,
                        customerid,
                        invoicedate
                    ORDER BY invoicedate
                ) AS row_number
            FROM source_db.sales_staging
        )
        SELECT
            time.date_key,
            customer.customer_key,
            product.product_key,
            country.country_key,
            invoice.invoice_key,
            source.invoiceno,
            source.stockcode,
            source.customerid,
            source.invoicedate,
            source.quantity,
            source.unitprice,
            source.total_venta,
            1
        FROM staging_dedup AS source
        INNER JOIN dim_tiempo AS time
            ON CAST(source.invoicedate AS DATE) = time.full_date
        INNER JOIN dim_customer AS customer
            ON source.customerid = customer.customerid
        INNER JOIN dim_product AS product
            ON source.stockcode = product.stockcode
           AND source.invoicedate >= product.effective_from
           AND (
                product.effective_to IS NULL
                OR source.invoicedate < product.effective_to
           )
        INNER JOIN dim_country AS country
            ON source.country = country.country
        INNER JOIN dim_invoice AS invoice
            ON source.invoiceno = invoice.invoiceno
        WHERE source.row_number = 1
          AND NOT EXISTS (
              SELECT 1
              FROM fact_sales AS fact
              WHERE fact.invoiceno = source.invoiceno
                AND fact.stockcode = source.stockcode
                AND fact.customerid = source.customerid
                AND fact.invoicedate = source.invoicedate
          );
    """)


# =========================================================
# DATA QUALITY VALIDATIONS
# =========================================================
def validate_scd2_product(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Validate the most important SCD2 rules for dim_product."""
    logging.info("Validating dim_product SCD Type 2")

    checks = {
        "products with more than one current version": """
            SELECT COUNT(*)
            FROM (
                SELECT stockcode
                FROM dim_product
                WHERE is_current = TRUE
                GROUP BY stockcode
                HAVING COUNT(*) > 1
            ) AS invalid;
        """,
        "products without a current version": """
            SELECT COUNT(*)
            FROM (
                SELECT stockcode
                FROM dim_product
                GROUP BY stockcode
                HAVING SUM(
                    CASE WHEN is_current = TRUE THEN 1 ELSE 0 END
                ) <> 1
            ) AS invalid;
        """,
        "versions with an invalid validity period": """
            SELECT COUNT(*)
            FROM dim_product
            WHERE effective_to IS NOT NULL
              AND effective_to <= effective_from;
        """,
        "overlapping product versions": """
            SELECT COUNT(*)
            FROM dim_product AS first_version
            INNER JOIN dim_product AS second_version
                ON first_version.stockcode = second_version.stockcode
               AND first_version.product_key
                    < second_version.product_key
               AND first_version.effective_from
                    < COALESCE(
                        second_version.effective_to,
                        TIMESTAMP '9999-12-31 23:59:59'
                    )
               AND second_version.effective_from
                    < COALESCE(
                        first_version.effective_to,
                        TIMESTAMP '9999-12-31 23:59:59'
                    );
        """,
    }

    failures = []
    for check_name, query in checks.items():
        invalid_rows = con.execute(query).fetchone()[0]
        logging.info("%s: %s", check_name, invalid_rows)
        if invalid_rows:
            failures.append(f"{check_name}: {invalid_rows}")

    if failures:
        raise ValueError(
            "SCD2 validation failed. " + "; ".join(failures)
        )


def validate_fact_sales(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Validate logical foreign keys and the temporal product relationship."""
    logging.info("Validating fact_sales")

    null_foreign_keys = con.execute("""
        SELECT COUNT(*)
        FROM fact_sales
        WHERE date_key IS NULL
           OR customer_key IS NULL
           OR product_key IS NULL
           OR country_key IS NULL
           OR invoice_key IS NULL;
    """).fetchone()[0]

    orphan_product_keys = con.execute("""
        SELECT COUNT(*)
        FROM fact_sales AS fact
        LEFT JOIN dim_product AS product
            ON fact.product_key = product.product_key
        WHERE product.product_key IS NULL;
    """).fetchone()[0]

    invalid_product_versions = con.execute("""
        SELECT COUNT(*)
        FROM fact_sales AS fact
        INNER JOIN dim_product AS product
            ON fact.product_key = product.product_key
        WHERE fact.invoicedate < product.effective_from
           OR (
                product.effective_to IS NOT NULL
                AND fact.invoicedate >= product.effective_to
           );
    """).fetchone()[0]

    logging.info(
        "fact_sales rows with null foreign keys: %s",
        null_foreign_keys,
    )
    logging.info(
        "fact_sales rows with orphan product keys: %s",
        orphan_product_keys,
    )
    logging.info(
        "fact_sales rows linked to an invalid product version: %s",
        invalid_product_versions,
    )

    if (
        null_foreign_keys
        or orphan_product_keys
        or invalid_product_versions
    ):
        raise ValueError(
            "fact_sales validation failed. "
            f"Null foreign keys: {null_foreign_keys}; "
            f"orphan product keys: {orphan_product_keys}; "
            f"invalid product versions: {invalid_product_versions}."
        )


def log_table_counts(con: duckdb.DuckDBPyConnection) -> None:
    """Log row counts for all dimension and fact tables."""
    tables = [
        "dim_tiempo",
        "dim_customer",
        "dim_product",
        "dim_country",
        "dim_invoice",
        "fact_sales",
    ]

    for table in tables:
        row_count = con.execute(
            f"SELECT COUNT(*) FROM {table};"
        ).fetchone()[0]
        logging.info("%s: %s rows", table, row_count)


# =========================================================
# EXPORT TABLES FOR POWER BI
# =========================================================
def export_powerbi_csv(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Export Data Warehouse tables to CSV files for Power BI."""
    logging.info("Exporting Data Warehouse tables to CSV for Power BI")
    DASHBOARD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tables = [
        "dim_tiempo",
        "dim_customer",
        "dim_product",
        "dim_country",
        "dim_invoice",
        "fact_sales",
    ]

    for table in tables:
        output_path = DASHBOARD_OUTPUT_DIR / f"{table}.csv"
        logging.info("Exporting %s to %s", table, output_path)

        con.execute(f"""
            COPY (
                SELECT *
                FROM {table}
            )
            TO '{output_path}'
            (HEADER, DELIMITER ',');
        """)

    logging.info("Power BI CSV export completed successfully")


# =========================================================
# PIPELINE
# =========================================================
def build_data_warehouse(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Create, load and validate the Data Warehouse atomically."""
    con.execute("BEGIN TRANSACTION;")

    try:
        validate_existing_product_schema(con)
        create_sequences(con)
        create_dimensions(con)
        create_fact_table(con)

        load_dim_time(con)
        load_dim_customer(con)
        load_dim_country(con)
        load_dim_invoice(con)
        load_dim_product_scd2(con)

        refresh_fact_product_keys(con)
        load_fact_sales(con)

        validate_scd2_product(con)
        validate_fact_sales(con)
        log_table_counts(con)

        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")
        raise


def main() -> None:
    """Execute the complete Data Warehouse workflow."""
    setup_logger()
    logging.info("Starting data warehouse pipeline")

    con = None

    try:
        con = connect_to_dw()
        attach_source_database(con)

        build_data_warehouse(con)
        export_powerbi_csv(con)

        logging.info(
            "Data warehouse pipeline completed successfully"
        )
    except Exception:
        logging.exception("Data warehouse pipeline failed")
        raise
    finally:
        if con is not None:
            con.close()


if __name__ == "__main__":
    main()