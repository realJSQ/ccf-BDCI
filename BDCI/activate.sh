# Usage: source /home/jsqke/lpyproject/BDCI/activate.sh
BDCI_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$BDCI_ROOT/.venv/bin/activate"
# The shared virtual environment may have another editable JiuwenSwarm checkout.
# Prefer this repository's source, including its research budget rail.
export PYTHONPATH="$BDCI_ROOT/jiuwenswarm${PYTHONPATH:+:$PYTHONPATH}"
export JIUWENSWARM_HOME="$BDCI_ROOT/runtime"
export JIUWENSWARM_DATA_DIR="$JIUWENSWARM_HOME/.jiuwenswarm"
export UV_CACHE_DIR="$BDCI_ROOT/.cache/uv"
export FRONTEND_HOST=127.0.0.1
export GATEWAY_HOST=127.0.0.1
export WEB_HOST=127.0.0.1
export AGENT_SERVER_HOST=127.0.0.1
