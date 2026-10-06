import duckdb
import pandas as pd
import pytest

import scripts.data_ingestion as ingestion


def build_valid_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "invoiceno": ["10001", "10002"],
            "stockcode": ["A001", "A002"],
            "description": ["Product A", "Product B"],
            "quantity": [2, 3],
            "invoicedate": [
                "2026-01-01 10:00:00",
                "2026-01-02 11:00:00",
            ],
            "unitprice": [10.0, 20.0],
            "customerid": ["C001", "C002"],
            "country": ["United Kingdom", "France"],
        }
    )


def test_data_quality_flow_passes_and_persists_metrics(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_quality.db"

    monkeypatch.setattr(
        ingestion,
        "DW_DB_PATH",
        test_db,
    )

    df = build_valid_dataframe()

    metrics = ingestion.calculate_data_quality_metrics(df)

    run_id = "integration-pass"

    ingestion.save_quality_metrics(
        metrics,
        run_id,
    )

    ingestion.enforce_quality_gate(metrics)

    con = duckdb.connect(str(test_db))

    try:
        persisted_metrics = con.execute(
            """
            SELECT
                rule,
                status
            FROM data_quality_metrics
            WHERE run_id = ?
            ORDER BY rule;
            """,
            [run_id],
        ).fetchall()

    finally:
        con.close()

    assert len(persisted_metrics) == 7

    assert all(
        status == "PASS"
        for _, status in persisted_metrics
    )


def test_critical_failure_is_persisted_before_gate_stops_pipeline(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_quality_failure.db"

    monkeypatch.setattr(
        ingestion,
        "DW_DB_PATH",
        test_db,
    )

    df = build_valid_dataframe()

    df.loc[
        0,
        "invoiceno",
    ] = None

    metrics = ingestion.calculate_data_quality_metrics(df)

    run_id = "integration-critical-failure"

    ingestion.save_quality_metrics(
        metrics,
        run_id,
    )

    with pytest.raises(
        RuntimeError,
        match="Critical data quality rules failed",
    ):
        ingestion.enforce_quality_gate(metrics)

    con = duckdb.connect(str(test_db))

    try:
        result = con.execute(
            """
            SELECT
                failed_rows,
                status
            FROM data_quality_metrics
            WHERE run_id = ?
              AND rule = 'invoiceno_not_null';
            """,
            [run_id],
        ).fetchone()

    finally:
        con.close()

    assert result is not None

    failed_rows, status = result

    assert failed_rows == 1
    assert status == "FAIL"


def test_non_critical_failure_is_persisted_without_stopping_pipeline(
    tmp_path,
    monkeypatch,
):
    test_db = tmp_path / "test_quality_non_critical.db"

    monkeypatch.setattr(
        ingestion,
        "DW_DB_PATH",
        test_db,
    )

    df = build_valid_dataframe()

    df.loc[
        0,
        "customerid",
    ] = None

    metrics = ingestion.calculate_data_quality_metrics(df)

    run_id = "integration-non-critical-failure"

    ingestion.save_quality_metrics(
        metrics,
        run_id,
    )

    ingestion.enforce_quality_gate(metrics)

    con = duckdb.connect(str(test_db))

    try:
        result = con.execute(
            """
            SELECT
                failed_rows,
                status
            FROM data_quality_metrics
            WHERE run_id = ?
              AND rule = 'customerid_not_null';
            """,
            [run_id],
        ).fetchone()

    finally:
        con.close()

    assert result is not None

    failed_rows, status = result

    assert failed_rows == 1