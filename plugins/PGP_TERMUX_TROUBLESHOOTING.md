# PGP Plugin - Termux Troubleshooting Guide

## Issue: "No key configured" after plugin loads

This happens when key generation fails silently on Termux. Here's how to fix it:

### Step 1: Verify GPG is installed

```bash
gpg --version
```

**If not installed:**
```bash
pkg install gnupg -y
```

### Step 2: Verify python-gnupg is installed

```bash
pip list | grep gnupg
```

**If not installed:**
```bash
pip install python-gnupg --break-system-packages
```

### Step 3: Run diagnostic

Start your LXMF client and run:
```
pgp diagnose
```

This will show you:
- ✓ GPG binary status
- ✓ Python library status
- ✓ Keyring directory permissions
- ✓ Existing keys
- 💡 Specific recommendations

### Step 4: Manual key generation

If auto-generation failed, generate manually:

```
pgp keygen
```

This will:
1. Prompt for confirmation
2. Show detailed progress
3. Display any errors that occur
4. Give you troubleshooting steps if it fails

### Common Termux Issues

#### Issue: GPG not found
**Solution:**
```bash
pkg update
pkg install gnupg -y
```

#### Issue: Permission denied on keyring
**Solution:**
```bash
# Find your keyring directory (shown in "pgp diagnose")
chmod 700 ~/.local/share/lxmf_client_storage/plugins/pgp/keyring
```

#### Issue: Key generation hangs
**Cause:** Insufficient entropy on mobile devices

**Solutions:**

1. **Move your device around** while key generation runs (adds entropy)

2. **Install haveged** (entropy generator):
```bash
pkg install haveged
haveged -w 1024
```
Then try `pgp keygen` again

3. **Use smaller key** (edit plugin temporarily):
   - Not recommended for production use
   - Only if you're testing

#### Issue: "GPG version: None"
**Cause:** GPG binary not in PATH or python-gnupg can't find it

**Solution:**
```bash
# Check where GPG is installed
which gpg

# Should show: /data/data/com.termux/files/usr/bin/gpg

# If not found, reinstall:
pkg reinstall gnupg
```

## Manual Key Generation (Outside Plugin)

If the plugin continues to fail, you can generate a key manually and configure the plugin to use it:

### Step 1: Generate key with GPG directly

```bash
gpg --full-gen-key
```

Choose:
- Key type: **RSA and RSA**
- Key size: **2048**
- Expiration: **0** (never)
- Name: **Your LXMF display name**
- Email: **anything@lxmf.local**
- Passphrase: **Leave empty** (or remember it)

### Step 2: List your keys

```bash
gpg --list-keys
```

Look for output like:
```
pub   rsa2048 2024-12-20 [SC]
      1234567890ABCDEF1234567890ABCDEF12345678
uid           [ultimate] YourName <anything@lxmf.local>
```

The long hex string is your **fingerprint**.

### Step 3: Configure plugin to use this key

Edit the plugin config:
```bash
nano ~/.local/share/lxmf_client_storage/plugins/pgp/config.json
```

Add or modify:
```json
{
  "my_key_id": "1234567890ABCDEF1234567890ABCDEF12345678",
  "auto_encrypt": false,
  "auto_sign": true,
  "auto_decrypt": true,
  "auto_verify": true,
  "reject_unsigned": false,
  "reject_unencrypted": false
}
```

Replace the fingerprint with yours from step 2.

### Step 4: Restart LXMF client

Exit and restart. Check status:
```
pgp status
```

Should now show your key!

## Still Having Issues?

### Get detailed error information

Run diagnostic:
```
pgp diagnose
```

Save the output and check:
1. Is GPG binary found? ✓
2. Is python-gnupg loaded? ✓
3. Is keyring writable? ✓
4. What's the specific error?

### Test GPG directly

```bash
# Create test message
echo "test" > test.txt

# Try to encrypt it
gpg --armor --encrypt --recipient your@email.local test.txt

# If this fails, the issue is with GPG itself, not the plugin
```

### Check permissions

```bash
# Plugin directories should be readable/writable
ls -la ~/.local/share/lxmf_client_storage/plugins/pgp/

# Should show:
# drwx------ keyring/
# -rw-r--r-- config.json
```

Fix if needed:
```bash
chmod 700 ~/.local/share/lxmf_client_storage/plugins/pgp/keyring
chmod 644 ~/.local/share/lxmf_client_storage/plugins/pgp/config.json
```

## Working Configuration Example

Here's what a working Termux setup looks like:

```bash
# 1. GPG installed and working
$ gpg --version
gpg (GnuPG) 2.4.0
...

# 2. Python library installed
$ pip list | grep gnupg
python-gnupg  0.5.1

# 3. In LXMF client
> pgp diagnose

🔍 GPG Binary:
  ✓ Found: gpg (GnuPG) 2.4.0

🐍 Python GnuPG Library:
  ✓ Module loaded: ...

📁 Keyring Directory:
  Path: /data/data/com.termux/files/home/.local/share/lxmf_client_storage/plugins/pgp/keyring
  Exists: True
  Writable: True

🔧 Python-GnuPG Status:
  ✓ GPG version: 2.4.0

🔑 Current Keys in Keyring:
  Found 1 key(s):
  ★ 1234567890ABCDEF: YourName <hash@lxmf.local>

⚙️  Plugin Configuration:
  Configured key ID: 1234567890ABCDEF1234567890ABCDEF12345678

# 4. Status shows working key
> pgp status

🔑 Your Key:
  Key ID: 1234567890ABCDEF1234567890ABCDEF12345678
  Name: YourName <hash@lxmf.local>
  Type: RSA 2048-bit
```

## Quick Fix Checklist

Run these commands in order:

```bash
# 1. Update and install GPG
pkg update && pkg install gnupg -y

# 2. Install Python library
pip install python-gnupg --break-system-packages

# 3. Test GPG
gpg --version

# 4. In LXMF client - diagnose
pgp diagnose

# 5. Generate key if needed
pgp keygen

# 6. Verify it worked
pgp status
```

## Need More Help?

If you're still stuck:

1. Run `pgp diagnose` and save output
2. Check what specific error appears during `pgp keygen`
3. Try manual GPG key generation (see above)
4. Check Termux logs for errors

The most common fix is simply:
```bash
pkg install gnupg
pip install python-gnupg --break-system-packages
```

Then in LXMF:
```
pgp keygen
```
