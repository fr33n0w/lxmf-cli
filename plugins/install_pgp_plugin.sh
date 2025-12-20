#!/usr/bin/env bash
# PGP Plugin Installer for LXMF CLI

set -e

echo "======================================"
echo "PGP Plugin Installer for LXMF CLI"
echo "======================================"
echo ""

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=Mac;;
    CYGWIN*)    MACHINE=Windows;;
    MINGW*)     MACHINE=Windows;;
    *)          MACHINE="UNKNOWN:${OS}"
esac

echo "Detected OS: ${MACHINE}"
echo ""

# Check for Termux
if [ -d "/data/data/com.termux" ]; then
    echo "Termux environment detected"
    IS_TERMUX=true
else
    IS_TERMUX=false
fi

# Step 1: Check for Python
echo "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ Found: ${PYTHON_VERSION}"
else
    echo "❌ Python 3 not found!"
    echo "Please install Python 3 first"
    exit 1
fi
echo ""

# Step 2: Check for GnuPG
echo "Checking GnuPG installation..."
if command -v gpg &> /dev/null; then
    GPG_VERSION=$(gpg --version | head -n 1)
    echo "✓ Found: ${GPG_VERSION}"
else
    echo "❌ GnuPG not found!"
    echo ""
    echo "Installation instructions:"
    
    if [ "$IS_TERMUX" = true ]; then
        echo "  pkg install gnupg"
    elif [ "$MACHINE" = "Linux" ]; then
        echo "  Debian/Ubuntu: sudo apt install gnupg"
        echo "  Fedora: sudo dnf install gnupg"
        echo "  Arch: sudo pacman -S gnupg"
    elif [ "$MACHINE" = "Mac" ]; then
        echo "  brew install gnupg"
    else
        echo "  Download from: https://gnupg.org/download/"
    fi
    
    echo ""
    read -p "Install GnuPG now? [y/N] " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ "$IS_TERMUX" = true ]; then
            pkg install gnupg -y
        elif [ "$MACHINE" = "Linux" ]; then
            if command -v apt &> /dev/null; then
                sudo apt update && sudo apt install gnupg -y
            elif command -v dnf &> /dev/null; then
                sudo dnf install gnupg -y
            elif command -v pacman &> /dev/null; then
                sudo pacman -S gnupg --noconfirm
            fi
        elif [ "$MACHINE" = "Mac" ]; then
            brew install gnupg
        fi
    else
        echo "Please install GnuPG manually and run this script again"
        exit 1
    fi
fi
echo ""

# Step 3: Install python-gnupg
echo "Installing python-gnupg..."
if [ "$IS_TERMUX" = true ]; then
    pip install python-gnupg --break-system-packages
else
    if command -v pip3 &> /dev/null; then
        pip3 install python-gnupg --user
    else
        python3 -m pip install python-gnupg --user
    fi
fi
echo "✓ python-gnupg installed"
echo ""

# Step 4: Find LXMF storage directory
echo "Locating LXMF client storage..."

# Common locations
POSSIBLE_PATHS=(
    "$HOME/.local/share/lxmf_client_storage"
    "$HOME/lxmf_client_storage"
    "./lxmf_client_storage"
)

STORAGE_PATH=""
for path in "${POSSIBLE_PATHS[@]}"; do
    if [ -d "$path" ]; then
        STORAGE_PATH="$path"
        break
    fi
done

if [ -z "$STORAGE_PATH" ]; then
    echo "⚠ Could not auto-detect LXMF storage directory"
    echo ""
    read -p "Enter path to LXMF storage directory: " STORAGE_PATH
    
    if [ ! -d "$STORAGE_PATH" ]; then
        echo "❌ Directory not found: $STORAGE_PATH"
        exit 1
    fi
fi

echo "✓ Found: $STORAGE_PATH"
echo ""

# Step 5: Create plugins directory
PLUGINS_DIR="${STORAGE_PATH}/plugins"
echo "Setting up plugins directory..."
mkdir -p "$PLUGINS_DIR"
echo "✓ Created: $PLUGINS_DIR"
echo ""

# Step 6: Copy plugin file
echo "Installing PGP plugin..."
if [ -f "pgp.py" ]; then
    cp pgp.py "$PLUGINS_DIR/"
    echo "✓ Copied pgp.py to $PLUGINS_DIR/"
else
    echo "❌ pgp.py not found in current directory!"
    echo "Please run this script from the directory containing pgp.py"
    exit 1
fi
echo ""

# Step 7: Set permissions
chmod 644 "$PLUGINS_DIR/pgp.py"
echo "✓ Set file permissions"
echo ""

# Done!
echo "======================================"
echo "Installation Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Start your LXMF client"
echo "2. The PGP plugin will auto-load"
echo "3. Run 'pgp status' to verify"
echo "4. Run 'pgp help' for commands"
echo ""
echo "Quick start:"
echo "  pgp export          - Get your public key"
echo "  pgp trust <contact> <key> - Import contact's key"
echo "  pgp send <contact> <msg>  - Send encrypted message"
echo ""
echo "For full documentation, see: PGP_PLUGIN_README.md"
echo ""
