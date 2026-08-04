#!/usr/bin/env bash
# Run this ON the bastion/jumpbox, after copying awsx-offline-bundle.tar.gz
# there. Requires no internet access - everything needed is already inside
# the tarball's vendor/ directory.
#
# Usage:
#   ./install_offline.sh [install-dir]
#
# Default install-dir: /opt/awsx (falls back to ~/awsx if /opt isn't writable)

set -euo pipefail

BUNDLE="awsx-offline-bundle.tar.gz"
INSTALL_DIR="${1:-/opt/awsx}"

if [ ! -f "$BUNDLE" ]; then
  echo "Can't find $BUNDLE in the current directory." >&2
  exit 1
fi

if ! mkdir -p "$INSTALL_DIR" 2>/dev/null || [ ! -w "$INSTALL_DIR" ]; then
  INSTALL_DIR="$HOME/awsx"
  mkdir -p "$INSTALL_DIR"
  echo "No write access to the requested path; installing to $INSTALL_DIR instead."
fi

tar -xzf "$BUNDLE" -C "$INSTALL_DIR"

# Shared, multi-user-safe bin wrappers. These just run the vendored copy
# directly via `python3 -m awsx.cli` - no pip install, no site-packages
# writes, nothing that requires root.
mkdir -p "$INSTALL_DIR/bin"

cat > "$INSTALL_DIR/bin/awsx" << 'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 -m awsx.cli "$@"
EOF

cat > "$INSTALL_DIR/bin/awsx-ro" << 'EOF'
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AWSX_READONLY=1
exec python3 -c "from awsx.cli import main_readonly; main_readonly()" "$@"
EOF

chmod +x "$INSTALL_DIR/bin/awsx" "$INSTALL_DIR/bin/awsx-ro"

echo
echo "Installed to: $INSTALL_DIR"
echo
echo "Add this to /etc/profile.d/awsx.sh (all users) or each user's shell rc:"
echo "  export PYTHONPATH=\"$INSTALL_DIR:\$PYTHONPATH\""
echo "  export PATH=\"$INSTALL_DIR/bin:\$PATH\""
echo
echo "Then test with:"
echo "  awsx whoami"
echo "  awsx list-recipes"
echo
echo "To hand a user the query-only edition instead, only put"
echo "$INSTALL_DIR/bin/awsx-ro on their PATH (and restrict shell access so"
echo "they can't reach the vendored python package directly - see the"
echo "README's read-only mode caveat for why that matters)."
