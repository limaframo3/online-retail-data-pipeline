# 🛍️ Online Retail Data Pipeline & Analytics Dashboard

## 📌 Overview

This project implements an end-to-end **data pipeline and analytics solution** using Python, DuckDB, and Power BI.

It ingests raw retail data, performs data cleaning and transformations, builds a dimensional **Data Warehouse (Star Schema)**, and delivers business insights through an interactive Power BI dashboard.

The pipeline is fully modular, reproducible, and can be executed end-to-end with a single command.

---

## 🏗️ Architecture

The solution follows a layered data engineering approach:

1. **Data Ingestion (Python + Pandas)**

   * Reads raw CSV data
   * Performs initial cleaning and standardization

2. **Data Transformation (DuckDB - Staging Layer)**

   * Creates staging tables (`stg_time`, `sales_staging`)
   * Applies business rules and filters

3. **Data Warehouse (Star Schema)**

   * Builds dimension and fact tables
   * Ensures referential integrity

4. **Analytics Layer (Power BI)**

   * Connects directly to the Data Warehouse
   * Provides business insights and KPIs

---

## 📂 Project Structure

```
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
├── db/
├── logs/
│
├── run_pipeline.py
├── run_pipeline.sh
├── README.md
└── .gitignore
```

---

## 🔄 Pipeline Flow

```
data/raw/Online_Retail.csv
        ↓
data/processed/cleaned_sales.csv
        ↓
db/retail.db (staging layer)
        ↓
db/DW_Online_Retail.db (data warehouse)
        ↓
Power BI Dashboard
```

---

## ⚙️ Technologies Used

* Python
* Pandas
* DuckDB
* SQL
* Power BI
* Bash

---

## 📊 Data Warehouse Model

### Dimensions

* `dim_tiempo`
* `dim_customer`
* `dim_product`
* `dim_country`
* `dim_invoice`

### Fact Table

* `fact_sales`

The model follows a **star schema design** optimized for analytical queries.

---

## 📊 Power BI Dashboard

The dashboard connects directly to the Data Warehouse and provides:

### Key Metrics

* Total Revenue
* Total Orders
* Total Customers
* Average Order Value

### Visualizations

* Monthly Sales Trend
* Top Countries by Sales
* Top Products
* Customer Analysis

### File Location

```
dashboards/online_retail_dashboard.pbix
```

> Open using Power BI Desktop.

---

## 🔌 Power BI Data Source

The dashboard is configured to connect to:

```
db/DW_Online_Retail.db
```

If needed, update the data source path in Power BI Desktop.

---

## 📥 Dataset

This project uses the **Online Retail dataset**.

Download it from:
https://archive.ics.uci.edu/ml/datasets/Online+Retail

After downloading, place the file in:

```
data/raw/Online_Retail.csv
```

---

## 🚀 How to Run the Pipeline

### 1. Install dependencies

```bash
pip install pandas duckdb matplotlib
```

### 2. Execute pipeline

```bash
./run_pipeline.sh
```

Or:

```bash
python run_pipeline.py
```

---

## 📓 Notebook (EDA)

The notebook is used for:

* data exploration
* data validation
* business insights

Location:

```
notebooks/eda_online_retail.ipynb
```

---

## 🧠 Key Features

* End-to-end data pipeline
* Layered architecture (raw → processed → staging → DW)
* DuckDB-based transformations
* Star schema data modeling
* Power BI integration
* Logging and execution tracking
* Reproducible and modular design

---

## 📌 Notes

* Raw dataset is not included to keep the repository lightweight
* The pipeline is designed to be reproducible using relative paths
* Power BI may require updating the data source depending on the local environment

---

## 🎯 Author

**Lina Marcela Franco Montes**
Data Engineering Portfolio Project
