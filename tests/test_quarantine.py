import pandas as pd

from scripts.data_ingestion import (
    convert_data_types,
    split_valid_and_quarantine,
)


def test_invalid_quantity_goes_to_quarantine():
    df = pd.DataFrame({
        "invoiceno": ["536365", "536366"],
        "stockcode": ["85123A", "71053"],
        "description": ["Product A", "Product B"],
        "quantity": ["6", "invalid"],
        "invoicedate": [
            "2010-12-01 08:26:00",
            "2010-12-01 08:28:00",
        ],
        "unitprice": ["2.55", "3.39"],
        "customerid": ["17850", "17850"],
        "country": ["United Kingdom", "United Kingdom"],
    })

    df = convert_data_types(df)

    valid_df, quarantine_df = split_valid_and_quarantine(df)

    assert len(valid_df) == 1
    assert len(quarantine_df) == 1

    assert valid_df.iloc[0]["invoiceno"] == "536365"
    assert quarantine_df.iloc[0]["invoiceno"] == "536366"

    assert pd.isna(
        quarantine_df.iloc[0]["quantity"]
    )

def test_invalid_invoicedate_goes_to_quarantine():
        df = pd.DataFrame({
            "invoiceno": ["536365", "536366"],
            "stockcode": ["85123A", "71053"],
            "description": ["Product A", "Product B"],
            "quantity": ["6", "2"],
            "invoicedate": [
                "2010-12-01 08:26:00",
                "not-a-date",
            ],
            "unitprice": ["2.55", "3.39"],
            "customerid": ["17850", "17850"],
            "country": ["United Kingdom", "United Kingdom"],
        })

        df = convert_data_types(df)

        valid_df, quarantine_df = split_valid_and_quarantine(df)

        assert len(valid_df) == 1
        assert len(quarantine_df) == 1

        assert valid_df.iloc[0]["invoiceno"] == "536365"
        assert quarantine_df.iloc[0]["invoiceno"] == "536366"

        assert pd.isna(
            quarantine_df.iloc[0]["invoicedate"]
        )