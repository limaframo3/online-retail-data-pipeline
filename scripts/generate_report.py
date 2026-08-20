from pathlib import Path
from datetime import datetime
import duckdb


# =========================================================
# CONFIGURATION
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "db" / "DW_Online_Retail.db"
LOG_PATH = BASE_DIR / "logs" / "pipeline.log"
OUTPUT_DIR = BASE_DIR / "output"
REPORT_PATH = OUTPUT_DIR / "pipeline_report.txt"


# =========================================================
# REPORT GENERATION
# =========================================================
def generate_report() -> None:
    """Generate an automatic report for the Online Retail pipeline."""

    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        total_revenue = connection.execute("""
            SELECT COALESCE(ROUND(SUM(total_venta), 2), 0)
            FROM fact_sales;
        """).fetchone()[0]

        total_orders = connection.execute("""
            SELECT COUNT(DISTINCT invoiceno)
            FROM fact_sales;
        """).fetchone()[0]

        total_customers = connection.execute("""
            SELECT COUNT(DISTINCT customerid)
            FROM fact_sales
            WHERE customerid IS NOT NULL;
        """).fetchone()[0]

        total_products = connection.execute("""
            SELECT COUNT(DISTINCT stockcode)
            FROM dim_product;
        """).fetchone()[0]

        scd2_metrics = connection.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE is_current = TRUE
                ) AS current_versions,
                COUNT(*) FILTER (
                    WHERE is_current = FALSE
                ) AS historical_versions,
                COUNT(DISTINCT stockcode) FILTER (
                    WHERE is_current = FALSE
                ) AS products_with_history
            FROM dim_product;
        """).fetchone()

        top_countries = connection.execute("""
            SELECT
                country.country,
                ROUND(SUM(fact.total_venta), 2) AS revenue
            FROM fact_sales AS fact
            INNER JOIN dim_country AS country
                ON fact.country_key = country.country_key
            GROUP BY country.country
            ORDER BY revenue DESC
            LIMIT 5;
        """).fetchall()

        # Resolve each fact through its historical product_key, then group all
        # versions under the product's single current business description.
        top_products = connection.execute("""
            SELECT
                current_product.stockcode,
                current_product.description,
                ROUND(SUM(fact.total_venta), 2) AS revenue
            FROM fact_sales AS fact
            INNER JOIN dim_product AS product_version
                ON fact.product_key = product_version.product_key
            INNER JOIN dim_product AS current_product
                ON product_version.stockcode = current_product.stockcode
               AND current_product.is_current = TRUE
            GROUP BY
                current_product.stockcode,
                current_product.description
            ORDER BY revenue DESC
            LIMIT 5;
        """).fetchall()
    finally:
        connection.close()

    log_status = "Log file found" if LOG_PATH.exists() else "Log file not found"

    report_lines = [
        "ONLINE RETAIL PIPELINE REPORT",
        "=" * 35,
        "",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Database: {DB_PATH}",
        f"Log status: {log_status}",
        "",
        "GENERAL METRICS",
        "-" * 15,
        f"Total Revenue: ${total_revenue:,.2f}",
        f"Total Orders: {total_orders:,}",
        f"Total Customers: {total_customers:,}",
        f"Total Products: {total_products:,}",
        f"Current Product Versions: {scd2_metrics[0]:,}",
        f"Historical Product Versions: {scd2_metrics[1]:,}",
        f"Products with History: {scd2_metrics[2]:,}",
        "",
        "TOP 5 COUNTRIES BY REVENUE",
        "-" * 30,
    ]

    for country, revenue in top_countries:
        report_lines.append(f"{country}: ${revenue:,.2f}")

    report_lines.extend([
        "",
        "TOP 5 PRODUCTS BY REVENUE",
        "-" * 29,
    ])

    for stockcode, product, revenue in top_products:
        report_lines.append(
            f"{stockcode} - {product}: ${revenue:,.2f}"
        )

    report_lines.extend([
        "",
        "PIPELINE STATUS",
        "-" * 15,
        "Status: Completed successfully",
        "Report generated automatically after pipeline execution.",
    ])

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"Report generated successfully: {REPORT_PATH}")


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    generate_report()


if __name__ == "__main__":
    main()