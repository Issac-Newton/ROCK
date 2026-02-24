#!/bin/bash
set -uo pipefail

# Reproduce the output-loss bug when run under SDK's arun nohup mode.
# Key ingredients from the real swebench run-tests.sh:
#   1. exec > >(tee ...) process substitution that creates an async pipe subprocess
#   2. Large volume of output during the tee redirect to fill pipe buffers
#   3. exec 1>&3 2>&4 to restore stdout
#   4. A final command run via a child process (simulating uv run parser.py)

echo "=== Phase 1: Normal output ==="

# --- Start tee redirect (like run-tests.sh) ---
LOG_FILE=$(mktemp)
export LOG_FILE
exec 3>&1 4>&2
exec > >(tee "$LOG_FILE") 2>&1

# Generate large output to fill pipe buffers (simulates verbose test output)
for i in $(seq 1 500); do
    echo "test output line $i: $(head -c 200 /dev/urandom | base64 | head -c 100)"
done

# --- Restore stdout (like run-tests.sh) ---
exec 1>&3 2>&4

# Simulate uv run parser.py: run final output via a child process, not inline echo.
# This is critical — the real bug happens because the child process writes to the
# restored fd while the tee subprocess is still draining its pipe buffer.
python3 -c "
import time
time.sleep(0.1)
print('SWEBench results starts here')
print('PASSED')
print('SWEBench results ends here')
"
