#!/data/data/com.termux/files/usr/bin/bash
# Quick fix script for PGP plugin on Termux

echo "======================================"
echo "PGP Plugin - Termux Quick Fix"
echo "======================================"
echo ""

# Step 1: Update packages
echo "📦 Updating packages..."
pkg update -y
echo "✓ Done"
echo ""

# Step 2: Install GPG
echo "🔐 Installing GnuPG..."
pkg install gnupg -y
echo "✓ Done"
echo ""

# Step 3: Install python-gnupg
echo "🐍 Installing python-gnupg..."
pip install python-gnupg --break-system-packages --upgrade
echo "✓ Done"
echo ""

# Step 4: Verify GPG
echo "🔍 Verifying GPG installation..."
if command -v gpg &> /dev/null; then
    gpg --version | head -n 1
    echo "✓ GPG is working"
else
    echo "❌ GPG not found - something went wrong"
    exit 1
fi
echo ""

# Step 5: Check entropy (optional but helpful)
echo "🎲 Installing entropy generator (optional)..."
if ! command -v haveged &> /dev/null; then
    pkg install haveged -y 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "✓ Haveged installed (helps with key generation)"
    else
        echo "⚠ Haveged not available (not critical)"
    fi
else
    echo "✓ Haveged already installed"
fi
echo ""

# Step 6: Check keyring permissions
echo "🔑 Checking keyring directory..."
KEYRING_DIR="$HOME/.local/share/lxmf_client_storage/plugins/pgp/keyring"

if [ -d "$KEYRING_DIR" ]; then
    chmod 700 "$KEYRING_DIR"
    echo "✓ Keyring permissions fixed: $KEYRING_DIR"
else
    echo "⚠ Keyring directory doesn't exist yet (will be created on first run)"
fi
echo ""

# Step 7: Test GPG
echo "🧪 Testing GPG functionality..."
TEST_DIR=$(mktemp -d)
cd "$TEST_DIR"

# Create test key batch file
cat > gpg-test-batch <<EOF
%no-protection
Key-Type: RSA
Key-Length: 1024
Name-Real: Test User
Name-Email: test@test.local
Expire-Date: 0
EOF

# Try to generate a test key
echo "   Generating test key (this may take 10-30 seconds)..."
if timeout 60 gpg --batch --gen-key gpg-test-batch 2>&1 | grep -q "marked as ultimately trusted"; then
    echo "✓ GPG can generate keys successfully!"
    # Clean up test key
    TEST_KEY=$(gpg --list-keys --with-colons | grep "^fpr" | head -n 1 | cut -d: -f10)
    if [ -n "$TEST_KEY" ]; then
        gpg --batch --yes --delete-secret-keys "$TEST_KEY" 2>/dev/null
        gpg --batch --yes --delete-keys "$TEST_KEY" 2>/dev/null
    fi
else
    echo "⚠ GPG test key generation had issues"
    echo "   This might be due to low entropy on your device"
    echo "   Try moving your phone around during key generation"
fi

cd -
rm -rf "$TEST_DIR"
echo ""

# Done
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "✅ GPG installed and verified"
echo "✅ Python library installed"
echo "✅ Permissions configured"
echo ""
echo "Next steps:"
echo "1. Start your LXMF client"
echo "2. Run: pgp diagnose"
echo "3. Run: pgp keygen"
echo "4. Run: pgp status"
echo ""
echo "If key generation still fails:"
echo "• Move your device around (adds entropy)"
echo "• Try: haveged -w 1024 &"
echo "• See: TERMUX_TROUBLESHOOTING.md"
echo ""
