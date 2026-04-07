# Redis Cache Visualizer for Magento 2

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Redis 6.0+](https://img.shields.io/badge/redis-6.0+-red.svg)](https://redis.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Production-safe tools for analyzing, monitoring, and managing Redis cache in Magento 2 environments. Features a web dashboard with interactive treemap visualization, health monitoring, and tag-based cache management.

![Dashboard Preview](https://via.placeholder.com/800x400/0f172a/60a5fa?text=Redis+Cache+Visualizer)

## 🚀 Quick Start

```bash
# Install dependencies
pip install redis redis-async

# Start the production dashboard
./production_dashboard.py

# Open http://localhost:8765
```

## 📋 Requirements

- Python 3.8+
- Redis 6.0+ (with Magento 2 cache)
- Modern web browser

## 📁 Tools Overview

| Tool | Purpose | Best For |
|------|---------|----------|
| `production_dashboard.py` | Full-featured web dashboard | **Primary tool** - Real-time monitoring, treemap visualization, tag management |
| `redis_cache_visualizer.py` | Interactive TUI (Text User Interface) | Terminal-based exploration |
| `redis_cache_visualizer_fast.py` | Fast CLI scanner | Quick overviews and scripts |
| `redis_ops_check.py` | Health check with exit codes | Monitoring integration (Nagios, etc.) |
| `tag_hierarchy.py` | Tag analysis and hierarchy | Understanding cache tag structure |

## 🌐 Production Dashboard

The web dashboard provides comprehensive Redis cache monitoring at `http://localhost:8765`.

### Features

#### 🏥 Health & Telemetry
Real-time monitoring of critical Redis metrics:
- **Hit/Miss Ratio**: Cache efficiency tracking
- **Eviction Monitoring**: Keys evicted per second
- **Memory Fragmentation**: `mem_fragmentation_ratio` tracking
- **Connection Spikes**: Connected client count
- **Historical Charts**: Trend visualization with Chart.js

#### 🗺️ ECharts Treemap
Interactive cache distribution visualization:
- **Heatmap colors**: Blue → Purple → Red based on memory size
- **Click to filter**: Click any block to filter keys by prefix
- **Zoom/pan**: Explore large datasets
- **Tooltips**: Size and key count on hover

#### 🔑 Keys Browser
Full-featured key browser with:
- Search by key name pattern
- Filter by type (string, hash, list, set, zset)
- Filter by cache tag
- Sort by key, type, size, TTL
- Tag badges on each key
- Direct UNLINK action

#### 🔥 Large Key Detection
Identifies keys that block the Redis event loop:
- Configurable threshold (default: >1MB)
- Warning indicators for performance-killing keys
- Quick UNLINK for remediation

#### ⏰ No TTL Tracker
Finds keys without expiration:
- Identifies potential memory leaks
- Keys that persist until manually deleted
- Common issue: GraphQL schema cache

#### 🏷️ Tag Manager
Comprehensive Magento cache tag management:
- Browse all active tags
- Orphaned tag detection
- Tag-based UNLINK (async batch delete)
- Key count and memory per tag

### Production-Safe Operations

| Operation | Implementation | Production Safe? |
|-----------|----------------|------------------|
| Key Enumeration | `SCAN` with COUNT=1000 | ✅ Non-blocking |
| Key Listing | `KEYS *` | ❌ Never use - blocks Redis |
| Size Calculation | `MEMORY USAGE` | ✅ O(1) to O(N) |
| TTL Tracking | `PTTL` (milliseconds) | ✅ Precise |
| Bulk Delete | `UNLINK` (async) | ✅ Non-blocking |
| Bulk Delete | `DEL` | ❌ Blocks Redis |

### Dashboard Tabs

| Tab | Description |
|-----|-------------|
| **🏥 Health** | Hit rate charts, eviction monitoring, fragmentation alerts |
| **🗺️ Treemap** | Visual cache distribution with ECharts |
| **🔑 Keys** | Filterable, sortable key browser |
| **🔥 Large Keys** | Keys >1MB that could block Redis |
| **⏰ No TTL** | Keys without expiration |
| **🏷️ Tags** | Tag browser with UNLINK capability |

## 🏷️ Understanding Magento Cache Tags

Magento uses a sophisticated tagging system for selective cache invalidation.

### Tag Storage Structure

```
zc:tags              # Set of all tag names
zc:ti:<tag>          # Set of keys associated with tag
zc:k:<key>           # Cache value with metadata
```

### Cache Value Format

```json
{
  "t": "eec_MAGE,eec_CONFIG,eec_DB_PDO_MYSQL_DDL",
  "i": "0",
  "m": "1740826853.4705",
  "d": "<base64_encoded_data>"
}
```

### Common Tag Patterns

| Tag Pattern | Purpose |
|-------------|---------|
| `eec_MAGE` | Applied to ALL cache entries (570 keys) |
| `eec_REFLECTION` | Class introspection cache (338 keys) |
| `eec_CAT_P_*` | Catalog product cache (87 products) |
| `eec_CONFIG` | Configuration cache |
| `eec_BLOCK_HTML` | Block HTML cache |
| `eec_LAYOUT_*` | Layout cache |
| `eec_DB_PDO_MYSQL_DDL` | Database DDL definitions |

### Tag-Based Invalidation

To flush all keys with a specific tag:

1. Go to "🏷️ Tags" tab
2. Click desired tag
3. Click "UNLINK Tag" button
4. Confirm deletion

This removes:
- All keys from `zc:ti:<tag>` set
- All keys with matching tag in metadata
- The tag index itself

## 📊 Interpreting Metrics

### Hit Rate

| Value | Status | Action |
|-------|--------|--------|
| >80% | ✅ Excellent | No action needed |
| 50-70% | ⚠️ Warning | Check for broken block cache |
| <50% | 🔴 Critical | Investigate cache churn |

**Low hit rate causes:**
- Broken block cache
- URLs varying by query parameters
- Session-specific cache keys
- Unique cache keys per request

### Memory Fragmentation Ratio

| Value | Status | Action |
|-------|--------|--------|
| <1.2 | ✅ Excellent | No action needed |
| 1.2-1.5 | ✅ Normal | Monitor |
| 1.5-2.0 | ⚠️ Warning | Run `MEMORY PURGE` |
| >2.0 | 🔴 Critical | Restart Redis |

### Evicted Keys

| Value | Status | Action |
|-------|--------|--------|
| 0 | ✅ Optimal | Cache fits in memory |
| >0 | ⚠️ Warning | Increase `maxmemory` or reduce cache |

**Eviction causes:**
- `maxmemory` too low
- Over-caching unique data
- Memory leak in application

### No-TTL Keys

Keys without TTL persist until manually deleted or evicted:

- Magento should rarely store permanent keys
- Common culprits: GraphQL schema, layout blocks
- Monitor to prevent memory leaks
- Use TTL on all cache writes

## 🖥️ CLI Tools

### Fast Scanner

```bash
./redis_cache_visualizer_fast.py
```

Quick overview in <1 second:
```
╔══════════════════════════════════════════════════════════════════╗
║           REDIS CACHE VISUALIZER - FAST MODE                     ║
╠══════════════════════════════════════════════════════════════════╣
║  Redis Version: 7.2.6          Uptime: 11 days                   ║
║  Memory: 17.52 MB / 0 B          Fragmentation: 0.10             ║
║  Total Keys: 640                 Hit Rate: 88.9%                 ║
╠══════════════════════════════════════════════════════════════════╣
║  Top Memory Consumers:                                           ║
║  1. zc:k:eec_ADMINHTML__BACKEND_SYSTEM_CONFIGURATION_STRUCTURE   ║
╚══════════════════════════════════════════════════════════════════╝
```

### Health Check

```bash
./redis_ops_check.py
```

Exit codes for monitoring integration:
- `0`: Healthy
- `1`: Warning
- `2`: Critical

```bash
# Nagios/Icinga integration
./redis_ops_check.py || echo "Redis check failed"
```

### Tag Hierarchy

```bash
python3 tag_hierarchy.py
```

Shows complete tag tree structure:
```
Root: zc:tags
├── System Tags
│   └── eec_MAGE (570 keys)
├── Catalog Tags
│   ├── eec_CAT_P (87 keys)
│   └── eec_CAT_C (categories)
├── Configuration Tags
│   └── eec_CONFIG (43 keys)
...
```

### Interactive TUI

```bash
./redis_cache_visualizer.py
```

Rich terminal interface with:
- Real-time key browser
- Value inspection
- Tag filtering
- Dark mode optimized

## 🔧 Configuration

### Environment Variables

```bash
export REDIS_HOST=127.0.0.1
export REDIS_PORT=6379
export REDIS_DB=0
```

### Custom Port

```bash
# Edit production_dashboard.py
server = ThreadedHTTPServer(('0.0.0.0', 8080), DashboardHandler)
```

## 🔒 Security Considerations

- Dashboard binds to `0.0.0.0:8765` (all interfaces)
- No authentication by default
- **Use firewall/iptables to restrict access:**
  ```bash
  iptables -A INPUT -p tcp --dport 8765 -s 10.0.0.0/8 -j ACCEPT
  iptables -A INPUT -p tcp --dport 8765 -j DROP
  ```
- All delete operations require confirmation
- Use `UNLINK` (async) never `DEL` (blocking)

## 🐛 Troubleshooting

### Dashboard won't start

```bash
# Check if port is in use
lsof -ti:8765 | xargs kill -9

# Restart
./production_dashboard.py
```

### No data displayed

```bash
# Verify Redis connection
redis-cli ping

# Check Magento cache prefix
redis-cli keys 'zc:k:eec_*' | head -5
```

### High memory usage

```bash
# Check for No-TTL keys
curl -s http://localhost:8765/api/data | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'No-TTL keys: {d[\"no_ttl_count\"]}')"

# Find large keys
curl -s http://localhost:8765/api/data | python3 -c "
import json,sys
d=json.load(sys.stdin)
large=[k for k in d['keys'] if k['size']>1024*1024]
for k in large[:5]:
    print(f\"{k['key']}: {k['size']/1024/1024:.1f} MB\")"
```

## 📈 Performance

- **Scan Speed**: ~1000 keys per second
- **Dashboard Update**: Every 10 seconds
- **Memory Usage**: Streams data, minimal caching
- **Browser**: Handles 10,000+ keys smoothly
- **Treemap**: Top 100 prefixes for performance

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📝 License

MIT License - See [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Apache ECharts](https://echarts.apache.org/) for the treemap visualization
- [Chart.js](https://www.chartjs.org/) for health metric charts
- Magento Community for cache architecture documentation

## 📞 Support

- GitHub Issues: [Report bugs or request features](https://github.com/yourusername/redis-cache-visualizer/issues)
- Documentation: This README and inline code comments
