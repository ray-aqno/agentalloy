#!/usr/bin/env python3
"""Scan all SKILL.md files for duplicate content and report similarities."""

import os
import hashlib
from collections import defaultdict, deque


def token_hash(content):
    """Create a fuzzy hash based on content tokens."""
    text = content.lower()
    text = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    tokens = text.split()
    fp_tokens = tokens[:500]
    return hashlib.md5(" ".join(fp_tokens).encode()).hexdigest()[:16]


def jaccard_similarity(s1, s2):
    """Compute Jaccard similarity between two token sets."""
    tokens1 = set(s1.lower().split())
    tokens2 = set(s2.lower().split())
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)


def find_all_skill_md(base_paths):
    """Find all SKILL.md files in the given base directories."""
    skill_files = []
    for base in base_paths:
        base = os.path.expanduser(base)
        if os.path.isdir(base):
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    if f == "SKILL.md":
                        skill_files.append(os.path.join(root, f))
    return sorted(skill_files)


def main():
    base_paths = [
        "/home/nmeyers/.hermes",
        "/home/nmeyers/dev/agentalloy",
    ]

    skill_files = find_all_skill_md(base_paths)
    print(f"Found {len(skill_files)} SKILL.md files.\n")

    if not skill_files:
        print("No SKILL.md files found.")
        return

    # Phase 1: Exact duplicates via content hash
    exact_groups = defaultdict(list)
    file_contents = {}
    for fpath in skill_files:
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            print(f"  Warning: could not read {fpath}: {e}")
            continue
        file_contents[fpath] = content
        h = hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
        exact_groups[h].append((fpath, content))

    exact_duplicates = {h: pairs for h, pairs in exact_groups.items() if len(pairs) > 1}

    print("=" * 72)
    print("EXACT DUPLICATES (identical content)")
    print("=" * 72)

    if exact_duplicates:
        for h, pairs in exact_duplicates.items():
            print(f"\n  Hash: {h}")
            print(f"  Count: {len(pairs)} files")
            for fpath, _ in pairs:
                rel = os.path.relpath(fpath, "/home/nmeyers")
                print(f"    - {rel}")
    else:
        print("  No exact duplicates found.")

    # Phase 2: Near-duplicates via token hash grouping + Jaccard
    token_groups = defaultdict(list)
    for fpath, content in file_contents.items():
        th = token_hash(content)
        token_groups[th].append((fpath, content))

    # Build similarity map
    near_dup_map = {}
    for th, pairs in token_groups.items():
        if len(pairs) < 2:
            continue
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                fp1, c1 = pairs[i]
                fp2, c2 = pairs[j]
                sim = jaccard_similarity(c1, c2)
                if sim >= 0.3:
                    key = tuple(sorted([fp1, fp2]))
                    if key not in near_dup_map or sim > near_dup_map[key][1]:
                        near_dup_map[key] = (fp1, fp2, sim)

    # Build adjacency and find clusters
    adjacency = defaultdict(set)
    for key, (fp1, fp2, sim) in near_dup_map.items():
        adjacency[fp1].add((fp2, sim))
        adjacency[fp2].add((fp1, sim))

    visited = set()
    clusters = []
    for fp in adjacency:
        if fp in visited:
            continue
        cluster = []
        queue = deque([fp])
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            cluster.append(node)
            for neighbor, sim in adjacency[node]:
                if neighbor not in visited:
                    queue.append(neighbor)
        if len(cluster) > 1:
            clusters.append(cluster)

    print(f"\n{'=' * 72}")
    print("NEAR-DUPLICATE CLUSTERS (Jaccard similarity >= 0.3)")
    print("=" * 72)

    if clusters:
        for idx, cluster in enumerate(clusters, 1):
            print(f"\n  Cluster {idx}: {len(cluster)} files")
            for fp in sorted(cluster):
                rel = os.path.relpath(fp, "/home/nmeyers")
                size = len(file_contents.get(fp, ""))
                print(f"    - {rel} ({size} bytes)")
            print("  Pairwise similarities:")
            for i in range(len(cluster)):
                for j in range(i + 1, len(cluster)):
                    fp1, fp2 = cluster[i], cluster[j]
                    key = tuple(sorted([fp1, fp2]))
                    sim = near_dup_map.get(key, (None, None, 0))[2]
                    print(f"    - {os.path.relpath(fp1, '/home/nmeyers')} <-> {os.path.relpath(fp2, '/home/nmeyers')}: {sim:.1%}")
    else:
        print("  No near-duplicate clusters found.")

    # Phase 3: Summary statistics
    print(f"\n{'=' * 72}")
    print("SUMMARY")
    print("=" * 72)
    total_files = len(skill_files)
    exact_dup_files = sum(len(p) for p in exact_duplicates.values())
    near_dup_files = len(visited)
    unique_content = total_files - exact_dup_files
    print(f"  Total SKILL.md files scanned:   {total_files}")
    print(f"  Exact duplicate groups:         {len(exact_duplicates)}")
    print(f"  Files involved in exact dupes:  {exact_dup_files}")
    print(f"  Near-duplicate clusters:        {len(clusters)}")
    print(f"  Files involved in near-dupes:   {near_dup_files}")
    print(f"  Unique content files:           {unique_content}")


if __name__ == "__main__":
    main()
