#!/usr/bin/env bash
# Install (or update) the sportsticker systemd service on the Raspberry Pi.
#
#   sudo ./deploy/install.sh
#
# Idempotent: re-run it after `git pull` to reinstall the package, re-validate
# config.yaml, refresh the unit file and restart the service.
#
# Overrides (environment variables). The unit file is rewritten to match:
#   TICKER_HOME  repo checkout         (default /home/charlie/sportsticker)
#   TICKER_VENV  virtualenv directory  (default /home/charlie/ticker-venv)

set -euo pipefail

readonly DEFAULT_HOME="/home/charlie/sportsticker"
readonly DEFAULT_VENV="/home/charlie/ticker-venv"
TICKER_HOME="${TICKER_HOME:-$DEFAULT_HOME}"
TICKER_VENV="${TICKER_VENV:-$DEFAULT_VENV}"

readonly SERVICE="ticker.service"
readonly UNIT_SRC="$TICKER_HOME/deploy/$SERVICE"
readonly UNIT_DST="/etc/systemd/system/$SERVICE"
readonly PY="$TICKER_VENV/bin/python"
readonly PIP="$TICKER_VENV/bin/pip"

die() {
    echo "error: $*" >&2
    exit 1
}

step() {
    echo
    echo "==> $*"
}

# Escape a string for use as the replacement part of `sed s|...|...|`.
sed_escape() {
    printf '%s' "$1" | sed -e 's/[\/&|]/\\&/g'
}

if [[ $EUID -ne 0 ]]; then
    die "must run as root: sudo $0"
fi

[[ -f "$TICKER_HOME/pyproject.toml" ]] || die "no sportsticker checkout at $TICKER_HOME (set TICKER_HOME)"
[[ -f "$TICKER_HOME/config.yaml" ]] || die "missing $TICKER_HOME/config.yaml"
[[ -f "$UNIT_SRC" ]] || die "missing unit file $UNIT_SRC"

step "Checking the virtualenv at $TICKER_VENV"
if [[ ! -x "$PY" ]]; then
    die "no virtualenv at $TICKER_VENV. Create it as charlie first:
    python3 -m venv $TICKER_VENV
  then build the rpi-rgb-led-matrix bindings into it (README, Raspberry Pi setup)."
fi

if ! "$PY" -c 'import rgbmatrix' >/dev/null 2>&1; then
    die "cannot import rgbmatrix from $PY. The service needs the rpi-rgb-led-matrix
Python bindings in the venv. Install them (README, Raspberry Pi setup):
    sudo apt install python-dev-is-python3 python3-pil cython3 build-essential
    $PIP install git+https://github.com/hzeller/rpi-rgb-led-matrix
then re-run this script."
fi
echo "ok: rgbmatrix imports"

step "Installing sportsticker into $TICKER_VENV"
"$PIP" install --quiet --disable-pip-version-check -e "$TICKER_HOME"

step "Validating $TICKER_HOME/config.yaml"
if ! (cd "$TICKER_HOME" && "$PY" -m sportsticker run --config "$TICKER_HOME/config.yaml" --check-config); then
    die "config check failed; fix config.yaml and re-run"
fi

step "Installing $UNIT_DST"
tmp_unit="$(mktemp)"
trap 'rm -f "$tmp_unit"' EXIT
sed \
    -e "s|/home/charlie/sportsticker|$(sed_escape "$TICKER_HOME")|g" \
    -e "s|/home/charlie/ticker-venv|$(sed_escape "$TICKER_VENV")|g" \
    "$UNIT_SRC" > "$tmp_unit"
install -m 0644 "$tmp_unit" "$UNIT_DST"

if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "$UNIT_DST" || echo "warning: systemd-analyze reported problems with $UNIT_DST" >&2
fi

step "Enabling and (re)starting $SERVICE"
systemctl daemon-reload
systemctl enable "$SERVICE"
# restart rather than `enable --now`, so a re-run picks up new code and config.
systemctl restart "$SERVICE"

sleep 3
step "Status"
systemctl --no-pager status "$SERVICE" || true
echo
echo "Follow the logs with: journalctl -u $SERVICE -f"
