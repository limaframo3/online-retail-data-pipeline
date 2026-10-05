from copy import deepcopy

import pytest

from run_pipeline import (
    CONFIG,
    get_env,
    get_environment_config,
)


REQUIRED_ENVIRONMENT_KEYS = {
    "database",
    "staging_database",
    "processed_parquet",
    "quarantine_parquet",
    "powerbi_output",
    "report_output",
    "log_level",
}


def test_default_environment_is_dev(monkeypatch):
    monkeypatch.delenv(
        "ONLINE_RETAIL_ENV",
        raising=False,
    )

    environment = get_env(
        "ONLINE_RETAIL_ENV",
        CONFIG["pipeline"]["environment"],
    )

    assert environment == "dev"


def test_environment_can_be_overridden_to_test(monkeypatch):
    monkeypatch.setenv(
        "ONLINE_RETAIL_ENV",
        "test",
    )

    environment = get_env(
        "ONLINE_RETAIL_ENV",
        CONFIG["pipeline"]["environment"],
    )

    assert environment == "test"


def test_invalid_environment_raises_error():
    with pytest.raises(
        RuntimeError,
        match="Invalid environment",
    ):
        get_environment_config(
            CONFIG,
            "invalid",
        )


@pytest.mark.parametrize(
    "environment",
    [
        "dev",
        "test",
        "prod",
    ],
)
def test_environment_contains_required_keys(environment):
    environment_config = get_environment_config(
        CONFIG,
        environment,
    )

    assert REQUIRED_ENVIRONMENT_KEYS.issubset(
        environment_config.keys()
    )


def test_environment_database_paths_are_isolated():
    dev_config = get_environment_config(
        CONFIG,
        "dev",
    )

    test_config = get_environment_config(
        CONFIG,
        "test",
    )

    prod_config = get_environment_config(
        CONFIG,
        "prod",
    )

    database_paths = {
        dev_config["database"],
        test_config["database"],
        prod_config["database"],
    }

    staging_database_paths = {
        dev_config["staging_database"],
        test_config["staging_database"],
        prod_config["staging_database"],
    }

    assert len(database_paths) == 3
    assert len(staging_database_paths) == 3


def test_environment_output_paths_are_isolated():
    environments = [
        get_environment_config(
            CONFIG,
            environment,
        )
        for environment in (
            "dev",
            "test",
            "prod",
        )
    ]

    processed_paths = {
        config["processed_parquet"]
        for config in environments
    }

    quarantine_paths = {
        config["quarantine_parquet"]
        for config in environments
    }

    powerbi_paths = {
        config["powerbi_output"]
        for config in environments
    }

    report_paths = {
        config["report_output"]
        for config in environments
    }

    assert len(processed_paths) == 3
    assert len(quarantine_paths) == 3
    assert len(powerbi_paths) == 3
    assert len(report_paths) == 3


def test_missing_environment_configuration_raises_error():
    incomplete_config = deepcopy(CONFIG)

    del incomplete_config["environments"]["test"]

    with pytest.raises(
        RuntimeError,
        match="Invalid environment",
    ):
        get_environment_config(
            incomplete_config,
            "test",
        )


def test_environment_missing_required_key_is_detected():
    incomplete_config = deepcopy(CONFIG)

    del incomplete_config[
        "environments"
    ]["dev"]["database"]

    dev_config = get_environment_config(
        incomplete_config,
        "dev",
    )

    missing_keys = (
        REQUIRED_ENVIRONMENT_KEYS
        - dev_config.keys()
    )

    assert "database" in missing_keys