from scripts.data_quality import (
    evaluate_rule,
    has_critical_failure,
)

import pytest
from scripts.data_ingestion import enforce_quality_gate


def test_evaluate_rule_passes_with_zero_failures():
    metric = evaluate_rule(
        rule_name="quantity_positive",
        failed_rows=0,
        total_rows=1000,
    )

    assert metric["status"] == "PASS"
    assert metric["failure_percentage"] == 0.0
    assert metric["threshold_percentage"] == 0.30


def test_quantity_rule_passes_within_threshold():
    metric = evaluate_rule(
        rule_name="quantity_positive",
        failed_rows=2,
        total_rows=1000,
    )

    assert metric["failure_percentage"] == 0.2
    assert metric["status"] == "PASS"


def test_quantity_rule_fails_above_threshold():
    metric = evaluate_rule(
        rule_name="quantity_positive",
        failed_rows=4,
        total_rows=1000,
    )

    assert metric["failure_percentage"] == 0.4
    assert metric["status"] == "FAIL"


def test_evaluate_rule_passes_within_customerid_threshold():
    metric = evaluate_rule(
        rule_name="customerid_not_null",
        failed_rows=250,
        total_rows=1000,
    )

    assert metric["status"] == "PASS"
    assert metric["failure_percentage"] == 25.0
    assert metric["threshold_percentage"] == 30.0


def test_evaluate_rule_fails_above_customerid_threshold():
    metric = evaluate_rule(
        rule_name="customerid_not_null",
        failed_rows=310,
        total_rows=1000,
    )

    assert metric["status"] == "FAIL"
    assert metric["failure_percentage"] == 31.0


def test_critical_failure_returns_true():
    metrics = [
        {
            "rule": "invoicedate_not_null",
            "failed_rows": 1,
            "failure_percentage": 0.1,
            "threshold_percentage": 0.0,
            "status": "FAIL",
        }
    ]

    assert has_critical_failure(metrics) is True


def test_non_critical_failure_returns_false():
    metrics = [
        {
            "rule": "quantity_positive",
            "failed_rows": 4,
            "failure_percentage": 0.4,
            "threshold_percentage": 0.30,
            "status": "FAIL",
        }
    ]

    assert has_critical_failure(metrics) is False


def test_quality_gate_stops_pipeline_on_critical_failure():
    metrics = [
        {
            "rule": "invoicedate_not_null",
            "failed_rows": 1,
            "failure_percentage": 0.1,
            "threshold_percentage": 0.0,
            "status": "FAIL",
        }
    ]

    with pytest.raises(
        RuntimeError,
        match="invoicedate_not_null",
    ):
        enforce_quality_gate(metrics)


def test_quality_gate_allows_non_critical_failure():
    metrics = [
        {
            "rule": "quantity_positive",
            "failed_rows": 10,
            "failure_percentage": 0.5,
            "threshold_percentage": 0.30,
            "status": "FAIL",
        }
    ]

    enforce_quality_gate(metrics)

def test_failed_metric_can_be_persisted_before_quality_gate(tmp_path, monkeypatch):
        import duckdb
        import scripts.data_ingestion as ingestion

        test_db = tmp_path / "test_quality.db"

        monkeypatch.setattr(
            ingestion,
            "DW_DB_PATH",
            test_db,
        )

        metrics = [
            {
                "rule": "invoicedate_not_null",
                "failed_rows": 1,
                "failure_percentage": 0.1,
                "threshold_percentage": 0.0,
                "status": "FAIL",
            }
        ]

        run_id = "test-failed-run"

        ingestion.save_quality_metrics(
            metrics,
            run_id,
        )

        with pytest.raises(
                RuntimeError,
                match="invoicedate_not_null",
        ):
            ingestion.enforce_quality_gate(metrics)

        con = duckdb.connect(str(test_db))

        persisted = con.execute("""
            SELECT
                run_id,
                rule,
                status
            FROM data_quality_metrics;
        """).fetchone()

        con.close()

        assert persisted == (
            "test-failed-run",
            "invoicedate_not_null",
            "FAIL",
        )

def test_quality_metrics_do_not_duplicate_same_run_id(tmp_path, monkeypatch):
    import duckdb
    import scripts.data_ingestion as ingestion

    test_db = tmp_path / "test_quality.db"

    monkeypatch.setattr(
        ingestion,
        "DW_DB_PATH",
        test_db,
    )

    metrics = [
        {
            "rule": "quantity_positive",
            "failed_rows": 1,
            "failure_percentage": 0.1,
            "threshold_percentage": 0.3,
            "status": "PASS",
        }
    ]

    run_id = "same-run"

    ingestion.save_quality_metrics(metrics, run_id)
    ingestion.save_quality_metrics(metrics, run_id)

    con = duckdb.connect(str(test_db))

    count = con.execute("""
        SELECT COUNT(*)
        FROM data_quality_metrics
        WHERE run_id = ?;
    """, [run_id]).fetchone()[0]

    con.close()

    assert count == 1