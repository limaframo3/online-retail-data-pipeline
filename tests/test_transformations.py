import duckdb

from scripts.transformations import create_sales_staging


def test_sales_staging_keeps_only_valid_commercial_transactions():
    con = duckdb.connect(":memory:")

    con.execute("""
        CREATE TABLE sales_base (
            invoiceno VARCHAR,
            stockcode VARCHAR,
            description VARCHAR,
            quantity INTEGER,
            unitprice DECIMAL(12,2),
            invoicedate TIMESTAMP,
            customerid VARCHAR,
            country VARCHAR
        );
    """)

    con.execute("""
        INSERT INTO sales_base VALUES
        ('536365', 'A1', 'Valid Product', 5, 2.50,
         '2010-12-01 08:26:00', '17850', 'United Kingdom'),

        ('536366', 'A2', 'Invalid Quantity', 0, 2.50,
         '2010-12-01 08:27:00', '17850', 'United Kingdom'),

        ('536367', 'A3', 'Invalid Price', 5, 0,
         '2010-12-01 08:28:00', '17850', 'United Kingdom'),

        ('C536368', 'A4', 'Cancelled Product', 5, 2.50,
         '2010-12-01 08:29:00', '17850', 'United Kingdom'),

        ('536369', 'A5', 'POSTAGE', 5, 2.50,
         '2010-12-01 08:30:00', '17850', 'United Kingdom');
    """)

    create_sales_staging(con)

    result = con.execute("""
        SELECT invoiceno
        FROM sales_staging
        ORDER BY invoiceno;
    """).fetchall()

    con.close()

    assert result == [("536365",)]