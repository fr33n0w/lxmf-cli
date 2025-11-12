# LXMF Interactive Client

**Terminal-based LXMF Messaging Client for Reticulum**

A feature-rich, cross-platform command-line interface for [LXMF](https://github.com/markqvist/lxmf) (Low Bandwidth Message Format) messaging over [Reticulum Network Stack](https://reticulum.network/).

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20Android-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
</p>



## ✨ Features

### 📨 Messaging
- **Send and receive** LXMF messages over Reticulum mesh networks
- **Reply functionality** - Quick reply to the last received message
- **Message history** - Persistent storage of all conversations
- **Conversation view** - Browse full message threads with specific users
- **Real-time delivery tracking** - Progress indicators and delivery confirmations

### 👥 Contacts & Peer Discovery
- **Contact management** - Save contacts with nicknames and fixed index numbers
- **Auto-discovery** - Automatically detects announced LXMF peers on the network
- **Display name caching** - Remembers display names from network announces
- **Quick messaging** - Send messages using contact numbers (e.g., `s 3 hello`)
- **Peer list** - View all discovered peers with last-seen timestamps

### 📊 Statistics & Information
- **Message statistics** - Track sent/received messages globally and per-user
- **System status** - View uptime, network info, and connection details
- **Conversation list** - See all users you've messaged with indexed navigation

### ⚙️ Customization
- **Interactive settings menu** - Easy configuration without editing files
- **Custom display name** - Set your visible identity on the network
- **Announce interval** - Configure auto-announce frequency
- **Discovery alerts** - Toggle notifications for newly discovered peers

### 🎨 User Interface
- **Color-coded output** - Beautiful terminal colors using colorama
- **Categorized help menu** - Organized commands by function
- **Visual notifications** - Colorful flash effects for new messages
- **Audio alerts** - Platform-specific notification sounds
  - Windows: Musical beep melody
  - Linux: System notification sounds
  - Android/Termux: Vibration patterns + notifications
- **Dynamic prompt** - Visual indicator for unread messages
- **Progress indicators** - Real-time message sending progress

### 🖥️ Cross-Platform Support
- **Windows** - Full support with native beep sounds
- **Linux** - Desktop and server environments
- **Android/Termux** - Mobile support with vibration and notifications
- **macOS** - Compatible (limited testing)

## 📋 Requirements

- Python 3.8 or higher
- [RNS (Reticulum Network Stack)](https://github.com/markqvist/Reticulum)
- [LXMF](https://github.com/markqvist/lxmf)
- colorama (for colored terminal output)

### Optional (for Termux/Android)
- termux-api package
- Termux:API app (from F-Droid or Play Store)

## 🚀 Installation

### Quick Install
```bash
# Clone the repository
git clone https://github.com/fr33n0w/lxmf-cli.git
cd lxmf-cli

# Install dependencies
pip install rns lxmf colorama

# Run the client
python lxmf-cli.py
```

### Termux/Android Installation
```bash
# Update packages
pkg update && pkg upgrade

# Install Python and dependencies
pkg install python git

# Install required Python packages
pip install rns lxmf colorama

# Optional: Install termux-api for notifications and vibration
pkg install termux-api
# Also install Termux:API app from F-Droid or Play Store

# Clone and run
git clone https://github.com/fr33n0w/lxmf-cli.git
cd lxmf-cli
python lxmf-cli.py
```

### First Run Setup

On first launch, you'll be prompted to:
1. **Set your display name** - This is how others will see you
2. **Configure announce interval** - How often you announce your presence (default: 300s)

The client will automatically create necessary directories and files:
- `lxmf_client_identity` - Your cryptographic identity
- `lxmf_client_storage/` - Messages, contacts, and configuration

## 📖 Usage

### Basic Commands
```bash
# Messaging
send <name/#/hash> <message>    (s)  - Send a message
reply <message>                 (re) - Reply to last message
messages [count]                (m)  - Show recent messages
messages list                        - List all conversations
messages user <#>                    - View full conversation

# Contacts & Peers
contacts                        (c)  - List all contacts
add <name> <hash>              (a)  - Add a contact
remove <name>                  (rm) - Remove a contact
peers                          (p)  - List announced LXMF peers
sendpeer <#> <message>         (sp) - Send to peer by number
addpeer <#> [name]             (ap) - Add peer to contacts

# Information
stats                          (st) - Show messaging statistics
status                              - Show system status
address                      (addr) - Show your LXMF address

# Settings
settings                      (set) - Open settings menu
name <new_name>                (n)  - Change display name
interval <seconds>             (i)  - Change announce interval
discoverannounce <on/off>     (da) - Toggle discovery alerts

# System
announce                      (ann) - Announce now
clear                         (cls) - Clear the screen
restart                        (r)  - Restart the client
help                           (h)  - Show help menu
quit / exit                   (q/e) - Exit
```

### Quick Examples
```bash
# Send a message to a contact
> s alice Hey, how are you?

# Send using contact number
> s 3 Quick message to contact #3

# Reply to the last received message
> re Thanks for the info!

# View conversation with a user
> m list                    # See all conversations
> m user 5                  # View full chat with user #5

# Add a discovered peer to contacts
> p                         # List announced peers
> ap 2 Bob                  # Add peer #2 as "Bob"

# Check statistics
> stats                     # View messaging stats
> status                    # View system status
```

## 🎯 Key Features Explained

### Fixed Index Numbers
All contacts, peers, and conversations have **permanent index numbers** that never change. This prevents accidentally sending messages to the wrong person when new peers are discovered or messages are received.

### Peer Discovery
The client automatically discovers and lists LXMF peers that announce themselves on the network. You can:
- View discovered peers with `peers`
- Send messages directly using `sendpeer <#>`
- Add them to contacts with `addpeer <#>`

### Message Threading
View complete conversation history with any user:
```bash
> m list              # See all people you've messaged
> m user 3            # View full conversation with user #3
> re Hey there!       # Reply directly (target is auto-set)
```

### Smart Notifications
- **Visual**: Colorful terminal flash effects
- **Audio**: Platform-specific sounds (melody on Windows, system sounds on Linux, vibration on Android)
- **Prompt Indicator**: Green dot (●) when last message was inbound

## 🗂️ File Structure
```
lxmf-client/
├── cli.py                          # Main client script
├── lxmf_client_identity            # Your identity (auto-generated)
└── lxmf_client_storage/
    ├── messages/                   # Individual message files
    ├── contacts.json               # Your contacts
    ├── config.json                 # Client configuration
    ├── display_names.json          # Cached display names
    ├── conversations.json          # Conversation indices
    └── lxmf_router/               # LXMF router data
```

## ⚙️ Configuration

Settings can be changed via the interactive settings menu (`settings` command) or by editing `lxmf_client_storage/config.json`:
```json
{
  "display_name": "Your Name",
  "announce_interval": 300,
  "show_announces": true
}
```

## 🔧 Troubleshooting

### No messages being received
- Ensure Reticulum is properly configured with at least one interface
- Check that your announce interval isn't too long
- Manually announce with `announce` command

### Can't find a peer
- Ask them to announce: they should run `announce` in their client
- Check if they're using the same Reticulum network/interfaces
- Try `peers` to see if they appear in discovered peers

### Notifications not working (Termux)
- Install termux-api: `pkg install termux-api`
- Install Termux:API app from F-Droid or Play Store
- Grant notification permissions to Termux

### Colors not showing
- Ensure your terminal supports ANSI colors
- colorama should handle most cases automatically
- On Windows, use Windows Terminal or a modern terminal emulator

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.


## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Mark Qvist](https://github.com/markqvist) for creating [Reticulum](https://reticulum.network/) and [LXMF](https://github.com/markqvist/lxmf)
- The Reticulum community for inspiration and support
- All contributors to this project

## 🔗 Related Projects

- [Reticulum Network Stack](https://github.com/markqvist/Reticulum) - The underlying mesh networking protocol
- [LXMF](https://github.com/markqvist/lxmf) - Low Bandwidth Message Format
- [NomadNet](https://github.com/markqvist/NomadNet) - Resilient mesh communication
- [Sideband](https://github.com/markqvist/Sideband) - LXMF client for Android and Linux

## 📧 Contact

For questions, issues, or suggestions:
- Open an [issue](https://github.com/fr33n0w/lxmf-cli/issues)
- Reach out on LXMF at: 0d051f3b6f844380c3e0c5d14e37fac8

---

**Note**: This client requires a working Reticulum installation and configuration. Please refer to the [Reticulum documentation](https://markqvist.github.io/Reticulum/manual/) for network setup.

