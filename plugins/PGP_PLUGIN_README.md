# PGP Plugin for LXMF CLI

End-to-end encryption and digital signatures for LXMF messages using PGP/GPG.

## Features

- 🔐 **Automatic Encryption/Decryption**: Seamlessly encrypt outgoing and decrypt incoming messages
- ✍️ **Digital Signatures**: Sign messages to prove authenticity and verify incoming signatures
- 🔑 **Key Management**: Generate, import, export, and manage PGP keys
- 🛡️ **Security Policies**: Reject unsigned or unencrypted messages
- 🤖 **Autonomous Operation**: Works automatically in the background once configured
- 👥 **Contact Key Mapping**: Automatically associates PGP keys with LXMF contacts

## Installation

### Prerequisites

1. **Python GnuPG library**:
```bash
pip install python-gnupg --break-system-packages
```

2. **GnuPG binary** (if not already installed):

**Termux/Android:**
```bash
pkg install gnupg
```

**Debian/Ubuntu:**
```bash
sudo apt install gnupg
```

**macOS:**
```bash
brew install gnupg
```

**Windows:**
Download and install from: https://gnupg.org/download/

### Installing the Plugin

1. Copy `pgp.py` to your LXMF client's plugins directory:
```bash
# Default location
cp pgp.py ~/.local/share/lxmf_client_storage/plugins/
```

2. Start the LXMF client - the plugin will auto-load

3. First run will automatically generate a PGP key pair for you

## Quick Start

### Basic Usage

1. **Check PGP status:**
```
pgp status
```

2. **Export your public key** (to share with contacts):
```
pgp export
```

3. **Import a contact's public key:**
```
pgp trust Alice <paste their public key>
```

4. **Send encrypted message:**
```
pgp send Alice Hello, this is encrypted!
```

### Automatic Mode

Enable automatic encryption for all messages:

```
pgp set auto_encrypt on
pgp set auto_sign on
```

Now all outgoing messages will be automatically encrypted and signed!

## Commands Reference

### Status & Information

| Command | Description |
|---------|-------------|
| `pgp status` | Show PGP configuration and statistics |
| `pgp list` | List all keys in keyring |
| `pgp help` | Show command help |

### Key Management

| Command | Description |
|---------|-------------|
| `pgp keygen` | Generate new PGP key pair (replaces current) |
| `pgp export` | Display your public key for sharing |
| `pgp import <contact>` | Request public key from contact |
| `pgp trust <contact> <key>` | Import and trust a public key |

### Messaging

| Command | Description |
|---------|-------------|
| `pgp send <contact> <message>` | Send encrypted & signed message |

### Settings

| Setting | Values | Description |
|---------|--------|-------------|
| `auto_encrypt` | on/off | Automatically encrypt all outgoing messages |
| `auto_sign` | on/off | Automatically sign all outgoing messages |
| `auto_decrypt` | on/off | Automatically decrypt incoming messages |
| `auto_verify` | on/off | Automatically verify incoming signatures |
| `reject_unsigned` | on/off | Reject messages without valid signatures |
| `reject_unencrypted` | on/off | Reject unencrypted messages |

**Example:**
```
pgp set auto_encrypt on
pgp set reject_unencrypted on
```

## Usage Scenarios

### Scenario 1: Secure Communication Setup

**You and Alice want secure communications:**

1. **You export your key:**
```
pgp export
```
Copy the output

2. **Send it to Alice via regular LXMF:**
```
send Alice -----BEGIN PGP PUBLIC KEY BLOCK----- <rest of key>
```

3. **Alice imports your key:**
```
pgp trust <your_name> <your_public_key>
```

4. **Alice sends you her key the same way**

5. **You import Alice's key:**
```
pgp trust Alice <alice_public_key>
```

6. **Now send encrypted messages:**
```
pgp send Alice This is secret!
```

### Scenario 2: Automatic Encryption

**Enable full automatic mode:**

```
pgp set auto_encrypt on
pgp set auto_sign on
pgp set auto_decrypt on
pgp set auto_verify on
```

Now:
- All outgoing messages are automatically encrypted & signed
- All incoming encrypted messages are automatically decrypted
- All signatures are automatically verified
- You can use normal `send` command and it works transparently!

### Scenario 3: High Security Mode

**Only accept encrypted & signed messages:**

```
pgp set reject_unencrypted on
pgp set reject_unsigned on
```

This will automatically reject any message that isn't both encrypted AND signed.

## How It Works

### Outgoing Messages

1. **Manual encryption** (`pgp send`):
   - Message is signed with your private key
   - Signed message is encrypted with recipient's public key
   - Encrypted blob is sent via LXMF

2. **Automatic encryption** (`auto_encrypt on`):
   - Intercepts normal `send` commands
   - Automatically encrypts if recipient's key is known
   - Falls back to unencrypted if no key available

### Incoming Messages

1. **Automatic decryption** (`auto_decrypt on`):
   - Detects PGP encrypted messages
   - Decrypts using your private key
   - Shows decrypted content

2. **Automatic verification** (`auto_verify on`):
   - Detects PGP signed messages
   - Verifies signature
   - Shows validity status and signer info

### Key Exchange

The plugin supports multiple key exchange methods:

1. **Manual exchange**: Copy/paste keys via any channel
2. **LXMF exchange**: Send keys as regular messages
3. **Out-of-band**: QR codes, files, etc.

## Security Considerations

### Key Storage

- Keys are stored in `~/.local/share/lxmf_client_storage/plugins/pgp/keyring/`
- This directory should be kept secure (use encryption at rest if possible)
- Private keys are never transmitted

### Trust Model

- **Manual trust**: You explicitly trust each imported key
- **No key servers**: Keys are exchanged directly between users
- **Contact mapping**: Keys are linked to LXMF addresses for convenience

### Limitations

- **No forward secrecy**: PGP doesn't provide forward secrecy like Signal/OTR
- **Key compromise**: If private key is compromised, all past messages are readable
- **No group encryption**: Each message encrypted separately for each recipient

### Best Practices

1. **Verify fingerprints** out-of-band when possible
2. **Backup your private key** securely
3. **Use strong passphrases** (future feature)
4. **Regenerate keys periodically** for long-term security
5. **Enable reject policies** for sensitive communications

## Troubleshooting

### "gnupg not found"
Install python-gnupg:
```bash
pip install python-gnupg --break-system-packages
```

### "Failed to generate key"
Ensure GnuPG is installed:
```bash
gpg --version
```

### "No public key for contact"
Import their public key first:
```bash
pgp trust <contact> <their_public_key>
```

### "Decryption failed"
- Message wasn't encrypted for your key
- Check your key is properly configured: `pgp status`

### Key not working after restart
- Keys are persistent in the keyring
- Check: `pgp list`
- Reimport if needed

## Advanced Usage

### Multiple Keys

You can have multiple keys in your keyring. Set the active one:
```
pgp keygen
```

### Export Specific Key

```bash
pgp export
```

### Key Fingerprint Verification

List all keys with full fingerprints:
```
pgp list
```

Compare fingerprints out-of-band (phone call, in person, etc.)

## Integration with LXMF CLI

The plugin seamlessly integrates with your LXMF client:

- **Works with all commands**: `send`, `reply`, `sendpeer`, etc.
- **Contact resolution**: Use contact names, numbers, or hashes
- **Message history**: Decrypted messages are stored decrypted
- **Notifications**: Normal notification system works with encrypted messages

## File Locations

```
~/.local/share/lxmf_client_storage/plugins/pgp/
├── keyring/           # GnuPG keyring (private & public keys)
├── config.json        # Plugin settings
└── trusted_keys.json  # Contact->Key mappings
```

## Privacy & Security

- ✅ End-to-end encryption
- ✅ Digital signatures for authenticity
- ✅ Local key storage only
- ✅ No key servers (no metadata leakage)
- ✅ Works offline
- ❌ No forward secrecy (use Signal Protocol plugin for that)
- ❌ No key expiration (manual rotation recommended)

## Contributing

Found a bug? Have a feature request? Please open an issue!

## License

Same as LXMF CLI client

## Credits

Built on:
- **GnuPG**: The GNU Privacy Guard
- **python-gnupg**: Python wrapper for GnuPG
- **LXMF**: Lightweight Extensible Message Format
- **Reticulum**: The cryptography-based networking stack
