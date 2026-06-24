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

    conn = duckdb.connect(str(DB_PATH), read_only=True)

    total_revenue = conn.execute("""
        SELECT ROUND(SUM(quantity * unitprice), 2)
        FROM fact_sales
    """).fetchone()[0]

    total_orders = conn.execute("""
        SELECT COUNT(DISTINCT invoiceno)
        FROM fact_sales
    """).fetchone()[0]

    total_customers = conn.execute("""
        SELECT COUNT(DISTINCT customerid)
        FROM fact_sales
        WHERE customerid IS NOT NULL
    """).fetchone()[0]

    total_products = conn.execute("""
        SELECT COUNT(DISTINCT stockcode)
        FROM fact_sales
    """).fetchone()[0]

    top_countries = conn.execute("""
        SELECT
            c.country,
            ROUND(SUM(f.quantity * f.unitprice), 2) AS revenue
        FROM fact_sales f
        LEFT JOIN dim_country c
            ON f.country_key = c.country_key
        GROUP BY c.country
        ORDER BY revenue DESC
        LIMIT 5
    """).fetchall()

    top_products = conn.execute("""
        SELECT
            p.description,
            ROUND(SUM(f.quantity * f.unitprice), 2) AS revenue
        FROM fact_sales f
        LEFT JOIN dim_product p
            ON f.stockcode = p.stockcode
        GROUP BY p.description
        ORDER BY revenue DESC
        LIMIT 5
    """).fetchall()

    conn.close()

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

    for product, revenue in top_products:
        report_lines.append(f"{product}: ${revenue:,.2f}")

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