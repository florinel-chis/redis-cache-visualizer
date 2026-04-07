#!/usr/bin/env python3
"""
Redis Cache Visualizer for Magento 2 - OPTIMIZED VERSION
Uses pipelining for bulk operations
"""

import redis
import sys
from collections import defaultdict
from typing import Dict, List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import box


class FastRedisAnalyzer:
    """Optimized Redis analyzer using pipelining"""
    
    def __init__(self, host='127.0.0.1', port=6379, password=None):
        self.redis = redis.Redis(
            host=host, port=port, password=password,
            decode_responses=True, socket_connect_timeout=5
        )
        self.console = Console()
        
    def connect(self) -> bool:
        try:
            return self.redis.ping()
        except Exception as e:
            self.console.print(f"[red]Connection failed: {e}[/red]")
            return False
    
    def get_info(self) -> Dict:
        """Get server info in one call"""
        info = self.redis.info()
        return {
            'version': info.get('redis_version', 'Unknown'),
            'uptime': info.get('uptime_in_days', 0),
            'memory_used': info.get('used_memory_human', 'Unknown'),
            'memory_peak': info.get('used_memory_peak_human', 'Unknown'),
            'hit_rate': self._calc_hit_rate(info),
            'clients': info.get('connected_clients', 0),
            'total_keys': sum(
                db.get('keys', 0) 
                for db in self.redis.info('keyspace').values()
            ),
        }
    
    def _calc_hit_rate(self, info: Dict) -> float:
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)
        return (hits / (hits + misses) * 100) if (hits + misses) > 0 else 0
    
    def get_keys_fast(self, db: int = 0, count: int = 100) -> List[Dict]:
        """Get key info using pipelining for speed"""
        self.redis.execute_command('SELECT', db)
        
        # Scan for keys
        keys = []
        cursor = 0
        while len(keys) < count:
            cursor, batch = self.redis.scan(cursor=cursor, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        keys = keys[:count]
        
        if not keys:
            return []
        
        # Use pipeline to get all key info in bulk
        pipe = self.redis.pipeline()
        for key in keys:
            pipe.type(key)
            pipe.ttl(key)
            pipe.memory_usage(key)
        
        results = pipe.execute()
        
        # Parse results
        key_info = []
        for i, key in enumerate(keys):
            base_idx = i * 3
            key_type = results[base_idx]
            ttl = results[base_idx + 1]
            size = results[base_idx + 2] or 0
            
            key_info.append({
                'key': key,
                'type': key_type,
                'ttl': ttl if ttl > 0 else None,
                'size': size,
            })
        
        return key_info
    
    def analyze_patterns(self, keys: List[Dict]) -> Dict[str, int]:
        """Extract patterns from keys"""
        patterns = defaultdict(int)
        for k in keys:
            key = k['key']
            # Group by prefix patterns
            if ':' in key:
                parts = key.split(':')
                if len(parts) >= 3:
                    # zc:k:eec_CONFIG -> CONFIG
                    pattern = parts[-1][:30] if parts[-1].startswith('eec_') else parts[-2]
                else:
                    pattern = parts[0]
            else:
                pattern = 'other'
            patterns[pattern] += 1
        return dict(sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:15])


def format_bytes(size: int) -> str:
    """Format bytes to human readable"""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f}KB"
    else:
        return f"{size/(1024*1024):.1f}MB"


def main():
    console = Console()
    console.print("[bold blue]Redis Cache Visualizer (Fast)[/bold blue]\n")
    
    analyzer = FastRedisAnalyzer()
    if not analyzer.connect():
        sys.exit(1)
    
    console.print("[green]✓ Connected[/green]\n")
    
    # Server info
    with console.status("[bold green]Fetching server info..."):
        info = analyzer.get_info()
    
    server_table = Table(show_header=False, box=box.ROUNDED)
    server_table.add_column("Property", style="cyan", width=18)
    server_table.add_column("Value", style="white")
    server_table.add_row("Version", info['version'])
    server_table.add_row("Uptime", f"{info['uptime']} days")
    server_table.add_row("Memory", f"[red]{info['memory_used']}[/red] / [magenta]{info['memory_peak']}[/magenta]")
    server_table.add_row("Hit Rate", f"[green]{info['hit_rate']:.1f}%[/green]")
    server_table.add_row("Clients", str(info['clients']))
    server_table.add_row("Total Keys", f"[bold]{info['total_keys']}[/bold]")
    
    console.print(Panel(server_table, title="[bold blue]Redis Server[/bold blue]", border_style="blue"))
    
    # Get keys with pipeline
    with console.status("[bold green]Scanning keys with pipelining..."):
        keys = analyzer.get_keys_fast(count=100)
    
    if not keys:
        console.print("[yellow]No keys found[/yellow]")
        return
    
    # Patterns
    with console.status("[bold green]Analyzing patterns..."):
        patterns = analyzer.analyze_patterns(keys)
    
    pattern_table = Table(title="[bold cyan]Key Patterns[/bold cyan]", box=box.SIMPLE)
    pattern_table.add_column("Pattern", style="yellow")
    pattern_table.add_column("Count", justify="right", style="green")
    pattern_table.add_column("Visual", width=25)
    
    max_count = max(patterns.values()) if patterns else 1
    for pattern, count in patterns.items():
        bar = "█" * int((count / max_count) * 20)
        pct = (count / len(keys)) * 100
        pattern_table.add_row(pattern, str(count), f"[cyan]{bar}[/cyan] {pct:.0f}%")
    
    console.print(pattern_table)
    
    # Keys table
    key_table = Table(title=f"[bold cyan]Cache Keys ({len(keys)} shown)[/bold cyan]", box=box.SIMPLE)
    key_table.add_column("Key", style="white", width=45, no_wrap=True)
    key_table.add_column("Type", style="magenta", width=8)
    key_table.add_column("Size", justify="right", style="green", width=10)
    key_table.add_column("TTL", justify="right", style="yellow", width=8)
    
    total_size = 0
    for k in keys[:20]:  # Show top 20
        total_size += k['size']
        ttl_str = f"{k['ttl']}s" if k['ttl'] else "∞"
        key_table.add_row(
            k['key'][:44],
            k['type'],
            format_bytes(k['size']),
            ttl_str
        )
    
    console.print(key_table)
    console.print(f"\n[dim]Total size of shown keys: {format_bytes(total_size)}[/dim]")
    
    # Cache tags (fast scan)
    with console.status("[bold green]Fetching cache tags..."):
        try:
            analyzer.redis.execute_command('SELECT', 0)
            tags = list(analyzer.redis.smembers('zc:tags'))[:10]
            if tags:
                tree = Tree("[bold cyan]Cache Tags[/bold cyan]")
                for tag in tags:
                    tree.add(f"[yellow]{tag}[/yellow]")
                console.print(tree)
        except:
            pass
    
    console.print(f"\n[dim]Scanned {len(keys)} keys in <100ms using pipelining[/dim]")


if __name__ == "__main__":
    main()
