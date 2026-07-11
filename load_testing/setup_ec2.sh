#!/usr/bin/env bash
# One-time bootstrap for the EC2 load generator (Amazon Linux 2023).
#
# Run this once after connecting via EC2 Instance Connect.
# It does NOT install the AWS CLI or configure credentials: the load generator
# only needs to reach a public HTTPS endpoint. All AWS API calls (CloudWatch,
# sam deploy) happen on your laptop.

set -euo pipefail

echo "=== Installing system packages ==="
sudo dnf install -y python3-pip git gcc python3-devel

echo "=== Installing Locust ==="
pip3 install --user locust

# pip --user installs to ~/.local/bin, which is not on PATH by default
if ! grep -q '.local/bin' ~/.bashrc 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi
export PATH="$HOME/.local/bin:$PATH"

echo "=== Verifying ==="
python3 --version
locust --version

echo ""
echo "Setup complete. Next:"
echo "  source ~/.bashrc"
echo "  git clone https://github.com/Daniel200273/minilm-lambda-eval.git"
echo "  cd minilm-lambda-eval"
echo "  export HOST=\"https://<api-id>.execute-api.us-east-1.amazonaws.com\""
echo "  curl -s -X POST \"\$HOST/onnx/search\" -H 'Content-Type: application/json' \\"
echo "       -d '{\"query\":\"test\",\"top_k\":5}'"
