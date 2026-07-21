#!/bin/bash

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==============================================="
echo "Running pipeline (Bash wrapper)"
echo "Timestamp: $(date)"
echo "==============================================="

cd "$PROJECT_DIR" || exit 1

"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/run_pipeline.py"
STATUS=$?

if [ "$STATUS" -ne 0 ]; then
    echo "Pipeline failed ❌"
    exit 1
fi

echo "Pipeline completed successfully ✅"