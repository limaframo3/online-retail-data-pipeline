import pandas as pd
import pytest

from scripts.data_ingestion import (
    standardize_column_names,
    validate_schema,
)


def test_validate_schema_passes_with_required_columns():
    df = pd.DataFrame({
        "InvoiceNo": ["536365"],
        "StockCode": ["85123A"],
        "Description": ["tests product"],
        "Quantity": [6],
        "InvoiceDate": ["2010-12-01 08:26:00"],
        "UnitPrice": [2.55],
        "CustomerID": [17850],
        "Country": ["United Kingdom"],
    })

    df = standardize_column_names(df)

    validate_schema(df)


def test_validate_schema_fails_when_required_column_is_missing():
    df = pd.DataFrame({
        "InvoiceNo": ["536365"],
        "StockCode": ["85123A"],
        "Description": ["tests product"],
        "Quantity": [6],
        "UnitPrice": [2.55],
        "CustomerID": [17850],
        "Country": ["United Kingdom"],
    })

    df = standardize_column_names(df)

    with pytest.raises(
        ValueError,
        match="Missing required columns: invoicedate",
    ):
        validate_schema(df)