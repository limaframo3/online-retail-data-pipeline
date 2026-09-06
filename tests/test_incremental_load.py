import duckdb

from scripts.build_datawarehouse import load_fact_sales


def test_fact_sales_is_idempotent():
    con = duckdb.connect(":memory:")

    # Simplified dimensions required by load_fact_sales
    con.execute("""
        CREATE TABLE dim_tiempo (
            date_key INTEGER,
            full_date DATE
        );

        CREATE TABLE dim_customer (
            customer_key INTEGER,
            customerid VARCHAR
        );

        CREATE TABLE dim_product (
            product_key INTEGER,
            stockcode VARCHAR,
            effective_from TIMESTAMP,
            effective_to TIMESTAMP
        );

        CREATE TABLE dim_country (
            country_key INTEGER,
            country VARCHAR
        );

        CREATE TABLE dim_invoice (
            invoice_key INTEGER,
            invoiceno VARCHAR
        );

        CREATE TABLE fact_sales (
            sales_key INTEGER DEFAULT 1,
            date_key INTEGER,
            customer_key INTEGER,
            product_key INTEGER,
            country_key INTEGER,
            invoice_key INTEGER,
            invoiceno VARCHAR,
            stockcode VARCHAR,
            customerid VARCHAR,
            invoicedate TIMESTAMP,
            quantity INTEGER,
            unitprice DOUBLE,
            total_venta DOUBLE,
            line_count INTEGER
        );

        CREATE SCHEMA source_db;

        CREATE TABLE source_db.sales_staging (
            invoiceno VARCHAR,
            stockcode VARCHAR,
            description VARCHAR,
            quantity INTEGER,
            unitprice DOUBLE,
            invoicedate TIMESTAMP,
            customerid VARCHAR,
            country VARCHAR,
            total_venta DOUBLE
        );
    """)

    # Dimension records
    con.execute("""
        INSERT INTO dim_tiempo VALUES
            (1, '2010-12-01');

        INSERT INTO dim_customer VALUES
            (1, '17850');

        INSERT INTO dim_product VALUES
            (1, '85123A', '2010-12-01 00:00:00', NULL);

        INSERT INTO dim_country VALUES
            (1, 'United Kingdom');

        INSERT INTO dim_invoice VALUES
            (1, '536365');
    """)

    # One source transaction
    con.execute("""
        INSERT INTO source_db.sales_staging VALUES (
            '536365',
            '85123A',
            'Valid Product',
            6,
            2.55,
            '2010-12-01 08:26:00',
            '17850',
            'United Kingdom',
            15.30
        );
    """)

    # First load
    load_fact_sales(con)

    first_count = con.execute(
        "SELECT COUNT(*) FROM fact_sales"
    ).fetchone()[0]

    # Same source is processed again
    load_fact_sales(con)

    second_count = con.execute(
        "SELECT COUNT(*) FROM fact_sales"
    ).fetchone()[0]

    con.close()

    assert first_count == 1
    assert second_count == 1

def test_fact_sales_inserts_new_transaction():
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE dim_tiempo (
            date_key INTEGER,
            full_date DATE
        );

        CREATE TABLE dim_customer (
            customer_key INTEGER,
            customerid VARCHAR
        );

        CREATE TABLE dim_product (
            product_key INTEGER,
            stockcode VARCHAR,
            effective_from TIMESTAMP,
            effective_to TIMESTAMP
        );

        CREATE TABLE dim_country (
            country_key INTEGER,
            country VARCHAR
        );

        CREATE TABLE dim_invoice (
            invoice_key INTEGER,
            invoiceno VARCHAR
        );

        CREATE TABLE fact_sales (
            sales_key INTEGER DEFAULT 1,
            date_key INTEGER,
            customer_key INTEGER,
            product_key INTEGER,
            country_key INTEGER,
            invoice_key INTEGER,
            invoiceno VARCHAR,
            stockcode VARCHAR,
            customerid VARCHAR,
            invoicedate TIMESTAMP,
            quantity INTEGER,
            unitprice DOUBLE,
            total_venta DOUBLE,
            line_count INTEGER
        );

        CREATE SCHEMA source_db;

        CREATE TABLE source_db.sales_staging (
            invoiceno VARCHAR,
            stockcode VARCHAR,
            description VARCHAR,
            quantity INTEGER,
            unitprice DOUBLE,
            invoicedate TIMESTAMP,
            customerid VARCHAR,
            country VARCHAR,
            total_venta DOUBLE
        );
    """)

    con.execute("""
        INSERT INTO dim_tiempo VALUES
            (1, '2010-12-01');

        INSERT INTO dim_customer VALUES
            (1, '17850');

        INSERT INTO dim_product VALUES
            (1, '85123A', '2010-12-01 00:00:00', NULL);

        INSERT INTO dim_country VALUES
            (1, 'United Kingdom');

        INSERT INTO dim_invoice VALUES
            (1, '536365'),
            (2, '536366');
    """)

    # First transaction
    con.execute("""
        INSERT INTO source_db.sales_staging VALUES (
            '536365',
            '85123A',
            'Valid Product',
            6,
            2.55,
            '2010-12-01 08:26:00',
            '17850',
            'United Kingdom',
            15.30
        );
    """)

    load_fact_sales(con)

    first_count = con.execute(
        "SELECT COUNT(*) FROM fact_sales"
    ).fetchone()[0]

    # A genuinely new transaction arrives
    con.execute("""
        INSERT INTO source_db.sales_staging VALUES (
            '536366',
            '85123A',
            'Valid Product',
            2,
            2.55,
            '2010-12-01 09:00:00',
            '17850',
            'United Kingdom',
            5.10
        );
    """)

    load_fact_sales(con)

    second_count = con.execute(
        "SELECT COUNT(*) FROM fact_sales"
    ).fetchone()[0]

    invoices = con.execute("""
        SELECT invoiceno
        FROM fact_sales
        ORDER BY invoiceno
    """).fetchall()

    con.close()

    assert first_count == 1
    assert second_count == 2
    assert invoices == [
        ("536365",),
        ("536366",),
    ]