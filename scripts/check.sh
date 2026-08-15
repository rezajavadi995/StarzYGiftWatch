#!/usr/bin/env bash
set -euo pipefail
python -m compileall -q starzygiftwatch tests
pytest -q
bash -n install.sh
bash tests/wrapper_test.sh
bash tests/install_idempotency_test.sh
