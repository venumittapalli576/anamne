"""Quick smoke-test for the clustering helper."""
from anamne.agents.oracle import _cluster_by_overlap

sample = [
    {"id": "a1", "fact": "I prefer Python over Go for backend services", "tags": []},
    {"id": "a2", "fact": "I prefer Python for backend and scripting work", "tags": []},
    {"id": "b1", "fact": "The database uses PostgreSQL not MySQL", "tags": []},
    {"id": "b2", "fact": "PostgreSQL was chosen over MySQL for the database", "tags": []},
    {"id": "c1", "fact": "I work in Pacific Standard Time zone", "tags": []},
]

clusters = _cluster_by_overlap(sample, threshold=0.3)
print("Clusters found:", len(clusters))
for i, c in enumerate(clusters):
    ids = [f["id"] for f in c]
    print(f"  Cluster {i+1} ({len(c)} facts): {ids}")

# Expect: a1+a2 grouped, b1+b2 grouped, c1 alone
assert len(clusters) == 3, f"Expected 3 clusters, got {len(clusters)}"
for c in clusters:
    if len(c) == 2:
        ids = {f["id"] for f in c}
        assert ids in ({"a1", "a2"}, {"b1", "b2"}), f"Unexpected cluster: {ids}"
print("OK — clustering works correctly")
