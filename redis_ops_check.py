#!/usr/bin/env python3
"""
Redis Operations Check - One-shot diagnostic tool
Displays all critical operational metrics with pass/fail status
"""

import sys
import redis
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box


def check_redis_ops(host='127.0.0.1', port=6379):
    console = Console()
    
    try:
        r = redis.Redis(host=host, port=port, decode_responses=True, socket_connect_timeout=5)
        r.ping()
    except Exception as e:
        console.print(f"[red]❌ Cannot connect to Redis: {e}[/red]")
        return 1
    
    console.print("[bold blue]Redis Operational Status Check[/bold blue]\n")
    
    # Collect all info
    sections = {
        'server': r.info('server'),
        'clients': r.info('clients'),
        'memory': r.info('memory'),
        'persistence': r.info('persistence'),
        'stats': r.info('stats'),
        'replication': r.info('replication'),
        'cpu': r.info('cpu'),
        'keyspace': r.info('keyspace'),
    }
    
    # Calculate metrics
    mem = sections['memory']
    stats = sections['stats']
    
    maxmemory = mem.get('maxmemory', 0)
    used_memory = mem.get('used_memory', 0)
    memory_pct = (used_memory / maxmemory * 100) if maxmemory > 0 else 0
    
    hits = stats.get('keyspace_hits', 0)
    misses = stats.get('keyspace_misses', 0)
    total = hits + misses
    hit_rate = (hits / total * 100) if total > 0 else 0
    
    # Status checks
    checks = []
    
    # 1. Memory Check
    if memory_pct > 95:
        checks.append(('🔴 CRITICAL', 'Memory', f'{memory_pct:.1f}% used - Imminent OOM!'))
    elif memory_pct > 80:
        checks.append(('🟡 WARNING', 'Memory', f'{memory_pct:.1f}% used - Approaching limit'))
    else:
        checks.append(('🟢 OK', 'Memory', f'{memory_pct:.1f}% used'))
    
    # 2. Fragmentation Check
    frag = mem.get('mem_fragmentation_ratio', 0)
    if frag > 2.0:
        checks.append(('🟡 WARNING', 'Fragmentation', f'{frag:.2f} - Consider restart'))
    else:
        checks.append(('🟢 OK', 'Fragmentation', f'{frag:.2f}'))
    
    # 3. Evictions Check (CRITICAL for Magento)
    evicted = stats.get('evicted_keys', 0)
    if evicted > 0:
        checks.append(('🔴 CRITICAL', 'Evictions', f'{evicted} keys evicted - Memory pressure!'))
    else:
        checks.append(('🟢 OK', 'Evictions', '0 keys evicted'))
    
    # 4. Hit Rate Check
    if hit_rate < 50:
        checks.append(('🔴 CRITICAL', 'Hit Rate', f'{hit_rate:.1f}% - Cache ineffective'))
    elif hit_rate < 70:
        checks.append(('🟡 WARNING', 'Hit Rate', f'{hit_rate:.1f}% - Below optimal'))
    else:
        checks.append(('🟢 OK', 'Hit Rate', f'{hit_rate:.1f}%'))
    
    # 5. Clients Check
    clients = sections['clients'].get('connected_clients', 0)
    maxclients = sections['clients'].get('maxclients', 10000)
    if clients > maxclients * 0.8:
        checks.append(('🟡 WARNING', 'Clients', f'{clients} connected (high)'))
    else:
        checks.append(('🟢 OK', 'Clients', f'{clients} connected'))
    
    # 6. Persistence Check
    persist = sections['persistence']
    rdb_ok = persist.get('rdb_last_bgsave_status') == 'ok'
    if rdb_ok:
        checks.append(('🟢 OK', 'RDB Save', 'Last save successful'))
    else:
        checks.append(('🔴 CRITICAL', 'RDB Save', f"Status: {persist.get('rdb_last_bgsave_status', 'N/A')}"))
    
    # 7. AOF Check (if enabled)
    if persist.get('aof_enabled'):
        aof_ok = persist.get('aof_last_write_status') == 'ok'
        if aof_ok:
            checks.append(('🟢 OK', 'AOF Write', 'Last write successful'))
        else:
            checks.append(('🔴 CRITICAL', 'AOF Write', f"Status: {persist.get('aof_last_write_status', 'N/A')}"))
    
    # 8. Replication Check (if slave)
    repl = sections['replication']
    if repl.get('role') == 'slave':
        link_up = repl.get('master_link_status') == 'up'
        if link_up:
            checks.append(('🟢 OK', 'Replication', 'Link UP'))
        else:
            checks.append(('🔴 CRITICAL', 'Replication', 'Link DOWN!'))
    
    # 9. Rejected Connections
    rejected = stats.get('rejected_connections', 0)
    if rejected > 0:
        checks.append(('🟡 WARNING', 'Rejected Conns', f'{rejected} connections rejected'))
    else:
        checks.append(('🟢 OK', 'Rejected Conns', '0 rejected'))
    
    # 10. Expired Keys Rate
    expired = stats.get('expired_keys', 0)
    checks.append(('🟢 INFO', 'Expired Keys', f'{expired:,} total'))
    
    # Print summary table
    table = Table(box=box.ROUNDED)
    table.add_column("Status", width=12)
    table.add_column("Check", width=15)
    table.add_column("Details")
    
    critical_count = 0
    warning_count = 0
    
    for status, check, detail in checks:
        if 'CRITICAL' in status:
            critical_count += 1
            style = "red"
        elif 'WARNING' in status:
            warning_count += 1
            style = "yellow"
        else:
            style = "green"
        
        table.add_row(status, check, detail, style=style)
    
    console.print(table)
    
    # Overall status
    console.print("\n[bold]Overall Status:[/bold]", end=" ")
    if critical_count > 0:
        console.print(f"[bold red]🔴 CRITICAL - {critical_count} critical issues found[/bold red]")
        return 2
    elif warning_count > 0:
        console.print(f"[bold yellow]🟡 WARNING - {warning_count} warnings[/bold yellow]")
        return 1
    else:
        console.print("[bold green]🟢 HEALTHY - All checks passed[/bold green]")
        return 0
    

if __name__ == "__main__":
    sys.exit(check_redis_ops())
