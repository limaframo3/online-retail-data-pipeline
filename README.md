🛍️ **Online Retail Data Pipeline & Analytics Dashboard**

🚀 One-command pipeline | 📊 Power BI ready | ⚡ DuckDB-powered | 🕒 SCD Type 2

📌 **Overview**

This project implements an end-to-end data pipeline and analytics solution using Python, DuckDB, and Power BI.

It ingests raw retail data, performs data cleaning and transformations, builds a dimensional Data Warehouse (Star Schema), and delivers business insights through an interactive Power BI dashboard.

The pipeline is fully modular, reproducible, and can be executed end-to-end with a single command.

## 🏗️ Architecture

The solution follows a layered data engineering approach:

1. **Data Ingestion (Python + Pandas)**
   * Reads the original Excel dataset (`Online Retail.xlsx`)
   * Automatically converts the source file into a raw CSV format (`Online_Retail.csv`)
   * Performs initial data cleaning and standardization
   * Handles null values, trims text fields, and normalizes column names
   * Enforces consistent data types and formatting rules
   * Standardizes country values using `pycountry`
   * Removes exact duplicate records
   * Generates a cleaned dataset (`cleaned_sales.csv`)
  
2. **Data Transformation (DuckDB - Staging Layer)**
   * Loads cleaned data into DuckDB (retail.db)
   * Creates staging tables (sales_base, stg_time, sales_staging)
   * Applies business rules and filters:
     * Removes invalid transactions (returns, test data, adjustments)
     * Ensures valid quantities, prices, and dates
   * Prepares structured data for the Data Warehouse
      
3. **Data Warehouse (Star Schema)**
      * Builds dimension and fact tables
      * Uses surrogate keys and sequences
      * Implements SCD Type 2 history for `dim_product`
      * Preserves historical product descriptions and validity periods
      * Assigns each sale to the correct product version through `product_key`
      * Applies referential, temporal, and deduplication validations
      
4. **Data Export (CSV for BI Consumption)**
   * Exports dimension and fact tables to CSV
   * Generates datasets in output/powerbi/
   * Enables plug-and-play integration with BI tools
   * Eliminates need for database configuration

5. **Automated Reporting**
   * Generates a pipeline execution report
   * Produces business KPI summaries
   * Includes current and historical SCD2 product metrics
   * Identifies top countries and products by revenue
   * Stores results in `output/pipeline_report.txt`
   * Executes automatically as the final pipeline step
   
6. **Analytics Layer (Power BI)**
    * Consumes generated CSV files
    * Provides dashboards and KPIs 
    * Works immediately after pipeline execution

## 📂 Project Structure
```
OnlineRetail/
├── scripts/
│   ├── data_ingestion.py           # Reads Excel, creates raw CSV, cleans data
│   ├── transformations.py          # Builds staging tables in DuckDB
│   ├── build_datawarehouse.py      # Builds the DW and SCD2 product history
│   ├── apply_scd2_demo_changes.py  # Applies controlled SCD2 source changes
│   ├── verify_scd2_demo.py         # Verifies historical and current versions
│   └── generate_report.py          # Generates the automated pipeline report
│
├── notebooks/
│   └── eda_online_retail.ipynb
│
├── dashboards/
│   └── online_retail_dashboard.pbix  # Power BI dashboard
│
├── data/
│   ├── raw/
│   │   ├── Online Retail.xlsx   # Original dataset
│   │   └── Online_Retail.csv    # Auto-generated raw CSV
│   ├── processed/
│   │   └── cleaned_sales.csv    # Cleaned dataset
│   └── demo/
│       └── scd2_product_changes.xlsx  # Demo reference workbook
│
├── output/
│   ├── powerbi/                 # CSV exports for Power BI
│   └── pipeline_report.txt      # Automated KPI and SCD2 report
│
├── db/
│   ├── retail.db                # Staging database
│   └── DW_Online_Retail.db      # Dimensional Data Warehouse
│
├── logs/
│   ├── pipeline.log             # Main pipeline execution log
│   ├── scd2_demo.log            # Controlled demo changes log
│   └── scd2_verification.log    # SCD2 verification log
│
├── config.json                  # Centralized pipeline configuration
├── run_pipeline.py              # Python pipeline orchestrator
├── run_pipeline.sh              # Bash execution helper
├── requirements.txt
├── README.md
└── .gitignore 
```

## 🔄 Pipeline Flow

```
data/raw/Online Retail.xlsx
        ↓
data/raw/Online Retail.csv
        ↓
data/processed/cleaned_sales.csv
        ↓
db/retail.db (staging layer)
        ↓
db/DW_Online_Retail.db (data warehouse)
        ↓
 ┌─────────────────────┬──────────────────┐
 ↓                     ↓
output/powerbi/*.csv   output/pipeline_report.txt
 ↓
Power BI Dashboard

```

## ⚙️ Technologies Used

* Python
* Pandas
* DuckDB
* SQL
* Power BI
* Bash
* Git & GitHub

## 📦 Environment & Dependencies

This project was developed using:

- Python 3.12+
- Pandas
- DuckDB
- OpenPyXL
- PyCountry
- Matplotlib
- Power BI
- Git & GitHub
- Bash

Dependencies are managed through a clean `requirements.txt` file using controlled version ranges.

A virtual environment (`.venv`) is recommended to ensure dependency isolation and reproducibility.

## ⚙️ Pipeline Configuration

The pipeline uses a centralized `config.json` file to manage input, output, database, log, and execution settings.

```json
{
  "paths": {
    "excel": "data/raw/Online Retail.xlsx",
    "input": "data/raw/Online_Retail.csv",
    "output": "data/processed/cleaned_sales.csv",
    "database": "db/DW_Online_Retail.db",
    "log": "logs/pipeline.log"
  },
  "pipeline": {
    "version": "1.0",
    "environment": "dev"
  }
}
```
All paths are relative to the project root, allowing the pipeline to run consistently across different environments.

The configuration is loaded automatically by the pipeline orchestrator and supporting scripts where applicable

## 📊 Data Warehouse Model

**Dimensions**
 ```
    dim_tiempo
    dim_customer
    dim_product
    dim_country
    dim_invoice
```
**Fact Table**
```   
    fact_sales
```

The model follows a star schema design optimized for analytical queries.

🕒 SCD Type 2 - Product Dimension

`dim_product` preserves product-description changes instead of overwriting previous values.

```   
  Column                  Purpose
`product_key`      Surrogate key for each product version
`stockcode`        Product business key
`description`      Description valid for the version period
`effective_from`   Timestamp when the version became valid
`effective_to`     Exclusive end timestamp; NULL for the current version
`is_current`       Identifies the active product version
```
The SCD2 implementation enforces the following rules:

* Each product has exactly one current version
* Historical versions are closed with `is_current = FALSE`
* The previous effective_to matches the next `effective_from`
* Version validity periods cannot overlap or contain gaps
* Duplicate business versions are rejected
* Facts reference the product version valid at the transaction timestamp

The relationship between `fact_sales.product_key` and `dim_product.product_key` is validated logically by the pipeline instead of using a physical DuckDB foreign-key constraint. This avoids DuckDB limitations when closing referenced SCD Type 2 versions while preserving referential and temporal validation.

## 🧪 Data Quality & Validation

The pipeline includes:

  * Null validation checks 
  * Data type enforcement 
  * Business rule filtering (invalid transactions removed)
  * Deduplication using window functions 
  * Physical foreign keys for stable dimensions 
  * Logical product-key integrity validation for SCD2 
  * Product-version validity and continuity checks 
  * Detection of null, orphan, duplicated, and temporally invalid keys

## 📥 Dataset

This project uses the Online Retail dataset.

**Download it from:**
https://archive.ics.uci.edu/ml/datasets/Online+Retail

After downloading:

1. Extract the ZIP file
2. Move `Online Retail.xlsx` file into the route:
```
data/raw/
```

## 🚀 How to Run the Project

### 1. Clone the repository

```
git clone https://github.com/limaframo3/online-retail-data-pipeline.git
cd online-retail-data-pipeline
```

### 2. Create and activate virtual environment

#### Mac/Linux
```
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows
```
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```
pip install -r requirements.txt
```
### 4. Review the configuration

Before running the pipeline, verify that the paths defined in `config.json` match the project structure.

The default configuration uses relative paths, so no changes are normally required.

### 5. Run the pipeline

Run directly with Python:
```
python run_pipeline.py
```
🕒 SCD Type 2 Demonstration

The repository includes a controlled demonstration that allows recruiters and reviewers to observe a product-description change across two pipeline executions.

1. Execute the initial load
```
./run_pipeline.sh
```
Alternatively:
```
python run_pipeline.py
```
2. Apply controlled product changes
```
python scripts/apply_scd2_demo_changes.py
```
The utility:

* Reads current product descriptions from `dim_product` 
* Adds two controlled transactions to `data/raw/Online Retail.xlsx`
* Creates `data/raw/Online Retail.before_scd2_demo.xlsx` 
* Records the operation in `logs/scd2_demo.log` 
* Prevents the same demo rows from being applied twice

The workbook `data/demo/scd2_product_changes.xlsx` documents the demonstration scenario. The Python utility applies the controlled changes automatically.

3. Execute the incremental load
```
python run_pipeline.py
```
On Mac/Linux, `./run_pipeline.sh` can be used instead.

Do not delete `db/DW_Online_Retail.db` between the initial and incremental executions. The existing database contains the original versions that must be closed and preserved.

4. Verify the SCD2 result
```
python scripts/verify_scd2_demo.py
```
Expected result:

Validation failures:     0
Validation status:       PASSED

The verification confirms:

* A historical and a current version exist for each demo product 
* Each product has exactly one current version 
* Historical validity periods are closed correctly 
* Demo facts reference the correct `product_key` 
* No orphan product keys or temporal inconsistencies exist

Restore the original source
```
python scripts/apply_scd2_demo_changes.py --restore
```
Restoring the Excel source does not remove product history already loaded into DuckDB. 
To repeat the entire demonstration from a clean state, restore the source and recreate `db/retail.db and db/DW_Online_Retail.db` before running the initial load again.

## 📊 Output

After execution, the pipeline generates:

✔️ **Data Warehouse (DuckDB)**
```
db/DW_Online_Retail.db
```

✔️ **Power BI ready datasets**
```
output/powerbi/
├── dim_tiempo.csv
├── dim_customer.csv
├── dim_product.csv
├── dim_country.csv
├── dim_invoice.csv
└── fact_sales.csv
```

✔️ **Automated Pipeline Report**
```
output/pipeline_report.txt
```
The report is automatically generated as the final step of the pipeline and provides a summary of business KPIs and execution results.

**Report Contents**
* Pipeline execution timestamp
* Total Revenue
* Total Orders
* Total Customers
* Total Products
* Current Product Versions 
* Historical Product Versions 
* Products with History 
* Top 5 Countries by Revenue 
* Top 5 Products by Revenue without SCD2 duplication 
* Pipeline execution status

**Example**

ONLINE RETAIL PIPELINE REPORT
=============================

Generated at: 2026-06-23 15:30:12

GENERAL METRICS
---------------

Total Revenue: $8,911,407.90
Total Orders: 22,190
Total Customers: 4,372
Total Products: 3,684
Current Product Versions: 3,684
Historical Product Versions: 2
Products with History: 2

TOP 5 COUNTRIES BY REVENUE
--------------------------

United Kingdom: $7,308,392.54
Netherlands: $285,446.34
EIRE: $265,545.90
Germany: $228,867.14
France: $209,024.05

PIPELINE STATUS
---------------
Status: Completed successfully

📝 Execution Logs

   Log file                         Purpose
`logs/pipeline.log`            Main pipeline steps, execution times, output, and errors
`logs/scd2_demo.log`           Controlled source changes and restoration events
`logs/scd2_verification.log`   SCD2 validation results and detected failures

## 📊 Power BI Dashboard

The dashboard is built using exported CSV files from the Data Warehouse and provides:

* No configuration required
* Works immediately after running the pipeline
* Designed for easy consumption by recruiters and stakeholders

**Key Metrics**

* Total Revenue
* Total Orders
* Total Customers
* Average Order Value

**Visualizations**

* Monthly Sales Trend
* Top Countries by Sales
* Top Products
* Customer Analysis

**File Location**
```
dashboards/online_retail_dashboard.pbix
```
Open using Power BI Desktop (Windows) or Power BI Service (Mac users).

## 🔌 Power BI Data Source

The dashboard uses:
```
output/powerbi/
```
## ▶️ How to open the dashboard

The dashboard uses CSV files generated by the pipeline.

1. Open the .pbix file
2. If prompted, update the data source:
   Go to **Transform Data → Data Source Settings**
   Point to:
   output/powerbi/
3. Click Refresh

👉 The dashboard will load automatically

💡 **Notes:**

* No database connection required
* No additional configuration needed
* Works across different environments

## 📓 Notebook (EDA)

The notebook is used for:

* data exploration
* data validation
* business insights

**Location:**
```
notebooks/eda_online_retail.ipynb
```

## 🧠 Key Features

* Centralized JSON-based configuration
* End-to-end data pipeline
* Layered architecture (raw → processed → staging → DW → BI)
* DuckDB-based transformations
* Star schema data modeling
* SCD Type 2 product-history management
* Automated CSV export for BI tools
* Logging and execution tracking
* Reproducible and modular design
* Isolated environment with dependency management
* Automated business reporting
* Automated KPI and pipeline execution reporting

## 💡 Design Decisions

* Raw dataset is not included to keep the repository lightweight
* The pipeline is designed to be reproducible using relative paths
* The virtual environment (venv/) is excluded via .gitignore
* DuckDB used as lightweight analytical database
* SCD Type 2 used to preserve changes in product descriptions
* Product referential integrity validated logically to support DuckDB SCD2 updates
* CSV export layer implemented for easy BI integration
* Separation of concerns:
  * Ingestion & Cleaning
  * Transformation (Staging)
  * Data Warehouse
  * Analytics output
* Automated reporting layer implemented for KPI generation and pipeline monitoring

## 🎯 Author
**Lina Marcela Franco Montes**
Data Engineering Portfolio Project
