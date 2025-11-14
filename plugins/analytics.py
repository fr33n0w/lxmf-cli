"""
Advanced Analytics Plugin for LXMF-CLI
Detailed messaging statistics and insights
"""
import time
from collections import defaultdict
from datetime import datetime

class Plugin:
    def __init__(self, client):
        self.client = client
        self.commands = ['analytics', 'mystats']
        self.description = "Advanced messaging analytics"
        print("✓ Analytics loaded! Use 'analytics' to view stats")
    
    def handle_command(self, cmd, parts):
        with self.client.messages_lock:
            messages = self.client.messages.copy()
        
        if not messages:
            print("\n📊 No messages to analyze\n")
            return
        
        # Calculate statistics
        total = len(messages)
        sent = sum(1 for m in messages if m['direction'] == 'outbound')
        received = sum(1 for m in messages if m['direction'] == 'inbound')
        
        # Time-based stats
        now = time.time()
        last_24h = sum(1 for m in messages if (now - m['timestamp']) < 86400)
        last_week = sum(1 for m in messages if (now - m['timestamp']) < 604800)
        last_month = sum(1 for m in messages if (now - m['timestamp']) < 2592000)
        
        # Most active contacts
        contact_counts = defaultdict(int)
        for msg in messages:
            if msg['direction'] == 'outbound':
                hash_key = msg.get('destination_hash', 'unknown')
            else:
                hash_key = msg.get('source_hash', 'unknown')
            
            if hash_key != 'unknown':
                contact_counts[hash_key] += 1
        
        top_contacts = sorted(contact_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Busiest hour
        hours = defaultdict(int)
        for msg in messages:
            hour = datetime.fromtimestamp(msg['timestamp']).hour
            hours[hour] += 1
        busiest_hour = max(hours.items(), key=lambda x: x[1])[0] if hours else 0
        
        # Display analytics
        print(f"\n{'='*70}")
        print("📊 MESSAGING ANALYTICS")
        print(f"{'='*70}\n")
        
        print(f"📈 Overview:")
        print(f"  Total messages: {total}")
        print(f"  Sent: {sent} ({sent/total*100:.1f}%)")
        print(f"  Received: {received} ({received/total*100:.1f}%)")
        
        if sent > 0 and received > 0:
            ratio = sent / received
            if ratio > 1:
                print(f"  You send {ratio:.1f}x more than you receive")
            else:
                print(f"  You receive {1/ratio:.1f}x more than you send")
        
        print(f"\n📅 Recent Activity:")
        print(f"  Last 24 hours: {last_24h} messages")
        print(f"  Last 7 days: {last_week} messages")
        print(f"  Last 30 days: {last_month} messages")
        
        print(f"\n👥 Top 5 Most Active Contacts:")
        if top_contacts:
            for idx, (hash_str, count) in enumerate(top_contacts, 1):
                name = self.client.format_contact_display_short(hash_str)
                percentage = (count / total) * 100
                print(f"  {idx}. {name}: {count} messages ({percentage:.1f}%)")
        else:
            print("  No contact data")
        
        print(f"\n⏰ Messaging Patterns:")
        print(f"  Busiest hour: {busiest_hour:02d}:00")
        
        # Show hourly distribution (compact view)
        if hours:
            max_hour_count = max(hours.values())
            print(f"\n  📊 Hourly Distribution:")
            
            # Group into time blocks for cleaner display
            for block_start in range(0, 24, 6):
                block_end = min(block_start + 6, 24)
                print(f"\n    {block_start:02d}:00 - {block_end:02d}:00")
                
                for h in range(block_start, block_end):
                    count = hours.get(h, 0)
                    bar_length = int((count / max_hour_count) * 15) if max_hour_count > 0 else 0
                    bar = '█' * bar_length
                    print(f"      {h:02d}:00 {bar:<15} {count}")
        
        # First and last message
        if messages:
            first_msg = min(messages, key=lambda x: x['timestamp'])
            last_msg = max(messages, key=lambda x: x['timestamp'])
            
            first_date = datetime.fromtimestamp(first_msg['timestamp']).strftime('%Y-%m-%d')
            last_date = datetime.fromtimestamp(last_msg['timestamp']).strftime('%Y-%m-%d %H:%M')
            
            print(f"\n📆 Timeline:")
            print(f"  First message: {first_date}")
            print(f"  Last message: {last_date}")
            
            days_active = (last_msg['timestamp'] - first_msg['timestamp']) / 86400
            if days_active > 1:
                avg_per_day = total / days_active
                print(f"  Average: {avg_per_day:.1f} messages/day")
                print(f"  Days active: {days_active:.1f}")
        
        print(f"\n{'='*70}\n")

if __name__ == '__main__':
    print("This is a plugin for LXMF Client")
    print("Place in: ./lxmf_client_storage/plugins/")