#!/bin/zsh
# Build the Lambda zip: app code + Linux (x86_64, CPython 3.12) wheels. boto3 comes with the Lambda runtime.
set -eu
cd "${0:A:h}/../.."
rm -rf infra/aws/build && mkdir -p infra/aws/build
python3 -m pip install -q --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 \
  --only-binary=:all: --target infra/aws/build fastapi jinja2 python-multipart "mangum>=0.19"
cp -R app templates lambda_handler.py infra/aws/build/
mkdir -p infra/aws/build/evals/results && cp evals/__init__.py evals/metrics.py infra/aws/build/evals/ && cp evals/results/published.json infra/aws/build/evals/results/
mkdir -p infra/aws/build/data && cp data/voicedesk.db infra/aws/build/data/ 2>/dev/null || true
find infra/aws/build -name '__pycache__' -prune -exec rm -rf {} +
echo "build ready: $(du -sh infra/aws/build | cut -f1)"
