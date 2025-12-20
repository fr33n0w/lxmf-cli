# PGP Plugin - Quick Start Guide (Post-Installation)

## If Key Generation Failed (shows "No key configured")

### On Termux (Android)

**Option 1: Quick Fix Script (Recommended)**
```bash
# Run the automated fix
bash termux_pgp_fix.sh

# Then in LXMF client:
pgp keygen
```

**Option 2: Manual Steps**
```bash
# Install/reinstall GPG
pkg update
pkg install gnupg -y

# Install Python library
pip install python-gnupg --break-system-packages

# Verify installation
gpg --version

# Start LXMF client and run:
pgp diagnose
pgp keygen
```

### On Windows

Key generation should work automatically. If not:

```bash
# Verify GPG is installed
gpg --version

# If not found, download from: https://gnupg.org/download/

# In LXMF client:
pgp keygen
```

### On Linux/macOS

```bash
# Install GPG if needed
sudo apt install gnupg  # Debian/Ubuntu
brew install gnupg      # macOS

# Install Python library
pip install python-gnupg --user

# In LXMF client:
pgp keygen
```

## Step-by-Step: Getting Your PGP Working

### 1. Run Diagnostic

In your LXMF client, type:
```
pgp diagnose
```

This will tell you exactly what's wrong. Look for:
- ✓ GPG Binary: Should be "Found"
- ✓ Python GnuPG Library: Should be loaded
- ✓ Keyring Directory: Should be writable
- ✓ GPG version: Should show a version number

### 2. Generate Your Key

Once diagnostic shows all ✓ marks:
```
pgp keygen
```

**On mobile/Termux:** This may take 30-60 seconds. **Move your device around** to generate entropy.

Expected output:
```
📝 Generating new PGP key...

PGP PLUGIN - FIRST TIME SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name: YourName
Email: a1b2c3d4e5f6@lxmf.local

Using GPG version: 2.4.0
Starting key generation...

✓ PGP key pair generated!
✓ Key ID: 1234567890ABCDEF1234567890ABCDEF12345678
✓ Key generation complete!
```

### 3. Verify It Worked

```
pgp status
```

Should show:
```
🔑 Your Key:
  Key ID: 1234567890ABCDEF...
  Name: YourName <...@lxmf.local>
  Type: RSA 2048-bit
```

### 4. Export Your Public Key

```
pgp export
```

Copy the output (everything from `-----BEGIN PGP PUBLIC KEY BLOCK-----` to `-----END PGP PUBLIC KEY BLOCK-----`)

### 5. Share Keys with Contacts

**Send your key to a contact:**
```
send Alice -----BEGIN PGP PUBLIC KEY BLOCK----- [paste entire key] -----END PGP PUBLIC KEY BLOCK-----
```

**When you receive a contact's key:**
```
pgp trust Alice -----BEGIN PGP PUBLIC KEY BLOCK----- [paste their key] -----END PGP PUBLIC KEY BLOCK-----
```

### 6. Send Encrypted Messages

**Method 1: Direct command**
```
pgp send Alice Hello, this is encrypted!
```

**Method 2: Enable auto-mode**
```
pgp set auto_encrypt on
pgp set auto_sign on

# Now regular send is encrypted:
send Alice This is also encrypted!
```

## Common Issues & Solutions

### Issue: "Failed to generate key"

**Solution:**
```bash
# On Termux - improve entropy
pkg install haveged
haveged -w 1024 &

# Try again
pgp keygen
```

### Issue: "GPG not properly initialized"

**Solution:**
```bash
# Verify GPG binary exists
gpg --version

# If not found, reinstall:
# Termux: pkg install gnupg
# Linux: sudo apt install gnupg
# macOS: brew install gnupg
```

### Issue: "Could not get GPG version"

**Solution:**
```bash
# Reinstall python-gnupg
pip uninstall python-gnupg
pip install python-gnupg --break-system-packages
```

### Issue: Key generation hangs forever

**On Termux:**
- Move your device around (generates entropy)
- Install haveged: `pkg install haveged`
- Wait up to 2 minutes

**On any system:**
- Open another terminal and run: `ls -R /` (generates disk activity)
- Move mouse around (on desktop)
- Press random keys in another window

### Issue: "Permission denied" on keyring

**Solution:**
```bash
# Find keyring path with: pgp diagnose
# Then fix permissions:
chmod 700 ~/.local/share/lxmf_client_storage/plugins/pgp/keyring
```

## What to Do If Nothing Works

### Nuclear Option: Manual Key + Config

1. **Generate key outside plugin:**
```bash
gpg --full-gen-key
# Choose: RSA 2048, no expiration
# Use any name/email
```

2. **Get the key ID:**
```bash
gpg --list-keys
# Look for the long hex fingerprint
```

3. **Edit plugin config:**
```bash
# Find your storage path with: pgp diagnose
nano ~/.local/share/lxmf_client_storage/plugins/pgp/config.json
```

Add:
```json
{
  "my_key_id": "YOUR_FINGERPRINT_HERE",
  "auto_encrypt": false,
  "auto_sign": true,
  "auto_decrypt": true,
  "auto_verify": true
}
```

4. **Restart LXMF client**

5. **Check status:**
```
pgp status
```

Should now show your manually created key!

## Verification Checklist

Use this to verify everything is working:

- [ ] `pgp diagnose` shows all ✓ marks
- [ ] `pgp keygen` completes without errors
- [ ] `pgp status` shows a key ID
- [ ] `pgp list` shows your key with ★ marker
- [ ] `pgp export` shows your public key
- [ ] Can send encrypted message to yourself (if you trust your own key)

## Getting Help

If you're still stuck:

1. Run `pgp diagnose` and save the output
2. Try the manual key generation method above
3. Check the full TERMUX_TROUBLESHOOTING.md guide
4. Verify GPG works outside the plugin: `echo "test" | gpg --armor --encrypt -r your@email.local`

## Success! Now What?

Once you have a working key:

1. **Export and share:** `pgp export`
2. **Import contacts' keys:** `pgp trust <name> <their_key>`
3. **Send encrypted:** `pgp send <name> <message>`
4. **Or enable auto-mode:**
   ```
   pgp set auto_encrypt on
   pgp set auto_sign on
   ```

Enjoy secure messaging! 🔐
