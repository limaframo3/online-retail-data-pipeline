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
        format="%(asctime)s - %(levelname)s - %(message)s"
    )


# =========================================================
# CONNECTION
# =========================================================
def connect_to_dw() -> duckdb.DuckDBPyConnection:
    """Create connection to the target data warehouse database."""
    logging.info(f"Connecting to target DW database: {DW_DB_PATH}")
    return duckdb.connect(str(DW_DB_PATH))


def attach_source_database(con: duckdb.DuckDBPyConnection) -> None:
    """Attach source staging database."""
    logging.info(f"Attaching source database: {SOURCE_DB_PATH}")
    con.execute(f"ATTACH '{str(SOURCE_DB_PATH)}' AS source_db;")


# =========================================================
# CREATE SEQUENCES
# =========================================================
def create_sequences(con: duckdb.DuckDBPyConnection) -> None:
    """Create surrogate key sequences."""
    logging.info("Creating sequences")

    con.execute("""
    CREATE SEQUENCE IF NOT EXISTS seq_dim_tiempo START 1;
    CREATE SEQUENCE IF NOT EXISTS seq_dim_customer START 1;
    CREATE SEQUENCE IF NOT EXISTS seq_dim_product START 1;
    CREATE SEQUENCE IF NOT EXISTS seq_dim_country START 1;
    CREATE SEQUENCE IF NOT EXISTS seq_dim_invoice START 1;
    CREATE SEQUENCE IF NOT EXISTS seq_fact_sales START 1;
    """)


# =========================================================
# CREATE DIMENSIONS
# =========================================================
def create_dimensions(con: duckdb.DuckDBPyConnection) -> None:
    """Create dimension tables."""
    logging.info("Creating dimension tables")

    con.execute("""
    CREATE TABLE IF NOT EXISTS dim_tiempo (
        date_key INTEGER PRIMARY KEY DEFAULT nextval('seq_dim_tiempo'),
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
        customer_key INTEGER PRIMARY KEY DEFAULT nextval('seq_dim_customer'),
        customerid VARCHAR NOT NULL UNIQUE
    );
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS dim_product (
        product_key INTEGER PRIMARY KEY DEFAULT nextval('seq_dim_product'),
        stockcode VARCHAR NOT NULL UNIQUE,
        description VARCHAR
    );
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS dim_country (
        country_key INTEGER PRIMARY KEY DEFAULT nextval('seq_dim_country'),
        country VARCHAR NOT NULL UNIQUE
    );
    """)

    con.execute("""
    CREATE TABLE IF NOT EXISTS dim_invoice (
        invoice_key INTEGER PRIMARY KEY DEFAULT nextval('seq_dim_invoice'),
        invoiceno VARCHAR NOT NULL UNIQUE
    );
    """)


# =========================================================
# CREATE FACT TABLE
# =========================================================
def create_fact_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create fact table."""
    logging.info("Creating fact_sales table")

    con.execute("""
    CREATE TABLE IF NOT EXISTS fact_sales (
        sales_key INTEGER PRIMARY KEY DEFAULT nextval('seq_fact_sales'),

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

        CONSTRAINT uq_fact_sales UNIQUE (invoiceno, stockcode, customerid, invoicedate),

        FOREIGN KEY (date_key) REFERENCES dim_tiempo(date_key),
        FOREIGN KEY (customer_key) REFERENCES dim_customer(customer_key),
        FOREIGN KEY (product_key) REFERENCES dim_product(product_key),
        FOREIGN KEY (country_key) REFERENCES dim_country(country_key),
        FOREIGN KEY (invoice_key) REFERENCES dim_invoice(invoice_key)
    );
    """)


# =========================================================
# LOAD DIMENSIONS
# =========================================================
def load_dim_time(con: duckdb.DuckDBPyConnection) -> None:
    """Load dim_tiempo from source_db.stg_time."""
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
        t.invoice_date AS full_date,
        t.invoice_year AS year,
        t.invoice_quarter AS quarter,
        t.invoice_month AS month,
        t.month_name,
        t.invoice_week AS week_of_year,
        t.invoice_day AS day_of_month,
        t.day_name,
        CASE
            WHEN t.day_name IN ('Saturday', 'Sunday') THEN 1
            ELSE 0
        END AS is_weekend,
        strftime(t.invoice_date, '%Y-%m') AS year_month --converts a date into Year-Month formatted text
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
    ) t
    WHERE NOT EXISTS ( --Check if it doesn't exist in the dim before inserting the record
        SELECT 1
        FROM dim_tiempo d
        WHERE d.full_date = t.invoice_date
    );
    """)


def load_dim_customer(con: duckdb.DuckDBPyConnection) -> None:
    """Load dim_customer from source staging table."""
    logging.info("Loading dim_customer")

    con.execute("""
    INSERT INTO dim_customer (customerid)
    SELECT s.customerid
    FROM (
        SELECT DISTINCT customerid
        FROM source_db.sales_staging
        WHERE customerid IS NOT NULL
    ) s
    WHERE NOT EXISTS ( --Check if it doesn't exist in the dim before inserting the record
        SELECT 1
        FROM dim_customer d
        WHERE d.customerid = s.customerid
    );
    """)


def load_dim_product(con: duckdb.DuckDBPyConnection) -> None:
    """Load dim_product from source staging table."""
    logging.info("Loading dim_product")

    con.execute("""
    INSERT INTO dim_product (stockcode, description)
    SELECT
        s.stockcode,
        MIN(COALESCE(s.description, 'Unknown')) AS description
    FROM source_db.sales_staging s
    WHERE s.stockcode IS NOT NULL
      AND NOT EXISTS ( --Check if it doesn't exist in the dim before inserting the record
          SELECT 1
          FROM dim_product d
          WHERE d.stockcode = s.stockcode
      )
    GROUP BY s.stockcode;
    """)


def load_dim_country(con: duckdb.DuckDBPyConnection) -> None:
    """Load dim_country from source staging table."""
    logging.info("Loading dim_country")

    con.execute("""
    INSERT INTO dim_country (country)
    SELECT s.country
    FROM (
        SELECT DISTINCT country
        FROM source_db.sales_staging
        WHERE country IS NOT NULL
    ) s
    WHERE NOT EXISTS ( --Check if it doesn't exist in the dim before inserting the record
        SELECT 1
        FROM dim_country d
        WHERE d.country = s.country
    );
    """)


def load_dim_invoice(con: duckdb.DuckDBPyConnection) -> None:
    """Load dim_invoice from source staging table."""
    logging.info("Loading dim_invoice")

    con.execute("""
    INSERT INTO dim_invoice (invoiceno)
    SELECT s.invoiceno
    FROM (
        SELECT DISTINCT invoiceno
        FROM source_db.sales_staging
        WHERE invoiceno IS NOT NULL
    ) s
    WHERE NOT EXISTS ( --Check if it doesn't exist in the dim before inserting the record
        SELECT 1
        FROM dim_invoice d
        WHERE d.invoiceno = s.invoiceno
    );
    """)


# =========================================================
# LOAD FACT TABLE
# =========================================================
def load_fact_sales(con: duckdb.DuckDBPyConnection) -> None:
    """Load fact_sales from source staging table."""
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
        line_count  --It is used to count records
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
            ROW_NUMBER() OVER ( --lists by group
                PARTITION BY invoiceno, stockcode, customerid, invoicedate
                ORDER BY invoicedate
            ) AS rn
        FROM source_db.sales_staging
    )
    SELECT
        dt.date_key,
        dc.customer_key,
        dp.product_key,
        dco.country_key,
        di.invoice_key,
        s.invoiceno,
        s.stockcode,
        s.customerid,
        s.invoicedate,
        s.quantity,
        s.unitprice,
        s.total_venta,
        1 AS line_count
    FROM staging_dedup s
    INNER JOIN dim_tiempo dt
        ON CAST(s.invoicedate AS DATE) = dt.full_date
    INNER JOIN dim_customer dc
        ON s.customerid = dc.customerid
    INNER JOIN dim_product dp
        ON s.stockcode = dp.stockcode
    INNER JOIN dim_country dco
        ON s.country = dco.country
    INNER JOIN dim_invoice di
        ON s.invoiceno = di.invoiceno
    WHERE s.rn = 1  --- Select record with the number 1 after it has been grouped
      AND NOT EXISTS (
          SELECT 1
          FROM fact_sales f
          WHERE f.invoiceno = s.invoiceno
            AND f.stockcode = s.stockcode
            AND f.customerid = s.customerid
            AND f.invoicedate = s.invoicedate
      );
    """)


# =========================================================
# VALIDATION
# =========================================================
def log_table_counts(con: duckdb.DuckDBPyConnection) -> None:
    """Log row counts for dimension and fact tables."""
    tables = [
        "dim_tiempo",
        "dim_customer",
        "dim_product",
        "dim_country",
        "dim_invoice",
        "fact_sales",
    ]

    for table in tables:
        result = con.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()[0]
        logging.info(f"{table}: {result} rows")


def log_invalid_fact_rows(con: duckdb.DuckDBPyConnection) -> None:
    """Log rows with null foreign keys in fact table."""
    result = con.execute("""
    SELECT COUNT(*) AS invalid_rows
    FROM fact_sales
    WHERE date_key IS NULL
       OR customer_key IS NULL
       OR product_key IS NULL
       OR country_key IS NULL
       OR invoice_key IS NULL
    """).fetchone()[0]

    logging.info(f"fact_sales rows with null foreign keys: {result}")

# =========================================================
# EXPORT TABLES FOR POWER BI
# =========================================================
def export_powerbi_csv(con: duckdb.DuckDBPyConnection) -> None:
    """Export DW dimension and fact tables to CSV files for Power BI."""
    logging.info("Exporting Data Warehouse tables to CSV for Power BI")

    DASHBOARD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tables = [
        "dim_tiempo",
        "dim_customer",
        "dim_product",
        "dim_country",
        "dim_invoice",
        "fact_sales"
    ]

    for table in tables:
        output_path = DASHBOARD_OUTPUT_DIR / f"{table}.csv"

        logging.info(f"Exporting {table} to {output_path}")

        con.execute(f"""
        COPY (
            SELECT *
            FROM {table}
        )
        TO '{str(output_path)}'
        (HEADER, DELIMITER ',');
        """)

    logging.info("Power BI CSV export completed successfully")


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    """Execute data warehouse creation workflow."""
    setup_logger()
    logging.info("Starting data warehouse pipeline")

    con = None

    try:
        con = connect_to_dw()
        attach_source_database(con)

        create_sequences(con)
        create_dimensions(con)
        create_fact_table(con)

        load_dim_time(con)
        load_dim_customer(con)
        load_dim_product(con)
        load_dim_country(con)
        load_dim_invoice(con)
        load_fact_sales(con)

        log_table_counts(con)
        log_invalid_fact_rows(con)
        export_powerbi_csv(con)

        logging.info("Data warehouse pipeline completed successfully")

    except Exception as e:
        logging.error(f"Data warehouse pipeline failed: {e}")
        raise

    finally:
        if con:
            con.close()


if __name__ == "__main__":
    main()