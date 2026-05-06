🛍️ **Online Retail Data Pipeline & Analytics Dashboard**
🚀 One-command pipeline | 📊 Power BI ready | ⚡ DuckDB-powered

📌 **Overview**

This project implements an end-to-end data pipeline and analytics solution using Python, DuckDB, and Power BI.

It ingests raw retail data, performs data cleaning and transformations, builds a dimensional Data Warehouse (Star Schema), and delivers business insights through an interactive Power BI dashboard.

The pipeline is fully modular, reproducible, and can be executed end-to-end with a single command.

## 🏗️ Architecture

The solution follows a layered data engineering approach:

1. **Data Ingestion (Python + Pandas)**
   * Reads raw CSV data
   * Performs initial cleaning and standardization
   * Handles null values, trims strings, and enforces data types
   * Outputs a cleaned dataset (cleaned_sales.csv)
  
2. **Data Transformation (DuckDB - Staging Layer)**
   * Loads cleaned data into DuckDB (retail.db)
   * Creates staging tables (sales_base, stg_time, sales_staging)
   * Applies business rules and filters:
*     *Removes invalid transactions (returns, test data, adjustments)
*     *Ensures valid quantities, prices, and dates
* Prepares structured data for the Data Warehouse
      
3. **Data Warehouse (Star Schema)**
      * Builds dimension and fact tables
      * Uses surrogate keys and sequences
      * Ensures referential integrity
      * Applies deduplication logic
      
4. **Data Export (CSV for BI Consumption)**
   * Exports dimension and fact tables to CSV
   * Generates datasets in output/powerbi/
   * Enables plug-and-play integration with BI tools
   * Eliminates need for database configuration

5. **Analytics Layer (Power BI)**
    * Consumes generated CSV files
    * Provides dashboards and KPIs 
    * Works immediately after pipeline execution

## 📂 Project Structure

OnlineRetail/
├── scripts/
│   ├── data_ingestion.py
│   ├── transformations.py
│   └── build_datawarehouse.py
│
├── notebooks/
│   └── eda_online_retail.ipynb
│
├── dashboards/
│   └── online_retail_dashboard.pbix
│
├── data/
│   ├── raw/
│   └── processed/
│
├── output/
│   └── powerbi/          # CSV files for Power BI
│
├── db/
├── logs/
│
├── run_pipeline.py
├── run_pipeline.sh
├── README.md
└── .gitignore

## 🔄 Pipeline Flow

data/raw/Online Retail.csv
        ↓
data/processed/cleaned_sales.csv
        ↓
db/retail.db (staging layer)
        ↓
db/DW_Online_Retail.db (data warehouse)
        ↓
output/powerbi/*.csv
        ↓
Power BI Dashboard

## ⚙️ Technologies Used

Python
Pandas
DuckDB
SQL
Power BI
Bash

## 📦 Environment & Dependencies

This project uses a virtual environment to ensure dependency isolation and reproducibility.

**Create virtual environment**
  python -m venv .venv

**Activate environment**

**Mac/Linux**:

 source venv/bin/activate

**Windows:**

 venv\Scripts\activate

## 📄 Requirements

pandas>=2.0,<4.0
duckdb>=1.5.2,<2.0
matplotlib>=3.7,<4.0
pyarrow>=14.0,<20.0

**Install dependencies**
pip install -r requirements.txt

## 📥 Dataset

This project uses the Online Retail dataset.

**Download it from:**
https://archive.ics.uci.edu/ml/datasets/Online+Retail

After downloading, place the file in:

data/raw/Online_Retail.csv

## 🚀 How to Run the Project

1. **Clone the repository**
  git clone <your-repo-url>
  cd OnlineRetail
2. **Create virtual environment**
   python -m venv .venv
   source .venv/bin/activate   # Mac/Linux
3. **Install dependencies**
   pip install -r requirements.txt
4. **Run the pipeline**
   python run_pipeline.py

## 📊 Output

After execution, the pipeline generates:

✔️ **Data Warehouse (DuckDB)**

db/DW_Online_Retail.db

✔️ **Power BI ready datasets**

output/powerbi/
├── dim_tiempo.csv
├── dim_customer.csv
├── dim_product.csv
├── dim_country.csv
├── dim_invoice.csv
└── fact_sales.csv

## 📊 Data Warehouse Model

**Dimensions**
    dim_tiempo
    dim_customer
    dim_product
    dim_country
    dim_invoice
**Fact Table**
    fact_sales

The model follows a star schema design optimized for analytical queries.

## 🧪 Data Quality & Validation

The pipeline includes:

  * Null validation checks
  * Data type enforcement
  * Business rule filtering (invalid transactions removed)
  * Deduplication using window functions
  * Referential integrity via foreign keys

## 📊 Power BI Dashboard

The dashboard is built using exported CSV files from the Data Warehouse and provides:

✔️ No configuration required
✔️ Works immediately after running the pipeline
✔️ Designed for easy consumption by recruiters and stakeholders

**Key Metrics**
    Total Revenue
    Total Orders
    Total Customers
    Average Order Value
**Visualizations**
    Monthly Sales Trend
    Top Countries by Sales
    Top Products
    Customer Analysis

**File Location**
dashboards/online_retail_dashboard.pbix

Open using Power BI Desktop (Windows) or Power BI Service (Mac users).

## 🔌 Power BI Data Source

The dashboard uses:

output/powerbi/

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

No database connection required
No additional configuration needed
Works across different environments

## 📓 Notebook (EDA)

The notebook is used for:

data exploration
data validation
business insights

**Location:**

notebooks/eda_online_retail.ipynb

## 🧠 Key Features

* End-to-end data pipeline
* Layered architecture (raw → processed → staging → DW → BI)
* DuckDB-based transformations
* Star schema data modeling
* Automated CSV export for BI tools
* Logging and execution tracking
* Reproducible and modular design
* Isolated environment with dependency management

## 💡 Design Decisions

* Raw dataset is not included to keep the repository lightweight
* The pipeline is designed to be reproducible using relative paths
* The virtual environment (venv/) is excluded via .gitignore
* DuckDB used as lightweight analytical database
* CSV export layer implemented for easy BI integration
* Separation of concerns:
* Ingestion & Cleaning
* Transformation (Staging)
* Data Warehouse
* Analytics output

## 🎯 Author
**Lina Marcela Franco Montes**
Data Engineering Portfolio Project
