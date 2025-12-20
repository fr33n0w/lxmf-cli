# PGP Plugin v2 - Fixed Version

## What's New in v2

✅ **Improved key generation** with better error handling  
✅ **Diagnostic command** (`pgp diagnose`) to troubleshoot issues  
✅ **Termux-specific fixes** for mobile key generation  
✅ **Better error messages** that tell you exactly what's wrong  
✅ **Manual key configuration** support if auto-generation fails  

## For Termux Users: Key Not Generated?

### Quick Fix (Run this in Termux):

```bash
bash termux_pgp_fix.sh
```

Then in LXMF client:
```
pgp keygen
```

### Manual Steps:

1. **Install GPG:**
```bash
pkg install gnupg -y
```

2. **Install Python library:**
```bash
pip install python-gnupg --break-system-packages
```

3. **In LXMF client - diagnose:**
```
pgp diagnose
```

4. **Generate key:**
```
pgp keygen
```

**Pro tip:** Move your device around during key generation (helps with entropy)

## Installation

### Replace Old Plugin

If you already have pgp.py installed:

```bash
# Backup old version
cp ~/.local/share/lxmf_client_storage/plugins/pgp.py ~/.local/share/lxmf_client_storage/plugins/pgp.py.backup

# Install new version
cp pgp_v2.py ~/.local/share/lxmf_client_storage/plugins/pgp.py

# Restart LXMF client
```

### New Installation

```bash
# Copy plugin to plugins directory
cp pgp_v2.py ~/.local/share/lxmf_client_storage/plugins/pgp.py

# Restart LXMF client
```

## New Commands

### pgp diagnose

Shows detailed diagnostic information:
```
pgp diagnose
```

Output includes:
- ✓ GPG binary status
- ✓ Python library status  
- ✓ Keyring directory permissions
- ✓ Current keys in keyring
- 💡 Specific recommendations to fix issues

### pgp keygen (improved)

Now with:
- Better progress indication
- Detailed error messages
- Troubleshooting tips if it fails
- Works even if first auto-generation failed

## Troubleshooting

### No Key After First Load

**This is the most common issue on Termux.**

**Solution:**
```
# 1. Run diagnostic
pgp diagnose

# 2. Follow any recommendations shown

# 3. Generate key manually
pgp keygen

# 4. Verify
pgp status
```

### Key Generation Hangs

**On Termux:**
- Move your device around (generates entropy)
- Install haveged: `pkg install haveged && haveged -w 1024 &`
- Wait up to 2 minutes

**On any system:**
- Do disk-intensive operations in another terminal
- Move mouse / type random keys (on desktop)

### "GPG not properly initialized"

```bash
# Check GPG is installed
gpg --version

# If not found:
# Termux: pkg install gnupg
# Linux: sudo apt install gnupg
# macOS: brew install gnupg
```

### "Could not get GPG version"

```bash
# Reinstall python-gnupg
pip install python-gnupg --break-system-packages --upgrade
```

## Manual Key Configuration

If automatic generation keeps failing, you can create a key manually and configure the plugin to use it:

### Step 1: Generate key with GPG

```bash
gpg --full-gen-key
```

Choose:
- Type: RSA and RSA
- Size: 2048
- Expiration: 0 (never)
- Name: Your LXMF name
- Email: anything@lxmf.local

### Step 2: Get key fingerprint

```bash
gpg --list-keys --fingerprint
```

Copy the long hex fingerprint (40 characters)

### Step 3: Configure plugin

Edit config file:
```bash
nano ~/.local/share/lxmf_client_storage/plugins/pgp/config.json
```

Set:
```json
{
  "my_key_id": "YOUR_40_CHARACTER_FINGERPRINT_HERE",
  "auto_encrypt": false,
  "auto_sign": true,
  "auto_decrypt": true,
  "auto_verify": true
}
```

### Step 4: Restart LXMF

Exit and restart the client. Run:
```
pgp status
```

Should now show your manually configured key!

## Files in This Package

- **pgp_v2.py** - Updated plugin with fixes
- **QUICK_START_FIX.md** - Quick guide to fix key generation issues
- **TERMUX_TROUBLESHOOTING.md** - Comprehensive Termux troubleshooting
- **termux_pgp_fix.sh** - Automated fix script for Termux
- **PGP_PLUGIN_README.md** - Full documentation
- **PGP_USAGE_EXAMPLES.md** - 10 detailed usage examples

## Quick Start (After Fixing Key)

```
# 1. Verify key is configured
pgp status

# 2. Export your public key
pgp export

# 3. Share with contact via LXMF
send Bob -----BEGIN PGP PUBLIC KEY BLOCK----- ... -----END PGP PUBLIC KEY BLOCK-----

# 4. Import their key when received
pgp trust Bob -----BEGIN PGP PUBLIC KEY BLOCK----- ... -----END PGP PUBLIC KEY BLOCK-----

# 5. Send encrypted message
pgp send Bob Hello securely!

# 6. Or enable auto-mode
pgp set auto_encrypt on
send Bob This is also encrypted!
```

## Command Reference

### Essential Commands

| Command | Description |
|---------|-------------|
| `pgp diagnose` | **NEW** - Diagnose installation issues |
| `pgp keygen` | **IMPROVED** - Generate/regenerate key |
| `pgp status` | Show current configuration |
| `pgp export` | Get your public key to share |
| `pgp trust <contact> <key>` | Import contact's public key |
| `pgp send <contact> <msg>` | Send encrypted message |

### Settings

| Command | Description |
|---------|-------------|
| `pgp set auto_encrypt on/off` | Auto-encrypt all messages |
| `pgp set auto_sign on/off` | Auto-sign all messages |
| `pgp set auto_decrypt on/off` | Auto-decrypt incoming |
| `pgp set auto_verify on/off` | Auto-verify signatures |

## What Changed from v1

### Key Generation
- ✅ Better error handling
- ✅ Shows GPG version before attempting generation
- ✅ Displays detailed error messages
- ✅ Gives specific troubleshooting steps if it fails
- ✅ Works better on low-entropy devices (mobile)

### Diagnostics
- ✅ New `pgp diagnose` command
- ✅ Checks GPG binary
- ✅ Checks Python library
- ✅ Checks permissions
- ✅ Lists all keys in keyring
- ✅ Shows specific recommendations

### Error Messages
- ✅ More informative
- ✅ Include solutions
- ✅ Point to relevant documentation

### Documentation
- ✅ Termux-specific troubleshooting guide
- ✅ Quick start guide for fixing issues
- ✅ Automated fix script

## Still Having Issues?

1. **Run diagnostic:** `pgp diagnose`
2. **Read the output** - it will tell you what's wrong
3. **Check guides:**
   - QUICK_START_FIX.md - Fast solutions
   - TERMUX_TROUBLESHOOTING.md - Detailed Termux guide
   - PGP_PLUGIN_README.md - Full documentation

4. **Try automated fix** (Termux only):
   ```bash
   bash termux_pgp_fix.sh
   ```

5. **Manual key generation** (if all else fails) - see above

## Compatibility

- ✅ Termux (Android) - **Improved in v2**
- ✅ Windows - Works well
- ✅ Linux - Works well  
- ✅ macOS - Works well

## Requirements

- GPG/GnuPG 2.x
- python-gnupg library
- LXMF CLI client

## Support

The diagnostic command (`pgp diagnose`) will tell you exactly what's wrong and how to fix it. Run it first before seeking help!
