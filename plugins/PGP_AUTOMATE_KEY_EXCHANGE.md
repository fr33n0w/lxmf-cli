# Automated PGP Key Exchange - Quick Guide

## 🎉 NEW: One-Command Key Exchange!

No more copying and pasting keys! The plugin now handles everything automatically.

## Simple Method: `pgp exchange`

### Client A (Termux):
```bash
# Make sure contact exists first
add Bob <bob_hash>

# Start automatic key exchange
pgp exchange Bob
```

**Output:**
```
🔄 Starting key exchange with Bob...
──────────────────────────────────────────────────────────────
✓ Sent our public key
✓ Sent key request
──────────────────────────────────────────────────────────────

✅ Key exchange initiated with Bob

📥 What happens next:
   1. They receive your public key (auto-imported)
   2. They receive your key request (auto-responded)
   3. You receive their key (auto-imported)

⏱️  Wait ~5-10 seconds for messages to arrive
   Then check: pgp list
   Then test:  pgp send Bob Hello encrypted!
```

### Client B (Windows) - Auto-responds:
```
✓ [PGP] Received public key from Alice
✓ [PGP] Auto-imported and trusted key for Alice
  You can now send encrypted messages: pgp send Alice <message>

✓ [PGP] Received key request from Alice
✓ [PGP] Automatically sent our public key in response
```

### Back on Client A:
```
✓ [PGP] Received public key from Bob
✓ [PGP] Auto-imported and trusted key for Bob
  You can now send encrypted messages: pgp send Bob <message>
```

### Verify Exchange Worked:
```bash
# Check both keys are imported
pgp list

# Should show:
★ YOUR_KEY_ID: F.Cli <...>
  BOB_KEY_ID: Bob <...>
```

### Send Encrypted Message:
```bash
pgp send Bob Hello! This is encrypted!
```

## How It Works

### Automatic Key Request/Response

**When you send `pgp import <contact>`:**
1. Sends special "PGP_KEY_REQUEST" message
2. Their client auto-detects it
3. Their client auto-responds with their public key
4. Your client auto-imports their key
5. ✅ Done!

**When you send `pgp exchange <contact>`:**
1. Sends YOUR public key
2. Sends key request
3. They auto-import your key
4. They auto-respond with their key
5. You auto-import their key
6. ✅ Both sides have keys!

### Automatic Key Import

**When you receive a PGP public key:**
- Plugin detects `-----BEGIN PGP PUBLIC KEY BLOCK-----`
- Checks if you already have this contact's key
- If not, automatically imports and trusts it
- Notifies you: "Auto-imported key for [Contact]"
- Ready to use immediately!

## Testing Between Two Clients

### Setup (One-time):

**Both clients must have:**
1. Plugin installed and loaded
2. PGP key generated (`pgp status` shows key)
3. Each other in contacts list

### Method 1: Full Exchange (Recommended)

**Client A:**
```bash
pgp exchange Bob
```

**Wait 5-10 seconds**

**Done!** Both clients now have each other's keys.

### Method 2: Manual Request

**Client A:**
```bash
pgp import Bob
```

**Client B:**
```bash
pgp import Alice
```

**Wait a few seconds** - keys auto-exchange!

### Method 3: Manual (Old Way - Still Works)

**Client A:**
```bash
pgp export
# Copy output
send Bob <paste key>
```

**Client B receives:**
- Plugin auto-imports the key automatically!

## Verification

Check keys are imported:
```bash
pgp list
```

Should show both your key (★) and contact's key.

## Send Encrypted Messages

```bash
# Now just send normally:
pgp send Bob Secret message!

# Or enable auto-mode:
pgp set auto_encrypt on
send Bob This is also encrypted!
```

## Troubleshooting

### "No public key for contact"
```bash
# Check if key exists
pgp list

# If not, exchange again
pgp exchange <contact>
```

### Key exchange seems stuck
```bash
# Check messages arrived
messages

# Manually check for key
pgp import <contact>
```

### Want to re-exchange keys
```bash
# Import will ask for confirmation if key exists
pgp exchange <contact>
```

## Advanced: Auto-Exchange on First Contact

You can send your key to someone automatically:

```bash
# Add new contact
add Charlie <hash>

# Exchange keys immediately
pgp exchange Charlie

# Or just import (one-way)
pgp import Charlie
```

They'll receive:
1. Your public key (auto-imported)
2. A key request (auto-responded)

You'll receive:
1. Their public key (auto-imported)

Both ready to encrypt! 🔐

## Benefits of Automated Exchange

✅ **No copy/paste** - Everything automatic  
✅ **No manual trust** - Auto-imported and trusted  
✅ **Bidirectional** - Both sides get keys  
✅ **Fast** - Takes 5-10 seconds  
✅ **Simple** - One command: `pgp exchange <contact>`  

## Examples

### Example 1: Fresh Setup
```bash
# Alice and Bob just met
Alice> add Bob <hash>
Alice> pgp exchange Bob

[wait 10 seconds]

Alice> pgp send Bob Hey! This is encrypted!
Bob> pgp send Alice Got it! Replying encrypted too!
```

### Example 2: Group Setup
```bash
# Alice sets up with multiple people
add Bob <hash>
add Charlie <hash>
add Dave <hash>

pgp exchange Bob
pgp exchange Charlie
pgp exchange Dave

[wait a minute]

# Now can send encrypted to all
pgp send Bob Secret for Bob
pgp send Charlie Secret for Charlie
pgp send Dave Secret for Dave
```

### Example 3: Verify Exchange
```bash
# Check status
pgp list

# Test encryption
pgp send Bob Test message

# Bob receives encrypted ✓
```

That's it! Key exchange is now fully automated! 🎉
