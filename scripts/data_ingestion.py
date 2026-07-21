from pathlib import Path
import logging
import pandas as pd
import pycountry
import json


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
    CONFIG = json.load(config_file)


EXCEL_PATH = BASE_DIR / CONFIG["paths"]["excel"]
INPUT_PATH = BASE_DIR / CONFIG["paths"]["input"]
OUTPUT_PATH = BASE_DIR / CONFIG["paths"]["output"]
LOG_PATH = BASE_DIR / CONFIG["paths"]["log"]


# =========================================================
# LOGGER
# =========================================================
def setup_logger() -> None:
    """Configure logging for the ingestion process."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )


# =========================================================
# EXTRACT
# =========================================================

def load_data(excel_path: Path, csv_output_path: Path) -> pd.DataFrame:
    """
    Load Online Retail Excel dataset,
    convert it to CSV,
    and return DataFrame.
    """

    logging.info(f"Reading Excel file: {excel_path}")

    # Read Excel file
    df = pd.read_excel(excel_path)

    logging.info("Excel file loaded successfully.")

    # Export raw CSV
    df.to_csv(csv_output_path, index=False, encoding="utf-8")

    logging.info(f"Raw CSV created at: {csv_output_path}")

    # Read CSV file
    df = pd.read_csv(csv_output_path, encoding="utf-8")

    logging.info("CSV file loaded successfully.")

    return df

# =========================================================
# TRANSFORM
# =========================================================
def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names."""
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    return df


def trim_text_values(df: pd.DataFrame) -> pd.DataFrame:
    """Remove leading and trailing spaces from text columns."""
    df = df.copy()

    for col in df.columns:
        if df[col].dtype == "object" or str(df[col].dtype).startswith("string"):
            df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

    return df


def normalize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and standardize selected text columns."""
    df = df.copy()

    text_cols = ["invoiceno", "stockcode", "description", "country"]

    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype("string")
            df[col] = df[col].str.strip()
            df[col] = df[col].str.replace(r"\s+", " ", regex=True)
            df[col] = df[col].fillna("N/A")

    if "description" in df.columns:
        df["description"] = df["description"].str.title()

    return df


def standardize_country(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize country values and remove invalid entries."""
    df = df.copy()
    invalid = ["unspecified", "european community", "channel islands"]

    def normalize_country(country):
        try:
            return pycountry.countries.lookup(str(country)).name
        except Exception:
            return country

    if "country" in df.columns:
        df["country"] = df["country"].apply(normalize_country)
        df["country"] = df["country"].astype("string").str.strip()
        df = df[~df["country"].str.lower().isin(invalid)]
        df["country"] = df["country"].fillna("N/A").str.title()

    return df


def convert_data_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert core columns to expected data types."""
    df = df.copy()

    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")

    if "unitprice" in df.columns:
        df["unitprice"] = pd.to_numeric(df["unitprice"], errors="coerce")

    if "customerid" in df.columns:
        df["customerid"] = (
            pd.to_numeric(df["customerid"], errors="coerce")
            .astype("Int64")
            .astype("string")
            .fillna("N/A")
        )

    if "invoicedate" in df.columns:
        df["invoicedate"] = pd.to_datetime(df["invoicedate"], errors="coerce")

    return df


def remove_exact_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove fully duplicated rows."""
    df = df.copy()
    return df.drop_duplicates()


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Reorder columns for a cleaner final dataset."""
    preferred_order = [
        "invoiceno",
        "stockcode",
        "description",
        "quantity",
        "unitprice",
        "invoicedate",
        "customerid",
        "country",
    ]

    existing_cols = [col for col in preferred_order if col in df.columns]
    remaining_cols = [col for col in df.columns if col not in existing_cols]

    return df[existing_cols + remaining_cols]


# =========================================================
# VALIDATION
# =========================================================
def log_data_quality(df: pd.DataFrame) -> None:
    """Log a concise data quality summary."""
    logging.info("Generating data quality summary")
    logging.info(f"Rows: {len(df):,}")
    logging.info(f"Columns: {df.shape[1]}")
    logging.info(f"Data types:\n{df.dtypes}")
    logging.info(f"Missing values:\n{df.isna().sum()}")
    logging.info(f"Exact duplicates: {df.duplicated().sum()}")

    if "quantity" in df.columns:
        logging.info(f"Negative quantity rows: {int((df['quantity'] < 0).sum())}")
        logging.info(f"Zero quantity rows: {int((df['quantity'] == 0).sum())}")

    if "unitprice" in df.columns:
        logging.info(f"Negative unitprice rows: {int((df['unitprice'] < 0).sum())}")
        logging.info(f"Zero unitprice rows: {int((df['unitprice'] == 0).sum())}")

    if "country" in df.columns:
        logging.info(f"Unique countries: {df['country'].nunique(dropna=False)}")


# =========================================================
# LOAD
# =========================================================
def save_data(df: pd.DataFrame, output_path: Path) -> None:
    """Save cleaned dataset to CSV."""
    df.to_csv(output_path, index=False)
    logging.info(f"Cleaned file saved to: {output_path}")


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    """Execute ingestion and cleaning workflow."""
    setup_logger()
    logging.info("Starting ingestion pipeline")

    try:
        df = load_data(EXCEL_PATH, INPUT_PATH)
        df = standardize_column_names(df)
        df = trim_text_values(df)
        df = normalize_text_columns(df)
        df = standardize_country(df)
        df = convert_data_types(df)
        df = remove_exact_duplicates(df)
        df = reorder_columns(df)

        log_data_quality(df)
        save_data(df, OUTPUT_PATH)

        logging.info("Ingestion pipeline completed successfully")

    except Exception as e:
        logging.error(f"Ingestion pipeline failed: {e}")
        raise


if __name__ == "__main__":
    main()