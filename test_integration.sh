#!/bin/bash
# Integration test script for Locomotive
# Requires: dummy service running on localhost:8000

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Locomotive Integration Test ==="
echo ""

# Check if dummy service is running
echo "1. Checking if dummy service is running..."
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✓ Dummy service is running"
else
    echo "   ✗ Dummy service not running!"
    echo ""
    echo "   Start it with:"
    echo "   cd ../test-backend-for-ci-lib && python main.py"
    echo "   or:"
    echo "   cd ../test-backend-for-ci-lib && docker-compose up -d"
    exit 1
fi

# Check locust is installed
echo ""
echo "2. Checking locust installation..."
if command -v locust &> /dev/null; then
    echo "   ✓ Locust is installed: $(locust --version)"
else
    echo "   ✗ Locust not installed!"
    echo "   Run: pip install locust"
    exit 1
fi

# Clean previous artifacts
echo ""
echo "3. Cleaning previous artifacts..."
rm -rf artifacts/
echo "   ✓ Cleaned"

# Test 1: Generate locustfile from scenario
echo ""
echo "4. Testing locustfile generation..."
python3 -c "
from locomotive.scenario import generate_locustfile
from locomotive.config import load_config
from pathlib import Path

config = load_config('loconfig.example-scenario.json')
scenario = config['scenario']
target = config['load']

output = generate_locustfile(scenario, target, Path('artifacts/test-gen'))
print(f'   ✓ Generated: {output}')
"

# Test 2: Run short load test
echo ""
echo "5. Running load test (30s)..."
python3 -m locomotive ci \
    --config loconfig.example-scenario.json \
    --run-time 30s \
    --users 10 \
    --spawn-rate 5 \
    --set-baseline

echo ""
echo "6. Checking artifacts..."
if [ -f "artifacts/runs/local/metrics.json" ]; then
    echo "   ✓ metrics.json created"
    echo "   Metrics:"
    python3 -c "
import json
m = json.load(open('artifacts/runs/local/metrics.json'))
for k, v in m.items():
    if v is not None:
        print(f'     {k}: {v}')
"
else
    echo "   ✗ metrics.json not found"
    exit 1
fi

if [ -f "artifacts/runs/local/report.html" ]; then
    echo "   ✓ report.html created"
else
    echo "   ✗ report.html not found"
fi

if [ -f "artifacts/baseline.json" ]; then
    echo "   ✓ baseline.json created"
else
    echo "   ✗ baseline.json not found"
fi

echo ""
echo "=== All tests passed! ==="
echo ""
echo "Report: artifacts/runs/local/report.html"
