#!/usr/bin/env python3
"""
Redis Cache Visualizer for Magento 2
A beautiful TUI tool for exploring and analyzing Redis cache contents
"""

import redis
import json
import time
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.syntax import Syntax
from rich.tree import Tree
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich import box

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, Input, Button, Label, ListView, ListItem
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive


@dataclass
class CacheKeyInfo:
    """Information about a cache key"""
    key: str
    type: str
    size: int
    ttl: Optional[int]
    value_preview: str
    database: int


class RedisCacheAnalyzer:
    """Analyzes Redis cache contents"""
    
    def __init__(self, host='127.0.0.1', port=6379, password=None):
        self.host = host
        self.port = port
        self.password = password
        self.redis_client = None
        self.console = Console()
        
    def connect(self) -> bool:
        """Connect to Redis server"""
        try:
            self.redis_client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                decode_responses=True,
                socket_connect_timeout=5
            )
            return self.redis_client.ping()
        except Exception as e:
            self.console.print(f"[red]Failed to connect to Redis: {e}[/red]")
            return False
    
    def get_server_info(self) -> Dict:
        """Get Redis server information"""
        info = self.redis_client.info()
        return {
            'version': info.get('redis_version', 'Unknown'),
            'uptime': info.get('uptime_in_days', 0),
            'memory_used': info.get('used_memory_human', 'Unknown'),
            'memory_peak': info.get('used_memory_peak_human', 'Unknown'),
            'total_keys': sum(db.get('keys', 0) for db in self.get_databases().values()),
            'hit_rate': self._calculate_hit_rate(info),
            'connected_clients': info.get('connected_clients', 0),
        }
    
    def _calculate_hit_rate(self, info: Dict) -> float:
        """Calculate cache hit rate"""
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)
        total = hits + misses
        return (hits / total * 100) if total > 0 else 0.0
    
    def get_databases(self) -> Dict[int, Dict]:
        """Get all databases and their key counts"""
        keyspace = self.redis_client.info('keyspace')
        databases = {}
        for key, data in keyspace.items():
            if key.startswith('db'):
                db_num = int(key[2:])
                databases[db_num] = {
                    'keys': data.get('keys', 0),
                    'expires': data.get('expires', 0),
                    'avg_ttl': data.get('avg_ttl', 0)
                }
        return databases
    
    def scan_keys(self, database: int = 0, pattern: str = '*', count: int = 1000) -> List[str]:
        """Scan keys in a database"""
        self.redis_client.execute_command('SELECT', database)
        keys = []
        cursor = 0
        while True:
            cursor, batch = self.redis_client.scan(cursor=cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0 or len(keys) >= count:
                break
        return keys[:count]
    
    def get_key_info(self, key: str, database: int = 0) -> Optional[CacheKeyInfo]:
        """Get detailed information about a key"""
        try:
            self.redis_client.execute_command('SELECT', database)
            key_type = self.redis_client.type(key)
            ttl = self.redis_client.ttl(key)
            ttl = None if ttl == -1 else ttl
            
            # Get memory usage
            memory = self.redis_client.memory_usage(key) or 0
            
            # Get value preview
            value_preview = self._get_value_preview(key, key_type)
            
            return CacheKeyInfo(
                key=key,
                type=key_type,
                size=memory,
                ttl=ttl,
                value_preview=value_preview,
                database=database
            )
        except Exception as e:
            return None
    
    def _get_value_preview(self, key: str, key_type: str) -> str:
        """Get a preview of the value"""
        try:
            if key_type == 'string':
                value = self.redis_client.get(key)
                if value:
                    # Try to parse as JSON
                    try:
                        json.loads(value)
                        return value[:200] + "..." if len(value) > 200 else value
                    except:
                        return value[:200] + "..." if len(value) > 200 else value
                return "(empty)"
            elif key_type == 'hash':
                return f"{self.redis_client.hlen(key)} fields"
            elif key_type == 'list':
                return f"{self.redis_client.llen(key)} items"
            elif key_type == 'set':
                return f"{self.redis_client.scard(key)} members"
            elif key_type == 'zset':
                return f"{self.redis_client.zcard(key)} members"
            else:
                return f"Type: {key_type}"
        except Exception as e:
            return f"Error: {str(e)[:50]}"
    
    def analyze_patterns(self, keys: List[str]) -> Dict[str, int]:
        """Analyze key patterns"""
        patterns = defaultdict(int)
        for key in keys:
            # Extract pattern (e.g., "zc:k:eec_CONFIG" -> "CONFIG")
            if ':' in key:
                parts = key.split(':')
                if len(parts) >= 2:
                    pattern = ':'.join(parts[-2:]) if parts[-1].startswith('eec_') else parts[-1]
                    patterns[pattern] += 1
            else:
                patterns['other'] += 1
        return dict(sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:20])
    
    def get_cache_tags(self, database: int = 0) -> Dict[str, List[str]]:
        """Get cache tags and their associated keys"""
        self.redis_client.execute_command('SELECT', database)
        tags = {}
        try:
            tag_keys = self.redis_client.smembers('zc:tags')
            for tag in list(tag_keys)[:50]:  # Limit to 50 tags
                keys = self.redis_client.smembers(f'zc:ti:{tag}')
                tags[tag] = list(keys)[:10]  # Limit to 10 keys per tag
        except:
            pass
        return tags


class CacheVisualizerApp(App):
    """Textual TUI Application for Redis Cache Visualization"""
    
    CSS = """
    Screen { align: center middle; }
    
    #main-container {
        width: 100%;
        height: 100%;
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1;
    }
    
    .panel {
        border: solid green;
        padding: 1 2;
    }
    
    #stats-panel {
        row-span: 1;
        column-span: 2;
    }
    
    #keys-panel {
        row-span: 1;
    }
    
    #patterns-panel {
        row-span: 1;
    }
    
    DataTable {
        height: 100%;
    }
    
    Input {
        dock: top;
        margin-bottom: 1;
    }
    
    .title {
        text-align: center;
        text-style: bold;
        color: $accent;
    }
    """
    
    def __init__(self, analyzer: RedisCacheAnalyzer):
        self.analyzer = analyzer
        self.keys_data = []
        super().__init__()
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="main-container"):
            # Statistics Panel
            with Container(id="stats-panel", classes="panel"):
                yield Static(id="stats-content")
            
            # Keys Browser Panel
            with Container(id="keys-panel", classes="panel"):
                yield Label("🔍 Cache Keys Browser", classes="title")
                yield Input(placeholder="Filter keys (e.g., CONFIG, eec_*)...", id="key-filter")
                yield DataTable(id="keys-table")
            
            # Patterns Panel
            with Container(id="patterns-panel", classes="panel"):
                yield Label("📊 Key Patterns", classes="title")
                yield Static(id="patterns-content")
        
        yield Footer()
    
    def on_mount(self):
        """Initialize data on mount"""
        self.update_stats()
        self.update_keys()
        self.update_patterns()
        self.set_interval(5, self.update_stats)
    
    def update_stats(self):
        """Update statistics display"""
        info = self.analyzer.get_server_info()
        databases = self.analyzer.get_databases()
        
        stats_text = f"""
[bold cyan]Redis Server Information[/bold cyan]
├─ Version: [green]{info['version']}[/green]
├─ Uptime: [yellow]{info['uptime']} days[/yellow]
├─ Memory Used: [red]{info['memory_used']}[/red]
├─ Memory Peak: [magenta]{info['memory_peak']}[/magenta]
├─ Hit Rate: [green]{info['hit_rate']:.1f}%[/green]
├─ Connected Clients: [blue]{info['connected_clients']}[/blue]
└─ Total Keys: [bold]{info['total_keys']}[/bold]

[bold cyan]Database Details[/bold cyan]
"""
        for db_num, db_info in databases.items():
            stats_text += f"├─ DB {db_num}: [green]{db_info['keys']}[/green] keys, [yellow]{db_info['expires']}[/yellow] expiring\n"
        
        self.query_one("#stats-content", Static).update(stats_text)
    
    def update_keys(self, pattern: str = '*'):
        """Update keys table"""
        table = self.query_one("#keys-table", DataTable)
        table.clear()
        table.add_columns("Key", "Type", "Size", "TTL", "Preview")
        
        keys = self.analyzer.scan_keys(pattern=pattern, count=100)
        self.keys_data = []
        
        for key in keys:
            info = self.analyzer.get_key_info(key)
            if info:
                self.keys_data.append(info)
                ttl_str = f"{info.ttl}s" if info.ttl else "∞"
                size_str = self._format_bytes(info.size)
                table.add_row(
                    info.key[:50],
                    info.type,
                    size_str,
                    ttl_str,
                    info.value_preview[:40]
                )
    
    def _format_bytes(self, size: int) -> str:
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def update_patterns(self):
        """Update patterns display"""
        keys = self.analyzer.scan_keys(count=1000)
        patterns = self.analyzer.analyze_patterns(keys)
        
        pattern_text = "[bold]Top Key Patterns:[/bold]\n"
        for pattern, count in patterns.items():
            bar = "█" * min(count, 20)
            pattern_text += f"{pattern[:30]:30} [cyan]{bar}[/cyan] {count}\n"
        
        self.query_one("#patterns-content", Static).update(pattern_text)
    
    def on_input_changed(self, event: Input.Changed):
        """Handle filter input changes"""
        if event.input.id == "key-filter":
            pattern = event.value if event.value else "*"
            self.update_keys(pattern)


def print_rich_dashboard(analyzer: RedisCacheAnalyzer):
    """Print a rich dashboard to the console (non-interactive)"""
    console = Console()
    
    # Server Info Panel
    info = analyzer.get_server_info()
    
    server_table = Table(show_header=False, box=box.ROUNDED)
    server_table.add_column("Property", style="cyan", width=20)
    server_table.add_column("Value", style="white")
    server_table.add_row("Redis Version", info['version'])
    server_table.add_row("Uptime", f"{info['uptime']} days")
    server_table.add_row("Memory Used", f"[red]{info['memory_used']}[/red]")
    server_table.add_row("Memory Peak", f"[magenta]{info['memory_peak']}[/magenta]")
    server_table.add_row("Cache Hit Rate", f"[green]{info['hit_rate']:.1f}%[/green]")
    server_table.add_row("Connected Clients", str(info['connected_clients']))
    server_table.add_row("Total Keys", f"[bold]{info['total_keys']}[/bold]")
    
    console.print(Panel(server_table, title="[bold blue]Redis Server Status[/bold blue]", border_style="blue"))
    
    # Database Info
    databases = analyzer.get_databases()
    db_table = Table(title="[bold cyan]Database Statistics[/bold cyan]", box=box.SIMPLE)
    db_table.add_column("DB", style="bold")
    db_table.add_column("Keys", justify="right", style="green")
    db_table.add_column("Expiring", justify="right", style="yellow")
    db_table.add_column("Avg TTL", justify="right", style="blue")
    
    for db_num, db_info in databases.items():
        avg_ttl = db_info.get('avg_ttl', 0)
        ttl_str = f"{avg_ttl/1000:.0f}s" if avg_ttl else "∞"
        db_table.add_row(
            f"DB {db_num}",
            str(db_info['keys']),
            str(db_info['expires']),
            ttl_str
        )
    
    console.print(db_table)
    
    # Key Patterns
    keys = analyzer.scan_keys(count=500)
    patterns = analyzer.analyze_patterns(keys)
    
    pattern_table = Table(title="[bold cyan]Top Key Patterns[/bold cyan]", box=box.SIMPLE)
    pattern_table.add_column("Pattern", style="yellow")
    pattern_table.add_column("Count", justify="right", style="green")
    pattern_table.add_column("Distribution", width=30)
    
    max_count = max(patterns.values()) if patterns else 1
    for pattern, count in patterns.items():
        bar_length = int((count / max_count) * 20)
        bar = "█" * bar_length
        percentage = (count / len(keys)) * 100 if keys else 0
        pattern_table.add_row(pattern, str(count), f"[cyan]{bar}[/cyan] {percentage:.1f}%")
    
    console.print(pattern_table)
    
    # Recent Keys
    key_table = Table(title="[bold cyan]Sample Cache Keys (DB 0)[/bold cyan]", box=box.SIMPLE)
    key_table.add_column("Key", style="white", width=40)
    key_table.add_column("Type", style="magenta", width=10)
    key_table.add_column("Size", justify="right", style="green", width=10)
    key_table.add_column("TTL", justify="right", style="yellow", width=8)
    key_table.add_column("Preview", style="dim", width=30)
    
    sample_keys = analyzer.scan_keys(count=20)
    for key in sample_keys[:10]:
        info = analyzer.get_key_info(key)
        if info:
            ttl_str = f"{info.ttl}s" if info.ttl else "∞"
            size_str = f"{info.size/1024:.1f}KB" if info.size > 1024 else f"{info.size}B"
            key_table.add_row(
                info.key[:38],
                info.type,
                size_str,
                ttl_str,
                info.value_preview[:28]
            )
    
    console.print(key_table)
    
    # Cache Tags
    tags = analyzer.get_cache_tags()
    if tags:
        tag_tree = Tree("[bold cyan]Cache Tags Structure[/bold cyan]")
        for tag, keys in list(tags.items())[:10]:
            tag_node = tag_tree.add(f"[yellow]{tag}[/yellow]")
            for key in keys[:5]:
                tag_node.add(f"[dim]{key[:40]}[/dim]")
            if len(keys) > 5:
                tag_node.add(f"[dim]... and {len(keys) - 5} more[/dim]")
        console.print(tag_tree)


def main():
    """Main entry point"""
    console = Console()
    
    console.print("[bold blue]Redis Cache Visualizer for Magento 2[/bold blue]\n")
    
    # Initialize analyzer
    analyzer = RedisCacheAnalyzer(host='127.0.0.1', port=6379)
    
    if not analyzer.connect():
        console.print("[red]Failed to connect to Redis. Make sure Redis is running on 127.0.0.1:6379[/red]")
        sys.exit(1)
    
    console.print("[green]✓ Connected to Redis[/green]\n")
    
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
        # Run interactive TUI
        app = CacheVisualizerApp(analyzer)
        app.run()
    else:
        # Run non-interactive dashboard
        print_rich_dashboard(analyzer)
        
        console.print("\n[dim]Tip: Run with --interactive for a TUI experience[/dim]")


if __name__ == "__main__":
    main()
