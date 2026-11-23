import csv
from pathlib import Path

FILES = [
    Path("data/processed/pmbi_products.csv"),
    Path("data/processed/nlem2022_medicines.csv"),
]

print("AQUIFERASK DATASET REPORT")
print("=" * 40)

for path in FILES:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    print(f"\nDataset: {path.name}")
    print(f"Total records: {len(rows)}")
    print(f"Columns: {list(rows[0].keys()) if rows else 'No columns'}")
    print(f"Empty records: {sum(not any(v.strip() for v in row.values()) for row in rows)}")

print("\nReport completed.")
