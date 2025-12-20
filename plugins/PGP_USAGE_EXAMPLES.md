# PGP Plugin - Usage Examples

## Example 1: First Time Setup

```bash
# Start LXMF CLI - PGP plugin auto-generates key on first run
$ python lxmf_cli.py

[PGP Plugin loads]
PGP PLUGIN - FIRST TIME SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

No PGP key found. Let's create one for you.
This will be used to sign and encrypt your messages.

Name: Alice
Email: a1b2c3d4e5f6@lxmf.local

Generating 2048-bit RSA key pair...
This may take a minute...

✓ PGP key pair generated!
✓ Key ID: 1234567890ABCDEF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Check status
> pgp status

PGP STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔑 Your Key:
  Key ID: 1234567890ABCDEF
  Name: Alice <a1b2c3d4e5f6@lxmf.local>
  Type: RSA 2048-bit

⚙️  Settings:
  Auto-encrypt:  OFF
  Auto-sign:     ON
  Auto-decrypt:  ON
  Auto-verify:   ON
  Reject unsigned:    OFF
  Reject unencrypted: OFF

👥 Trusted Keys: 0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Example 2: Exchanging Keys with Bob

```bash
# Alice exports her public key
> pgp export

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR PUBLIC KEY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-----BEGIN PGP PUBLIC KEY BLOCK-----

mQENBGX1... [full key data] ...=abcd
-----END PGP PUBLIC KEY BLOCK-----
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Share this with contacts so they can send you encrypted messages
   You can send it via: send <contact> <paste key here>

# Alice sends her public key to Bob
> send Bob -----BEGIN PGP PUBLIC KEY BLOCK----- mQENBGX1...=abcd -----END PGP PUBLIC KEY BLOCK-----

📤 Sending to: Bob...
✅ Delivered to Bob (2.3s)

# Bob receives the key and imports it
[Bob's terminal]
📨 NEW MESSAGE from: Alice
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-----BEGIN PGP PUBLIC KEY BLOCK-----
mQENBGX1...=abcd
-----END PGP PUBLIC KEY BLOCK-----
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

> pgp trust Alice -----BEGIN PGP PUBLIC KEY BLOCK----- mQENBGX1...=abcd -----END PGP PUBLIC KEY BLOCK-----

✓ [PGP] Imported public key: 1234567890ABCDEF
✓ [PGP] Trusted key for Alice

# Bob sends his key to Alice (same process)
> pgp export
[copies key]
> send Alice -----BEGIN PGP PUBLIC KEY BLOCK----- ...

# Alice imports Bob's key
> pgp trust Bob -----BEGIN PGP PUBLIC KEY BLOCK----- ...

✓ [PGP] Imported public key: FEDCBA0987654321
✓ [PGP] Trusted key for Bob
```

## Example 3: Sending Encrypted Messages

```bash
# Alice sends encrypted message to Bob
> pgp send Bob Hey Bob! This message is encrypted and signed!

✓ [PGP] Sent encrypted & signed message
📤 Sending to: Bob...
✅ Delivered to Bob (3.1s)

# Bob receives and automatically decrypts
[Bob's terminal]
🔐 Encrypted message from Alice
✓ [PGP] Message decrypted
✓ [PGP] ✓ Signature valid - From: Alice <a1b2c3d4e5f6@lxmf.local>
  Key ID: 1234567890ABCDEF

📨 NEW MESSAGE from: Alice
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Hey Bob! This message is encrypted and signed!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Type 'reply <message>' to respond
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Example 4: Automatic Mode

```bash
# Enable automatic encryption and signing
> pgp set auto_encrypt on
✓ [PGP] auto_encrypt: enabled

> pgp set auto_sign on
✓ [PGP] auto_sign: enabled

# Now regular send commands are automatically encrypted!
> send Bob This is automatically encrypted!

[Behind the scenes: message is signed, encrypted, then sent]

✅ Delivered to Bob (2.8s)

# Bob receives it - automatically decrypted
[Bob's terminal]
🔐 Encrypted message from Alice
✓ [PGP] Message decrypted
✓ [PGP] ✓ Signature valid - From: Alice <a1b2c3d4e5f6@lxmf.local>

📨 NEW MESSAGE from: Alice
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is automatically encrypted!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Example 5: High Security Mode

```bash
# Only accept encrypted and signed messages
> pgp set reject_unencrypted on
✓ [PGP] reject_unencrypted: enabled

> pgp set reject_unsigned on
✓ [PGP] reject_unsigned: enabled

# Charlie (who doesn't have PGP) tries to send unencrypted message
[Charlie sends: "Hey Alice!"]

[Alice's terminal - message rejected]
⚠ [PGP] Rejected unencrypted message from <charlie_hash>
  Enable 'pgp set reject_unencrypted off' to receive unencrypted messages

# The message is blocked - Alice never sees it
```

## Example 6: Multi-User Scenario

```bash
# Alice has keys for multiple contacts
> pgp status

PGP STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔑 Your Key:
  Key ID: 1234567890ABCDEF
  Name: Alice <a1b2c3d4e5f6@lxmf.local>
  Type: RSA 2048-bit

⚙️  Settings:
  Auto-encrypt:  ON
  Auto-sign:     ON
  Auto-decrypt:  ON
  Auto-verify:   ON

👥 Trusted Keys: 3
  Bob: FEDCBA09876543...
  Charlie: AABBCCDD112233...
  Dave: 99887766554433...

# Send to multiple people - each message encrypted separately
> send Bob Secret for Bob only
> send Charlie Different secret for Charlie
> send Dave Yet another secret for Dave

# Each recipient gets their own encrypted copy
# Even if they intercept each other's messages, they can't decrypt them
```

## Example 7: Signed but Unencrypted Messages

```bash
# Sometimes you want authentication but not secrecy
> pgp set auto_encrypt off
✓ [PGP] auto_encrypt: disabled

> pgp set auto_sign on
✓ [PGP] auto_sign: enabled

> send Bob This is signed but readable by anyone who intercepts it

[Message is signed but not encrypted - proves it's from Alice]

[Bob receives]
✓ [PGP] ✓ Signature valid - From: Alice <a1b2c3d4e5f6@lxmf.local>

📨 NEW MESSAGE from: Alice
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is signed but readable by anyone who intercepts it
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Example 8: Verifying Fingerprints Out-of-Band

```bash
# Alice and Bob meet in person to verify keys
> pgp list

PGP KEYRING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Key ID           Type         Name
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
★ 1234567890ABCDEF RSA 2048-bit Alice <a1b2c3d4e5f6@lxmf.local>
  FEDCBA0987654321 RSA 2048-bit Bob <b2c3d4e5f6a7@lxmf.local>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

★ = Your key

# Alice reads out her fingerprint: "1234 5678 90AB CDEF"
# Bob verifies it matches what he has
# Bob reads his: "FEDC BA09 8765 4321"
# Alice confirms match

# Now they know the keys are authentic!
```

## Example 9: Emergency Key Rotation

```bash
# Private key compromised! Generate new one
> pgp keygen

⚠ Warning: This will replace your current key!
Continue? [y/N]: y

PGP PLUGIN - FIRST TIME SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Name: Alice
Email: a1b2c3d4e5f6@lxmf.local

Generating 2048-bit RSA key pair...

✓ PGP key pair generated!
✓ Key ID: ABCDEF1234567890

# Export new key and send to all contacts
> pgp export
[copy key]

> send Bob KEY ROTATION - please import this new key
> send Charlie KEY ROTATION - please import this new key
> send Dave KEY ROTATION - please import this new key
```

## Example 10: Plugin Management

```bash
# List all plugins
> plugin list

PLUGINS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plugin               Status          Description
──────────────────── ─────────────── ──────────────────────────────
pgp                  Loaded          End-to-end PGP encryption
echo                 Disabled        Echo bot example
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Disable PGP temporarily
> plugin disable pgp
✓ Plugin pgp disabled
⚠ Use 'plugin reload' to deactivate

> plugin reload
✓ Plugins reloaded

# Re-enable
> plugin enable pgp
✓ Plugin pgp enabled
⚠ Use 'plugin reload' to activate

> plugin reload
✓ Plugins reloaded
✓ [PGP] PGP plugin loaded
✓ [PGP] Using key: 1234567890ABCDEF
```

## Common Workflows

### Workflow 1: Initial Contact Setup
1. `pgp export` - Get your public key
2. `send <contact> <your_key>` - Send to contact
3. Wait for their key
4. `pgp trust <contact> <their_key>` - Import their key
5. `pgp send <contact> test` - Test encrypted messaging

### Workflow 2: Daily Use (Auto Mode)
1. `pgp set auto_encrypt on` - One time setup
2. `pgp set auto_sign on`
3. Use normal `send` commands - encryption is automatic!

### Workflow 3: Paranoid Mode
1. `pgp set reject_unencrypted on`
2. `pgp set reject_unsigned on`
3. `pgp set auto_encrypt on`
4. `pgp set auto_sign on`
5. Only encrypted & signed messages allowed

## Troubleshooting Examples

### Problem: Can't decrypt received message
```bash
> [Message shows encrypted blob]

# Check if you have the right key
> pgp status
# Look at "Your Key" - should match recipient

# Try manual decrypt (shouldn't be needed with auto_decrypt on)
> pgp set auto_decrypt on
```

### Problem: Recipient can't decrypt your message
```bash
# Did you import their public key?
> pgp list
# Check if their key is listed

# If not:
> pgp trust <contact> <their_public_key>
```

### Problem: Signature verification fails
```bash
⚠ [PGP] Invalid or missing signature!

# Possible causes:
# 1. Wrong key imported for this contact
# 2. Message was tampered with
# 3. Sender didn't actually sign it

# Solution: Re-verify fingerprints out-of-band
```
