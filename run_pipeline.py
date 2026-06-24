from pathlib import Path
import subprocess
import logging
import sys
import time


# =========================================================
# CONFIGURATION
# =========================================================
BASE_DIR = Path(__file__).resolve().parent

SCRIPTS_DIR = BASE_DIR / "scripts"
LOG_PATH = BASE_DIR / "logs" / "pipeline.log"

PIPELINE_STEPS = [
    {
        "name": "Data Ingestion",
        "script": SCRIPTS_DIR / "data_ingestion.py"
    },
    {
        "name": "Data Transformation",
        "script": SCRIPTS_DIR / "transformations.py"
    },
    {
        "name": "Build Data Warehouse",
        "script": SCRIPTS_DIR / "build_datawarehouse.py"
    },
   {
        "name": "Generate Report",
        "script": SCRIPTS_DIR / "generate_report.py"
    },
]


# =========================================================
# LOGGER
# =========================================================
def setup_logger() -> None:
    """Configure pipeline logging."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )


# =========================================================
# PIPELINE EXECUTION
# =========================================================
def run_step(step_name: str, script_path: Path) -> None:
    """Run a pipeline step using subprocess."""
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    logging.info("=" * 70)
    logging.info(f"Starting step: {step_name}")
    logging.info(f"Running script: {script_path}")

    start_time = time.perf_counter()

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True
    )

    end_time = time.perf_counter()
    duration = end_time - start_time

    if result.stdout:
        logging.info(f"{step_name} stdout:\n{result.stdout}")

    if result.stderr:
        logging.error(f"{step_name} stderr:\n{result.stderr}")

    if result.returncode != 0:
        logging.error(f"Step failed: {step_name}")
        logging.error(f"Execution time before failure: {duration:.2f} seconds")
        raise RuntimeError(f"Pipeline stopped because '{step_name}' failed.")

    logging.info(f"Step completed successfully: {step_name}")
    logging.info(f"Execution time: {duration:.2f} seconds")


def main() -> None:
    """Orchestrate the full pipeline in sequence."""
    setup_logger()

    logging.info("=" * 70)
    logging.info("Starting Online Retail pipeline")

    pipeline_start = time.perf_counter()

    try:
        for step in PIPELINE_STEPS:
            run_step(step["name"], step["script"])

        pipeline_end = time.perf_counter()
        total_duration = pipeline_end - pipeline_start

        logging.info("=" * 70)
        logging.info("Pipeline completed successfully")
        logging.info(f"Total pipeline execution time: {total_duration:.2f} seconds")

    except Exception as e:
        pipeline_end = time.perf_counter()
        total_duration = pipeline_end - pipeline_start

        logging.error("=" * 70)
        logging.error(f"Pipeline failed: {e}")
        logging.error(f"Total execution time before failure: {total_duration:.2f} seconds")
        raise


if __name__ == "__main__":
    main()