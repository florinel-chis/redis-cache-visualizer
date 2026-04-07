#!/usr/bin/env python3


import asyncio
import json
#!/usr/bin/env python3
"""
Redis Cache Visualizer - Production Dashboard
Production-safe scanning, treemap visualization, tag management
"""

import asyncio
import json
import os
import time
import gzip
from collections import defaultdict
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse, unquote

import redis.asyncio as redis_async

SCAN_COUNT = 1000
LARGE_KEY_THRESHOLD = 1024 * 1024
MAX_SCAN_ITERATIONS = 10000

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redis Cache Visualizer - Production Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-tertiary: #252f47;
            --border: #334155;
            --text-primary: #e2e8f0;
            --text-secondary: #94a3b8;
            --accent: #3b82f6;
            --accent-light: #60a5fa;
            --success: #4ade80;
            --warning: #fbbf24;
            --danger: #f87171;
            --info: #22d3ee;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg-primary); color: var(--text-primary); line-height: 1.6; }
        .header { background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%); padding: 1rem 2rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 100; }
        .header h1 { font-size: 1.25rem; color: var(--accent-light); display: flex; align-items: center; gap: 0.5rem; }
        .status-indicator { width: 10px; height: 10px; border-radius: 50%; background: var(--success); animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .header-stats { display: flex; gap: 2rem; font-size: 0.875rem; }
        .header-stat { text-align: center; }
        .header-stat-value { font-weight: 700; color: var(--accent-light); }
        .header-stat-label { color: var(--text-secondary); font-size: 0.75rem; }
        .refresh-btn { background: var(--accent); border: none; border-radius: 6px; padding: 0.5rem 1rem; color: white; cursor: pointer; display: flex; align-items: center; gap: 0.5rem; }
        .refresh-btn:hover { opacity: 0.9; }
        .refresh-btn.spinning { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .nav { background: var(--bg-secondary); border-bottom: 1px solid var(--border); display: flex; overflow-x: auto; padding: 0 1rem; }
        .nav-item { padding: 1rem 1.5rem; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; white-space: nowrap; font-size: 0.875rem; }
        .nav-item:hover { color: var(--accent-light); }
        .nav-item.active { color: var(--accent-light); border-bottom-color: var(--accent); }
        .container { max-width: 1600px; margin: 0 auto; padding: 1.5rem; }
        .content-section { display: none; }
        .content-section.active { display: block; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
        .stat-card { background: var(--bg-secondary); border-radius: 12px; padding: 1.25rem; border: 1px solid var(--border); }
        .stat-card h3 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-secondary); margin-bottom: 0.75rem; }
        .stat-value { font-size: 1.5rem; font-weight: 700; color: var(--accent-light); }
        .stat-value.success { color: var(--success); }
        .stat-value.warning { color: var(--warning); }
        .stat-value.danger { color: var(--danger); }
        .stat-value.info { color: var(--info); }
        .stat-subtitle { font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.25rem; }
        .panel { background: var(--bg-secondary); border-radius: 12px; border: 1px solid var(--border); overflow: hidden; margin-bottom: 1.5rem; }
        .panel-header { padding: 1rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        .panel-header h3 { font-size: 0.875rem; font-weight: 600; }
        .panel-body { padding: 1rem; max-height: 700px; overflow-y: auto; }
        .panel-body.no-padding { padding: 0; }
        table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
        th { text-align: left; padding: 0.75rem; color: var(--text-secondary); font-weight: 500; border-bottom: 2px solid var(--border); cursor: pointer; position: sticky; top: 0; background: var(--bg-secondary); z-index: 5; }
        th:hover { color: var(--text-primary); }
        td { padding: 0.75rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
        tr:hover { background: var(--bg-tertiary); }
        .key-cell { font-family: 'SF Mono', monospace; font-size: 0.75rem; max-width: 400px; overflow: hidden; text-overflow: ellipsis; }
        .badge { display: inline-block; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
        .badge-hash { background: #7c3aed; color: white; }
        .badge-string { background: #059669; color: white; }
        .badge-set { background: #dc2626; color: white; }
        .badge-list { background: #ea580c; color: white; }
        .badge-zset { background: #0891b2; color: white; }
        .size-critical { color: var(--danger); font-weight: 700; }
        .size-warning { color: var(--warning); font-weight: 600; }
        .size-normal { color: var(--success); }
        .tag-cloud { display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .tag-item { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.375rem 0.75rem; background: var(--bg-tertiary); border-radius: 6px; font-size: 0.75rem; cursor: pointer; transition: all 0.2s; border: 1px solid transparent; }
        .tag-item:hover { background: rgba(59, 130, 246, 0.2); border-color: var(--accent); }
        .tag-item.active { background: rgba(59, 130, 246, 0.3); border-color: var(--accent); }
        .tag-name { font-family: 'SF Mono', monospace; color: var(--accent-light); }
        .tag-count { background: var(--bg-primary); padding: 0.125rem 0.375rem; border-radius: 4px; font-size: 0.625rem; }
        .filters { background: var(--bg-secondary); border-radius: 12px; padding: 1rem; border: 1px solid var(--border); margin-bottom: 1.5rem; display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; }
        .filter-group { display: flex; align-items: center; gap: 0.5rem; }
        .filter-group label { font-size: 0.875rem; color: var(--text-secondary); }
        input, select { background: var(--bg-primary); border: 1px solid var(--border); border-radius: 6px; padding: 0.5rem 0.75rem; color: var(--text-primary); font-size: 0.875rem; }
        input:focus, select:focus { outline: none; border-color: var(--accent); }
        button { background: var(--accent); border: none; border-radius: 6px; padding: 0.5rem 1rem; color: white; font-size: 0.875rem; cursor: pointer; transition: opacity 0.2s; }
        button:hover { opacity: 0.9; }
        button.secondary { background: var(--bg-tertiary); border: 1px solid var(--border); }
        button.danger { background: var(--danger); }
        button.small { padding: 0.25rem 0.5rem; font-size: 0.75rem; }
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.8); z-index: 1000; align-items: center; justify-content: center; padding: 2rem; }
        .modal-overlay.active { display: flex; }
        .modal { background: var(--bg-secondary); border-radius: 12px; border: 1px solid var(--border); width: 100%; max-width: 900px; max-height: 85vh; display: flex; flex-direction: column; }
        .modal-header { padding: 1rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        .modal-body { padding: 1rem; overflow: auto; flex: 1; }
        .modal-footer { padding: 1rem; border-top: 1px solid var(--border); display: flex; gap: 0.5rem; justify-content: flex-end; }
        .value-content { font-family: 'SF Mono', monospace; font-size: 0.75rem; background: var(--bg-primary); padding: 1rem; border-radius: 8px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto; }
        .two-column { display: grid; grid-template-columns: 350px 1fr; gap: 1.5rem; }
        @media (max-width: 1200px) { .two-column { grid-template-columns: 1fr; } }
        .chart-container { height: 300px; position: relative; }
        #treemap-container { width: 100%; height: 500px; }
        .alert { padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem; }
        .alert-critical { background: rgba(248, 113, 113, 0.1); border: 1px solid var(--danger); color: var(--danger); }
        .alert-warning { background: rgba(251, 191, 36, 0.1); border: 1px solid var(--warning); color: var(--warning); }
        .alert-success { background: rgba(74, 222, 128, 0.1); border: 1px solid var(--success); color: var(--success); }
    </style>
</head>
<body>
    <div class="header">
        <h1><span class="status-indicator"></span>Redis Cache Visualizer <span style="font-size: 0.75rem; color: var(--text-secondary); font-weight: 400;">Production Dashboard</span></h1>
        <div class="header-stats">
            <div class="header-stat"><div class="header-stat-value" id="header-keys">-</div><div class="header-stat-label">Keys</div></div>
            <div class="header-stat"><div class="header-stat-value" id="header-memory">-</div><div class="header-stat-label">Memory</div></div>
            <div class="header-stat"><div class="header-stat-value" id="header-hitrate">-</div><div class="header-stat-label">Hit Rate</div></div>
        </div>
        <div style="display: flex; gap: 1rem; align-items: center;">
            <span id="last-update" style="color: var(--text-secondary); font-size: 0.875rem;">Loading...</span>
            <button class="refresh-btn" onclick="refreshData()">↻ Refresh</button>
        </div>
    </div>
    
    <div class="nav">
        <div class="nav-item active" onclick="showSection('health')">🏥 Health</div>
        <div class="nav-item" onclick="showSection('treemap')">🗺️ Treemap</div>
        <div class="nav-item" onclick="showSection('keys')">🔑 Keys</div>
        <div class="nav-item" onclick="showSection('large')">🔥 Large Keys</div>
        <div class="nav-item" onclick="showSection('notll')">⏰ No TTL</div>
        <div class="nav-item" onclick="showSection('tags')">🏷️ Tags</div>
    </div>
    
    <div class="container">
        <!-- Health View -->
        <div id="health" class="content-section active">
            <div id="alerts-container"></div>
            <div class="stats-grid" id="health-stats"></div>
            <div class="panel">
                <div class="panel-header"><h3>📊 Hit/Miss Ratio</h3></div>
                <div class="panel-body"><div class="chart-container"><canvas id="hitmiss-chart"></canvas></div></div>
            </div>
        </div>
        
        <!-- Treemap View -->
        <div id="treemap" class="content-section">
            <div class="filters">
                <div class="filter-group"><label>Min Size:</label><select id="treemap-min-size"><option value="0">All</option><option value="1024">1 KB</option><option value="10240">10 KB</option><option value="102400">100 KB</option><option value="1048576">1 MB</option></select></div>
                <button onclick="renderTreemap()">Regenerate</button>
            </div>
            <div class="panel">
                <div class="panel-header"><h3>🗺️ Cache Distribution (ECharts Treemap)</h3></div>
                <div class="panel-body no-padding"><div id="treemap-container"></div></div>
            </div>
        </div>
        
        <!-- Keys View -->
        <div id="keys" class="content-section">
            <div class="filters">
                <div class="filter-group"><label>Search:</label><input type="text" id="search-input" placeholder="Filter keys..." style="width: 200px;"></div>
                <div class="filter-group"><label>Type:</label><select id="type-filter"><option value="">All</option><option value="string">String</option><option value="hash">Hash</option><option value="list">List</option><option value="set">Set</option><option value="zset">Sorted Set</option></select></div>
                <div class="filter-group"><label>Tag:</label><select id="tag-filter"><option value="">All Tags</option></select></div>
                <button onclick="applyFilters()">Apply</button>
                <button class="secondary" onclick="clearFilters()">Clear</button>
            </div>
            <div class="panel">
                <div class="panel-header"><h3>Cache Keys</h3><span id="keys-count"></span></div>
                <div class="panel-body no-padding">
                    <table>
                        <thead><tr><th onclick="sortBy('key')">Key</th><th onclick="sortBy('type')">Type</th><th onclick="sortBy('size')">Size</th><th onclick="sortBy('ttl')">TTL</th><th>Tags</th><th>Actions</th></tr></thead>
                        <tbody id="keys-table"></tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- Large Keys View -->
        <div id="large" class="content-section">
            <div class="filters">
                <div class="filter-group"><label>Threshold:</label><select id="large-threshold"><option value="1048576">1 MB</option><option value="5242880">5 MB</option><option value="10485760">10 MB</option></select></div>
                <button onclick="updateLargeKeys()">Apply</button>
            </div>
            <div class="panel">
                <div class="panel-header"><h3>🔥 Large Keys</h3></div>
                <div class="panel-body no-padding">
                    <table><thead><tr><th>Rank</th><th>Key</th><th>Type</th><th>Size</th><th>TTL</th><th>Actions</th></tr></thead><tbody id="large-keys-table"></tbody></table>
                </div>
            </div>
        </div>
        
        <!-- No TTL View -->
        <div id="notll" class="content-section">
            <div class="panel">
                <div class="panel-header"><h3>⏰ Keys Without TTL</h3></div>
                <div class="panel-body no-padding">
                    <div style="padding: 1rem; background: rgba(251, 191, 36, 0.1);"><strong id="no-ttl-count">0 keys</strong> without expiration</div>
                    <table><thead><tr><th>Key</th><th>Type</th><th>Size</th><th>Actions</th></tr></thead><tbody id="no-ttl-table"></tbody></table>
                </div>
            </div>
        </div>
        
        <!-- Tags View -->
        <div id="tags" class="content-section">
            <div class="two-column">
                <div>
                    <div class="panel">
                        <div class="panel-header"><h3>All Tags</h3><input type="text" id="tag-search" placeholder="Filter..." style="width: 150px; font-size: 0.75rem;"></div>
                        <div class="panel-body"><div id="tag-cloud" class="tag-cloud"></div></div>
                    </div>
                </div>
                <div>
                    <div id="tag-detail-panel" style="display: none;">
                        <div class="panel" style="margin-bottom: 1rem;">
                            <div class="panel-header"><h3 id="detail-tag-name"></h3><div><button class="small" onclick="showKeysWithTag()">Show Keys</button><button class="small danger" onclick="confirmFlushTag()">UNLINK Tag</button></div></div>
                            <div class="panel-body"><div class="stats-grid" style="margin-bottom: 0;"><div class="stat-card"><h3>Keys</h3><div class="stat-value" id="detail-key-count">-</div></div><div class="stat-card"><h3>Total Size</h3><div class="stat-value" id="detail-total-size">-</div></div></div></div>
                        </div>
                    </div>
                    <div id="tag-select-prompt" style="text-align: center; padding: 3rem; color: var(--text-secondary);">Select a tag</div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Value Modal -->
    <div class="modal-overlay" id="value-modal" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header"><h3>Key Payload</h3><button class="secondary" onclick="closeModal()">×</button></div>
            <div class="modal-body">
                <div style="margin-bottom: 1rem; font-size: 0.875rem;"><strong>Key:</strong> <span id="modal-key"></span><br><strong>Type:</strong> <span id="modal-type"></span><br><strong>Size:</strong> <span id="modal-size"></span><br><strong>TTL:</strong> <span id="modal-ttl"></span></div>
                <div class="value-content" id="modal-value"></div>
            </div>
            <div class="modal-footer"><button onclick="copyValue()">Copy</button><button class="danger" onclick="unlinkKey()">UNLINK</button><button class="secondary" onclick="closeModal()">Close</button></div>
        </div>
    </div>
    
    <!-- Flush Tag Modal -->
    <div class="modal-overlay" id="flush-modal" onclick="closeFlushModal(event)">
        <div class="modal" onclick="event.stopPropagation()" style="max-width: 500px;">
            <div class="modal-header"><h3>Confirm UNLINK</h3><button class="secondary" onclick="closeFlushModal()">×</button></div>
            <div class="modal-body"><p>UNLINK all keys with tag:</p><p style="font-family: monospace; background: var(--bg-tertiary); padding: 0.75rem;" id="flush-tag-name"></p><p>This will delete <strong id="flush-key-count"></strong> keys asynchronously.</p></div>
            <div class="modal-footer"><button class="danger" onclick="executeFlushTag()">UNLINK Tag</button><button class="secondary" onclick="closeFlushModal()">Cancel</button></div>
        </div>
    </div>
    
    <script>
        let allData = {}, sortColumn = 'size', sortDirection = 'desc', selectedTag = null, currentModalKey = null;
        let treemapChart = null, hitMissChart = null;
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024, sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }
        
        function formatTTL(ms) {
            if (ms === null || ms === -1 || ms === -2) return 'Never';
            const s = Math.floor(ms / 1000);
            if (s < 60) return s + 's';
            if (s < 3600) return Math.floor(s / 60) + 'm';
            if (s < 86400) return Math.floor(s / 3600) + 'h';
            return Math.floor(s / 86400) + 'd';
        }
        
        function getSizeClass(bytes) {
            if (bytes > 10 * 1024 * 1024) return 'size-critical';
            if (bytes > 1024 * 1024) return 'size-warning';
            return 'size-normal';
        }
        
        function showSection(id) {
            document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            event.target.classList.add('active');
            if (id === 'treemap') setTimeout(renderTreemap, 100);
        }
        
        async function refreshData() {
            const btn = document.querySelector('.refresh-btn');
            btn.classList.add('spinning');
            try {
                const response = await fetch('/api/data');
                allData = await response.json();
                updateAllSections();
                document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
            } catch (err) {
                console.error('Failed:', err);
            } finally {
                btn.classList.remove('spinning');
            }
        }
        
        function updateAllSections() {
            updateHeader();
            updateHealth();
            updateKeysTable();
            updateLargeKeys();
            updateNoTTL();
            updateTagsSection();
            if (treemapChart) renderTreemap();
        }
        
        function updateHeader() {
            const info = allData.info;
            document.getElementById('header-keys').textContent = info.total_keys.toLocaleString();
            document.getElementById('header-memory').textContent = info.memory_used;
            document.getElementById('header-hitrate').textContent = info.hit_rate.toFixed(1) + '%';
        }
        
        function updateHealth() {
            const info = allData.info, health = allData.healthChecks || [];
            document.getElementById('health-stats').innerHTML = 
                '<div class="stat-card"><h3>Hit Rate</h3><div class="stat-value ' + (info.hit_rate < 50 ? 'danger' : info.hit_rate < 70 ? 'warning' : 'success') + '">' + info.hit_rate.toFixed(1) + '%</div></div>' +
                '<div class="stat-card"><h3>Evictions</h3><div class="stat-value ' + (info.evicted_keys > 0 ? 'danger' : 'success') + '">' + info.evicted_keys + '</div></div>' +
                '<div class="stat-card"><h3>Fragmentation</h3><div class="stat-value ' + (info.fragmentation_ratio > 1.5 ? 'warning' : 'success') + '">' + (info.fragmentation_ratio ? info.fragmentation_ratio.toFixed(2) : '-') + '</div></div>' +
                '<div class="stat-card"><h3>Connections</h3><div class="stat-value ' + (info.clients > 500 ? 'warning' : 'info') + '">' + info.clients + '</div></div>';
            
            const alerts = document.getElementById('alerts-container');
            if (allData.alerts && allData.alerts.length > 0) {
                alerts.innerHTML = allData.alerts.map(function(a) { return '<div class="alert alert-' + a.level.toLowerCase() + '">' + a.icon + ' ' + a.message + '</div>'; }).join('');
            } else {
                alerts.innerHTML = '<div class="alert alert-success">All systems operational</div>';
            }
            
            updateCharts();
        }
        
        function updateCharts() {
            const history = allData.history || { timestamps: [], hit_rates: [] };
            const ctx = document.getElementById('hitmiss-chart');
            if (ctx) {
                if (hitMissChart) hitMissChart.destroy();
                hitMissChart = new Chart(ctx, {
                    type: 'line',
                    data: { labels: history.timestamps.slice(-20), datasets: [{ label: 'Hit Rate %', data: history.hit_rates.slice(-20), borderColor: '#4ade80', backgroundColor: 'rgba(74, 222, 128, 0.1)', tension: 0.4, fill: true }] },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, max: 100, grid: { color: '#334155' } }, x: { grid: { color: '#334155' } } } }
                });
            }
        }
        
        // ECharts Treemap
        function initTreemap() {
            if (treemapChart) treemapChart.dispose();
            treemapChart = echarts.init(document.getElementById('treemap-container'));
        }
        
        function renderTreemap() {
            if (!treemapChart) initTreemap();
            const minSize = parseInt(document.getElementById('treemap-min-size')?.value) || 0;
            let prefixes = (allData.prefixes || []).filter(function(p) { return p.size >= minSize; });
            prefixes.sort(function(a, b) { return b.size - a.size; });
            prefixes = prefixes.slice(0, 100);
            
            if (prefixes.length === 0) {
                document.getElementById('treemap-container').innerHTML = '<div style="text-align: center; padding: 3rem;">No data</div>';
                return;
            }
            
            const maxSize = Math.max.apply(null, prefixes.map(function(p) { return p.size; })) || 1;
            
            const data = prefixes.map(function(p) {
                const ratio = p.size / maxSize;
                let r, g, b;
                if (ratio < 0.5) {
                    const t = ratio * 2;
                    r = Math.floor(59 + (147 - 59) * t);
                    g = Math.floor(130 + (51 - 130) * t);
                    b = Math.floor(246 + (250 - 246) * t);
                } else {
                    const t = (ratio - 0.5) * 2;
                    r = Math.floor(147 + (248 - 147) * t);
                    g = Math.floor(51 + (113 - 51) * t);
                    b = Math.floor(250 + (113 - 250) * t);
                }
                return { name: p.prefix, value: p.size, keyCount: p.count, itemStyle: { color: 'rgb(' + r + ',' + g + ',' + b + ')' } };
            });
            
            treemapChart.setOption({
                backgroundColor: 'transparent',
                tooltip: {
                    backgroundColor: '#1e293b', borderColor: '#334155', textStyle: { color: '#e2e8f0' },
                    formatter: function(p) { return '<b>' + p.name + '</b><br/>Size: ' + formatBytes(p.value) + '<br/>Keys: ' + p.data.keyCount; }
                },
                series: [{
                    type: 'treemap', width: '100%', height: '100%', roam: false, nodeClick: false, breadcrumb: { show: false },
                    label: { show: true, formatter: function(p) { return p.name.length > 25 ? p.name.substring(0, 22) + '...' : p.name; }, fontSize: 10 },
                    itemStyle: { borderColor: '#0f172a', borderWidth: 2, gapWidth: 2 },
                    data: data
                }]
            });
            
            treemapChart.off('click');
            treemapChart.on('click', function(p) { filterByPrefix(p.name); });
        }
        
        function filterByPrefix(prefix) {
            showSection('keys');
            document.querySelectorAll('.nav-item')[2].classList.add('active');
            document.getElementById('search-input').value = prefix;
            applyFilters();
        }
        
        function updateKeysTable() {
            let keys = [...(allData.keys || [])];
            const search = document.getElementById('search-input')?.value.toLowerCase() || '';
            if (search) keys = keys.filter(function(k) { return k.key.toLowerCase().indexOf(search) !== -1; });
            const typeFilter = document.getElementById('type-filter')?.value || '';
            if (typeFilter) keys = keys.filter(function(k) { return k.type === typeFilter; });
            const tagFilter = document.getElementById('tag-filter')?.value || '';
            if (tagFilter) keys = keys.filter(function(k) { return k.tags && k.tags.indexOf(tagFilter) !== -1; });
            
            keys.sort(function(a, b) {
                let va = a[sortColumn], vb = b[sortColumn];
                if (va === null) va = -1; if (vb === null) vb = -1;
                return sortDirection === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
            });
            
            document.getElementById('keys-count').textContent = 'Showing ' + Math.min(keys.length, 100) + ' of ' + keys.length;
            document.getElementById('keys-table').innerHTML = keys.slice(0, 100).map(function(k) {
                var tagsHtml = '';
                if (k.tags && k.tags.length > 0) {
                    for (var i = 0; i < Math.min(k.tags.length, 3); i++) {
                        tagsHtml += '<span class="tag-item" style="padding: 0.125rem 0.375rem; font-size: 0.625rem;" onclick="filterByTag(' + "'" + k.tags[i] + "'" + ')">' + k.tags[i] + '</span>';
                    }
                    if (k.tags.length > 3) tagsHtml += '<span class="tag-item" style="padding: 0.125rem 0.375rem; font-size: 0.625rem;">+' + (k.tags.length - 3) + '</span>';
                }
                return '<tr><td class="key-cell" title="' + k.key + '">' + k.key + '</td><td><span class="badge badge-' + k.type + '">' + k.type + '</span></td><td class="' + getSizeClass(k.size) + '">' + formatBytes(k.size) + '</td><td>' + formatTTL(k.ttl) + '</td><td><div class="tag-cloud" style="gap: 0.25rem;">' + tagsHtml + '</div></td><td><button class="secondary small" onclick="viewValue(' + "'" + encodeURIComponent(k.key) + "'" + ')">View</button><button class="danger small" onclick="unlinkSingleKey(' + "'" + encodeURIComponent(k.key) + "'" + ')">UNLINK</button></td></tr>';
            }).join('') || '<tr><td colspan="6" style="text-align: center; padding: 2rem;">No keys</td></tr>';
        }
        
        function sortBy(col) {
            if (sortColumn === col) sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
            else { sortColumn = col; sortDirection = 'desc'; }
            updateKeysTable();
        }
        
        function applyFilters() { updateKeysTable(); }
        function clearFilters() { document.getElementById('search-input').value = ''; document.getElementById('type-filter').value = ''; document.getElementById('tag-filter').value = ''; updateKeysTable(); }
        function filterByTag(tag) { document.getElementById('tag-filter').value = tag; applyFilters(); }
        
        function updateLargeKeys() {
            const threshold = parseInt(document.getElementById('large-threshold')?.value) || 1048576;
            const largeKeys = [...(allData.keys || [])].filter(function(k) { return k.size >= threshold; }).sort(function(a, b) { return b.size - a.size; });
            document.getElementById('large-keys-table').innerHTML = largeKeys.map(function(k, i) {
                return '<tr><td>#' + (i + 1) + '</td><td class="key-cell" title="' + k.key + '">' + k.key + '</td><td><span class="badge badge-' + k.type + '">' + k.type + '</span></td><td class="size-critical">' + formatBytes(k.size) + '</td><td>' + formatTTL(k.ttl) + '</td><td><button class="secondary small" onclick="viewValue(' + "'" + encodeURIComponent(k.key) + "'" + ')">View</button><button class="danger small" onclick="unlinkSingleKey(' + "'" + encodeURIComponent(k.key) + "'" + ')">UNLINK</button></td></tr>';
            }).join('') || '<tr><td colspan="6" style="text-align: center; padding: 2rem;">No large keys</td></tr>';
        }
        
        function updateNoTTL() {
            const noTtlKeys = [...(allData.keys || [])].filter(function(k) { return k.ttl === -1 || k.ttl === null; });
            document.getElementById('no-ttl-count').textContent = noTtlKeys.length + ' keys';
            document.getElementById('no-ttl-table').innerHTML = noTtlKeys.map(function(k) {
                return '<tr><td class="key-cell" title="' + k.key + '">' + k.key + '</td><td><span class="badge badge-' + k.type + '">' + k.type + '</span></td><td class="' + getSizeClass(k.size) + '">' + formatBytes(k.size) + '</td><td><button class="secondary small" onclick="viewValue(' + "'" + encodeURIComponent(k.key) + "'" + ')">View</button><button class="danger small" onclick="unlinkSingleKey(' + "'" + encodeURIComponent(k.key) + "'" + ')">UNLINK</button></td></tr>';
            }).join('') || '<tr><td colspan="4" style="text-align: center; padding: 2rem;">No keys without TTL</td></tr>';
        }
        
        function updateTagsSection() {
            const tags = allData.tagStats || [];
            const maxCount = Math.max.apply(null, tags.map(function(t) { return t.count; }).concat([1]));
            document.getElementById('tag-cloud').innerHTML = tags.map(function(t) {
                const opacity = 0.5 + (t.count / maxCount) * 0.5;
                return '<div class="tag-item ' + (selectedTag === t.tag ? 'active' : '') + '" style="opacity: ' + opacity + '" onclick="selectTag(' + "'" + t.tag + "'" + ')"><span class="tag-name">' + t.tag + '</span><span class="tag-count">' + t.count + '</span></div>';
            }).join('');
            
            const tagFilter = document.getElementById('tag-filter');
            const currentValue = tagFilter.value;
            tagFilter.innerHTML = '<option value="">All Tags</option>' + tags.map(function(t) { return '<option value="' + t.tag + '">' + t.tag + ' (' + t.count + ')</option>'; }).join('');
            tagFilter.value = currentValue;
        }
        
        function selectTag(tag) {
            selectedTag = tag;
            document.getElementById('tag-select-prompt').style.display = 'none';
            document.getElementById('tag-detail-panel').style.display = 'block';
            const tagInfo = allData.tagStats.find(function(t) { return t.tag === tag; });
            if (tagInfo) {
                document.getElementById('detail-tag-name').textContent = tag;
                document.getElementById('detail-key-count').textContent = tagInfo.count;
                document.getElementById('detail-total-size').textContent = formatBytes(tagInfo.totalSize);
            }
            updateTagsSection();
        }
        
        function showKeysWithTag() { if (!selectedTag) return; showSection('keys'); document.querySelectorAll('.nav-item')[2].classList.add('active'); document.getElementById('tag-filter').value = selectedTag; applyFilters(); }
        function confirmFlushTag() { if (!selectedTag) return; const tagInfo = allData.tagStats.find(function(t) { return t.tag === selectedTag; }); document.getElementById('flush-tag-name').textContent = selectedTag; document.getElementById('flush-key-count').textContent = tagInfo.count; document.getElementById('flush-modal').classList.add('active'); }
        function closeFlushModal(e) { if (!e || e.target.id === 'flush-modal') document.getElementById('flush-modal').classList.remove('active'); }
        
        async function executeFlushTag() {
            if (!selectedTag) return;
            try {
                const response = await fetch('/api/unlink-tag?tag=' + encodeURIComponent(selectedTag), { method: 'POST' });
                const result = await response.json();
                alert('UNLINKed ' + result.deleted + ' keys');
                closeFlushModal();
                refreshData();
            } catch (err) { alert('Failed: ' + err.message); }
        }
        
        async function viewValue(keyEncoded) {
            const key = decodeURIComponent(keyEncoded);
            currentModalKey = key;
            try {
                const response = await fetch('/api/value?key=' + keyEncoded);
                const data = await response.json();
                document.getElementById('modal-key').textContent = key;
                document.getElementById('modal-type').textContent = data.type;
                document.getElementById('modal-size').textContent = formatBytes(data.size || 0);
                document.getElementById('modal-ttl').textContent = formatTTL(data.ttl);
                let valueStr = typeof data.value === 'object' ? JSON.stringify(data.value, null, 2) : data.value;
                if (valueStr && valueStr.length > 10000) valueStr = valueStr.substring(0, 10000) + String.fromCharCode(10, 10) + '... [truncated]';
                document.getElementById('modal-value').textContent = valueStr || '(empty)';
                document.getElementById('value-modal').classList.add('active');
            } catch (err) { alert('Failed: ' + err.message); }
        }
        
        async function unlinkKey() {
            if (!currentModalKey) return;
            if (!confirm('UNLINK key: ' + currentModalKey + '?')) return;
            try {
                await fetch('/api/unlink?key=' + encodeURIComponent(currentModalKey), { method: 'POST' });
                closeModal();
                refreshData();
            } catch (err) { alert('Failed: ' + err.message); }
        }
        
        async function unlinkSingleKey(keyEncoded) {
            const key = decodeURIComponent(keyEncoded);
            if (!confirm('UNLINK key: ' + key + '?')) return;
            try {
                await fetch('/api/unlink?key=' + keyEncoded, { method: 'POST' });
                refreshData();
            } catch (err) { alert('Failed: ' + err.message); }
        }
        
        function closeModal(e) { if (!e || e.target.id === 'value-modal') { document.getElementById('value-modal').classList.remove('active'); currentModalKey = null; } }
        function copyValue() { navigator.clipboard.writeText(document.getElementById('modal-value').textContent).then(function() { alert('Copied!'); }); }
        
        window.addEventListener('resize', function() { if (treemapChart) treemapChart.resize(); });
        
        refreshData();
        setInterval(refreshData, 10000);
    </script>
</body>
</html>
'''


class ProductionDataProvider:
    def __init__(self, host='127.0.0.1', port=6379, db=0):
        self.host = host
        self.port = port
        self.db = db
        self.history = {'timestamps': [], 'hit_rates': [], 'evictions': [], 'connections': []}
        self.max_history = 100
    
    async def _get_redis_async(self):
        return await redis_async.from_url(f'redis://{self.host}:{self.port}/{self.db}', decode_responses=True)
    
    async def scan_and_profile(self):
        r = await self._get_redis_async()
        stats = {'keys': [], 'prefixes': defaultdict(lambda: {'size': 0, 'count': 0}), 'no_ttl_count': 0, 'large_keys': [], 'tag_index': defaultdict(list)}
        cursor = 0
        iterations = 0
        
        try:
            while iterations < MAX_SCAN_ITERATIONS:
                cursor, keys = await r.scan(cursor=cursor, count=SCAN_COUNT)
                if not keys:
                    if cursor == 0:
                        break
                    iterations += 1
                    continue
                
                pipe = r.pipeline()
                for key in keys:
                    pipe.type(key)
                    pipe.memory_usage(key)
                    pipe.pttl(key)
                type_results = await pipe.execute()
                
                hash_keys = [keys[i] for i in range(len(keys)) if type_results[i * 3] == 'hash']
                tag_results = {}
                if hash_keys:
                    tag_pipe = r.pipeline()
                    for key in hash_keys:
                        tag_pipe.hget(key, 't')
                    tag_values = await tag_pipe.execute()
                    tag_results = dict(zip(hash_keys, tag_values))
                
                for i, key in enumerate(keys):
                    base = i * 3
                    key_type = type_results[base]
                    size = type_results[base + 1] or 0
                    ttl_ms = type_results[base + 2]
                    tags_str = tag_results.get(key, '') if key_type == 'hash' else ''
                    tags = tags_str.split(',') if tags_str else []
                    
                    if ttl_ms == -1:
                        stats['no_ttl_count'] += 1
                    if size > LARGE_KEY_THRESHOLD:
                        stats['large_keys'].append({'key': key, 'size': size, 'type': key_type})
                    
                    prefix = self._extract_prefix(key)
                    stats['prefixes'][prefix]['size'] += size
                    stats['prefixes'][prefix]['count'] += 1
                    
                    for tag in tags:
                        stats['tag_index'][tag].append(key)
                    
                    stats['keys'].append({'key': key, 'type': key_type, 'size': size, 'ttl': ttl_ms, 'tags': tags})
                
                iterations += 1
                if cursor == 0:
                    break
        finally:
            await r.aclose()
        
        prefix_list = [{'prefix': p, 'size': d['size'], 'count': d['count']} for p, d in stats['prefixes'].items()]
        prefix_list.sort(key=lambda x: x['size'], reverse=True)
        
        tag_stats = [{'tag': t, 'count': len(keys), 'totalSize': sum(k['size'] for k in stats['keys'] if k['key'] in keys)} for t, keys in stats['tag_index'].items()]
        tag_stats.sort(key=lambda x: x['count'], reverse=True)
        
        return {'keys': stats['keys'], 'prefixes': prefix_list, 'no_ttl_count': stats['no_ttl_count'], 'large_keys': sorted(stats['large_keys'], key=lambda x: x['size'], reverse=True), 'tagStats': tag_stats}
    
    def _extract_prefix(self, key):
        if key.startswith('zc:k:'):
            parts = key.split(':')
            if len(parts) >= 3:
                return ':'.join(parts[:3])
        parts = key.split('_')
        if len(parts) >= 2 and len(parts[0]) < 20:
            return parts[0] + '_' + parts[1]
        return key[:30]
    
    async def get_all_data(self):
        r = await self._get_redis_async()
        try:
            info_server = await r.info('server')
            info_clients = await r.info('clients')
            info_memory = await r.info('memory')
            info_stats = await r.info('stats')
            info_keyspace = await r.info('keyspace')
            
            scan_data = await self.scan_and_profile()
            
            mem = info_memory
            stats = info_stats
            maxmemory = mem.get('maxmemory', 0)
            used = mem.get('used_memory', 0)
            memory_pct = (used / maxmemory * 100) if maxmemory > 0 else 0
            hits = stats.get('keyspace_hits', 0)
            misses = stats.get('keyspace_misses', 0)
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0
            
            now = datetime.now().strftime('%H:%M:%S')
            self.history['timestamps'].append(now)
            self.history['hit_rates'].append(hit_rate)
            self.history['evictions'].append(stats.get('evicted_keys', 0))
            self.history['connections'].append(info_clients.get('connected_clients', 0))
            
            if len(self.history['timestamps']) > self.max_history:
                for k in self.history:
                    self.history[k] = self.history[k][-self.max_history:]
            
            health = self._health_checks(mem, stats, hit_rate, info_clients)
            alerts = self._generate_alerts(health)
            
            return {
                'info': {
                    'version': info_server.get('redis_version', 'Unknown'),
                    'uptime': info_server.get('uptime_in_days', 0),
                    'memory_used': mem.get('used_memory_human', '0B'),
                    'memory_pct': memory_pct,
                    'fragmentation_ratio': mem.get('mem_fragmentation_ratio', 0),
                    'clients': info_clients.get('connected_clients', 0),
                    'total_keys': sum(db.get('keys', 0) for db in info_keyspace.values()),
                    'hit_rate': hit_rate,
                    'ops_per_sec': stats.get('instantaneous_ops_per_sec', 0),
                    'evicted_keys': stats.get('evicted_keys', 0),
                    'evicted_per_sec': stats.get('evicted_keys', 0) / max(info_server.get('uptime_in_seconds', 1), 1),
                },
                'history': self.history,
                **scan_data,
                'healthChecks': health,
                'alerts': alerts
            }
        finally:
            await r.aclose()
    
    def _health_checks(self, mem, stats, hit_rate, clients):
        checks = []
        memory_pct = (mem.get('used_memory', 0) / mem.get('maxmemory', 1) * 100) if mem.get('maxmemory', 0) > 0 else 0
        if memory_pct > 95:
            checks.append({'status': 'CRITICAL', 'check': 'Memory', 'detail': f'{memory_pct:.1f}% used', 'icon': '🔴'})
        elif memory_pct > 80:
            checks.append({'status': 'WARNING', 'check': 'Memory', 'detail': f'{memory_pct:.1f}% used', 'icon': '🟡'})
        else:
            checks.append({'status': 'OK', 'check': 'Memory', 'detail': f'{memory_pct:.1f}% used', 'icon': '🟢'})
        
        frag = mem.get('mem_fragmentation_ratio', 0)
        if frag > 2.0:
            checks.append({'status': 'WARNING', 'check': 'Fragmentation', 'detail': f'{frag:.2f}', 'icon': '🟡'})
        else:
            checks.append({'status': 'OK', 'check': 'Fragmentation', 'detail': f'{frag:.2f}', 'icon': '🟢'})
        
        evicted = stats.get('evicted_keys', 0)
        if evicted > 0:
            checks.append({'status': 'CRITICAL', 'check': 'Evictions', 'detail': f'{evicted} keys evicted', 'icon': '🔴'})
        else:
            checks.append({'status': 'OK', 'check': 'Evictions', 'detail': '0 keys evicted', 'icon': '🟢'})
        
        if hit_rate < 50:
            checks.append({'status': 'CRITICAL', 'check': 'Hit Rate', 'detail': f'{hit_rate:.1f}%', 'icon': '🔴'})
        elif hit_rate < 70:
            checks.append({'status': 'WARNING', 'check': 'Hit Rate', 'detail': f'{hit_rate:.1f}%', 'icon': '🟡'})
        else:
            checks.append({'status': 'OK', 'check': 'Hit Rate', 'detail': f'{hit_rate:.1f}%', 'icon': '🟢'})
        
        conn = clients.get('connected_clients', 0)
        if conn > 5000:
            checks.append({'status': 'WARNING', 'check': 'Clients', 'detail': f'{conn} connected', 'icon': '🟡'})
        else:
            checks.append({'status': 'OK', 'check': 'Clients', 'detail': f'{conn} connected', 'icon': '🟢'})
        
        return checks
    
    def _generate_alerts(self, health):
        alerts = []
        for check in health:
            if check['status'] == 'CRITICAL':
                alerts.append({'level': 'CRITICAL', 'icon': '🔴', 'message': f"{check['check']}: {check['detail']}"})
            elif check['status'] == 'WARNING':
                alerts.append({'level': 'WARNING', 'icon': '🟡', 'message': f"{check['check']}: {check['detail']}"})
        return alerts
    
    async def get_value(self, key):
        r = await self._get_redis_async()
        try:
            key_type = await r.type(key)
            ttl = await r.pttl(key)
            size = await r.memory_usage(key) or 0
            tags_str = await r.hget(key, 't')
            tags = tags_str.split(',') if tags_str else []
            
            value = None
            if key_type == 'string':
                raw = await r.get(key)
                value = self._decode_value(raw)
            elif key_type == 'hash':
                raw = await r.hgetall(key)
                if 'd' in raw:
                    value = {'metadata': {k: v for k, v in raw.items() if k != 'd'}, 'data': self._decode_value(raw.get('d', ''))}
                else:
                    value = dict(list(raw.items())[:100])
                    if len(raw) > 100:
                        value['...'] = f'truncated, {len(raw)} fields'
            elif key_type == 'list':
                length = await r.llen(key)
                value = await r.lrange(key, 0, 49)
                if length > 50:
                    value.append(f'... truncated, {length} items')
            elif key_type == 'set':
                members = await r.smembers(key)
                value = list(members)[:50]
                if len(members) > 50:
                    value.append(f'... truncated, {len(members)} members')
            elif key_type == 'zset':
                members = await r.zrange(key, 0, 49, withscores=True)
                value = [{'member': m, 'score': s} for m, s in members]
                length = await r.zcard(key)
                if length > 50:
                    value.append(f'... truncated, {length} members')
            else:
                value = f'(unsupported: {key_type})'
            
            return {'key': key, 'type': key_type, 'size': size, 'ttl': ttl if ttl > 0 else None, 'tags': tags, 'value': value}
        finally:
            await r.aclose()
    
    def _decode_value(self, data):
        if not data:
            return '(empty)'
        
        if isinstance(data, bytes):
            try:
                if data[:2] == b'\x1f\x8b':
                    decompressed = gzip.decompress(data)
                    data = decompressed
            except:
                pass
            try:
                data = data.decode('utf-8', errors='ignore')
            except:
                data = data.hex()
        
        if isinstance(data, str):
            try:
                return json.loads(data)
            except:
                pass
            if data.startswith('a:') or data.startswith('s:') or data.startswith('O:'):
                return f'[PHP Serialized: {len(data)} chars]'
        
        return data
    
    async def unlink_key(self, key):
        r = await self._get_redis_async()
        try:
            result = await r.unlink(key)
            return {'deleted': result, 'key': key}
        finally:
            await r.aclose()
    
    async def unlink_tag(self, tag):
        r = await self._get_redis_async()
        try:
            keys = list(await r.smembers(f'zc:ti:{tag}'))
            cursor = 0
            metadata_keys = []
            for _ in range(50):
                cursor, batch = await r.scan(cursor=cursor, match='eec_*', count=100)
                if batch:
                    pipe = r.pipeline()
                    for k in batch:
                        pipe.hget(k, 't')
                    results = await pipe.execute()
                    for i, tags_str in enumerate(results):
                        if tags_str and tag in tags_str.split(','):
                            metadata_keys.append(batch[i])
                if cursor == 0:
                    break
            
            all_keys = list(set(keys + metadata_keys))
            if all_keys:
                await r.unlink(*all_keys)
            await r.unlink(f'zc:ti:{tag}')
            await r.srem('zc:tags', tag)
            return {'deleted': len(all_keys), 'tag': tag}
        finally:
            await r.aclose()


class DashboardHandler(BaseHTTPRequestHandler):
    provider = ProductionDataProvider()
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        if path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())
        elif path == '/api/data':
            asyncio.run(self.handle_get_data())
        elif path == '/api/value':
            asyncio.run(self.handle_get_value(params))
        else:
            self.send_response(404)
            self.end_headers()
    
    async def handle_get_data(self):
        try:
            data = await self.provider.get_all_data()
            self.send_json(data)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    async def handle_get_value(self, params):
        try:
            key = unquote(params.get('key', [''])[0])
            data = await self.provider.get_value(key)
            self.send_json(data)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        
        if path == '/api/unlink':
            asyncio.run(self.handle_unlink(params))
        elif path == '/api/unlink-tag':
            asyncio.run(self.handle_unlink_tag(params))
        else:
            self.send_response(404)
            self.end_headers()
    
    async def handle_unlink(self, params):
        try:
            key = unquote(params.get('key', [''])[0])
            result = await self.provider.unlink_key(key)
            self.send_json(result)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    async def handle_unlink_tag(self, params):
        try:
            tag = unquote(params.get('tag', [''])[0])
            result = await self.provider.unlink_tag(tag)
            self.send_json(result)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass


def main():
    import os
    os.system('lsof -ti:8765 | xargs kill -9 2>/dev/null')
    time.sleep(0.5)
    
    server = ThreadedHTTPServer(('0.0.0.0', 8765), DashboardHandler)
    print('''
╔══════════════════════════════════════════════════════════════════════════════╗
║         REDIS CACHE VISUALIZER - PRODUCTION DASHBOARD                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  URL: http://localhost:8765                                                  ║
║                                                                              ║
║  Features:                                                                   ║
║  • ECharts Treemap - Professional cache distribution visualization           ║
║  • Health Monitoring - Hit rate, evictions, fragmentation                    ║
║  • Keys Browser - Filterable, sortable with tag badges                       ║
║  • Large Key Detection - Finds keys >1MB                                     ║
║  • No-TTL Tracker - Identifies keys without expiration                       ║
║  • Tag Manager - Browse and UNLINK by tag                                    ║
║                                                                              ║
║  All operations use SCAN and UNLINK (production-safe)                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
''')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
