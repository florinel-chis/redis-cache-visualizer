#!/usr/bin/env python3
"""
Visual tag hierarchy generator for Magento Redis cache
Shows tag relationships and dependencies
"""

import redis
import json
from collections import defaultdict

def analyze_tag_hierarchy():
    """Analyze the tag hierarchy and relationships"""
    r = redis.Redis(decode_responses=True)
    
    # Get all tags
    all_tags = sorted(list(r.smembers('zc:tags')))
    
    # Categorize tags
    categories = {
        'System': [],
        'Catalog Products': [],
        'Catalog Categories': [],
        'Configuration': [],
        'Database': [],
        'Layout': [],
        'Block HTML': [],
        'Translation': [],
        'Store/Website': [],
        'EAV': [],
        'Reflection': [],
        'Sales/Orders': [],
        'Customer': [],
        'Theme': [],
        'Other': []
    }
    
    for tag in all_tags:
        if tag == 'eec_MAGE':
            categories['System'].append(tag)
        elif tag.startswith('eec_CAT_P_'):
            categories['Catalog Products'].append(tag)
        elif tag.startswith('eec_CAT_C_'):
            categories['Catalog Categories'].append(tag)
        elif 'CONFIG' in tag:
            categories['Configuration'].append(tag)
        elif 'DB_' in tag or 'DDL' in tag:
            categories['Database'].append(tag)
        elif 'LAYOUT' in tag:
            categories['Layout'].append(tag)
        elif 'BLOCK_HTML' in tag:
            categories['Block HTML'].append(tag)
        elif 'TRANSLATE' in tag:
            categories['Translation'].append(tag)
        elif 'STORE_' in tag or 'WEBSITE_' in tag:
            categories['Store/Website'].append(tag)
        elif 'EAV' in tag:
            categories['EAV'].append(tag)
        elif 'REFLECTION' in tag:
            categories['Reflection'].append(tag)
        elif 'SALES' in tag or 'ORDER' in tag:
            categories['Sales/Orders'].append(tag)
        elif 'CUSTOMER' in tag:
            categories['Customer'].append(tag)
        elif 'THEME' in tag:
            categories['Theme'].append(tag)
        else:
            categories['Other'].append(tag)
    
    # Get key counts for each tag
    tag_stats = {}
    for tag in all_tags:
        count = r.scard(f'zc:ti:{tag}')
        tag_stats[tag] = count
    
    return categories, tag_stats

def print_hierarchy():
    """Print the tag hierarchy in a tree format"""
    categories, tag_stats = analyze_tag_hierarchy()
    
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                  MAGENTO REDIS CACHE TAG HIERARCHY                            ║
╠══════════════════════════════════════════════════════════════════════════════╣

Root: zc:tags (Set containing all tags)
│
├── System Tags
│   └── eec_MAGE (Applied to ALL cache entries - 502 keys)
│       └── System-level invalidation
│
├── Catalog Tags
│   ├── eec_CAT_P (87 keys)
│   │   └── eec_CAT_P_<product_id> - Individual product cache
│   └── eec_CAT_C (Category cache)
│       └── eec_CAT_C_<category_id> - Individual category cache
│
├── Configuration Tags
│   ├── eec_CONFIG (43 keys)
│   │   ├── System configuration
│   │   ├── Module configuration  
│   │   └── Store configuration
│   └── eec_CONFIG_GLOBAL
│
├── Database Tags
│   ├── eec_DB_PDO_MYSQL_DDL (34 keys)
│   │   └── Table structure/schema cache
│   ├── eec_DB_DDL
│   └── eec_RESOLVED_DDL
│
├── EAV Tags
│   ├── eec_EAV (36 keys)
│   │   └── Entity-Attribute-Value metadata
│   ├── eec_EAV_ENTITY_TYPES
│   ├── eec_EAV_ENTITY_ATTRIBUTRES
│   └── eec_EAV_ENTITY_ATTRIBUTE_OPTIONS
│
├── Layout Tags
│   ├── eec_LAYOUT_GENERAL_CACHE_TAG (36 keys)
│   ├── eec_LAYOUT (12 keys)
│   ├── eec_LAYOUT_<design_area>
│   └── eec_LAYOUT_adminhtml_STORE<store_id>
│
├── Block HTML Tags
│   ├── eec_BLOCK_HTML (18 keys)
│   │   └── Block content cache
│   └── eec_BLOCK_<block_name>
│
├── Translation Tags
│   ├── eec_TRANSLATE (16 keys)
│   ├── eec_TRANSLATE_<locale>
│   └── eec_TRANSLATE_EN_US
│
├── Reflection Tags
│   ├── eec_REFLECTION (338 keys)
│   │   └── Class introspection cache
│   ├── eec_REFLECTION_<class_name>
│   └── eec_INTERFACE_<interface_name>
│
├── Sales Tags
│   ├── eec_SALES_TOTALS_CONFIG
│   └── eec_ORDER_GRID
│
├── Customer Tags
│   └── eec_CUSTOMER
│
├── Store/Website Tags
│   ├── eec_STORE (Store IDs)
│   ├── eec_STORE_<store_id> (Individual stores)
│   ├── eec_WEBSITE (Website IDs)
│   └── eec_WEBSITE_<website_id> (Individual websites)
│
└── Theme Tags
    └── eec_THEME

══════════════════════════════════════════════════════════════════════════════

""")
    
    # Print category summary
    print("Category Summary:")
    print("-" * 60)
    total_tags = 0
    for category, tags in categories.items():
        if tags:
            count = len(tags)
            total_tags += count
            total_keys = sum(tag_stats.get(t, 0) for t in tags)
            print(f"  {category:25s} {count:3d} tags  {total_keys:4d} keys")
    
    print("-" * 60)
    print(f"  {'TOTAL':25s} {total_tags:3d} tags  {sum(tag_stats.values()):4d} key references")
    
    # Print top tags by key count
    print("\n\nTop 15 Tags by Key Count:")
    print("-" * 60)
    sorted_tags = sorted(tag_stats.items(), key=lambda x: x[1], reverse=True)
    for tag, count in sorted_tags[:15]:
        print(f"  {tag:50s} {count:4d}")

def generate_tag_insights():
    """Generate insights about tag usage"""
    r = redis.Redis(decode_responses=True)
    all_tags = list(r.smembers('zc:tags'))
    
    # Find orphaned tags (no keys)
    orphaned = []
    single_key = []
    heavily_used = []
    
    for tag in all_tags:
        count = r.scard(f'zc:ti:{tag}')
        if count == 0:
            orphaned.append(tag)
        elif count == 1:
            single_key.append(tag)
        elif count > 100:
            heavily_used.append((tag, count))
    
    print("\n\n══════════════════════════════════════════════════════════════════")
    print("                         TAG INSIGHTS                             ")
    print("══════════════════════════════════════════════════════════════════\n")
    
    print(f"Orphaned tags (0 keys): {len(orphaned)}")
    if orphaned[:5]:
        print("  Sample:", ", ".join(orphaned[:5]))
    
    print(f"\nSingle-key tags: {len(single_key)}")
    if single_key[:5]:
        print("  Sample:", ", ".join(single_key[:5]))
    
    print(f"\nHeavily used tags (>100 keys):")
    for tag, count in sorted(heavily_used, key=lambda x: x[1], reverse=True):
        print(f"  {tag}: {count} keys")
    
    # Tag statistics
    counts = [r.scard(f'zc:ti:{t}') for t in all_tags]
    avg_keys_per_tag = sum(counts) / len(counts) if counts else 0
    max_keys = max(counts) if counts else 0
    min_keys = min(counts) if counts else 0
    
    print(f"\nTag Statistics:")
    print(f"  Total tags: {len(all_tags)}")
    print(f"  Average keys per tag: {avg_keys_per_tag:.1f}")
    print(f"  Max keys per tag: {max_keys}")
    print(f"  Min keys per tag: {min_keys}")

if __name__ == '__main__':
    print_hierarchy()
    generate_tag_insights()
