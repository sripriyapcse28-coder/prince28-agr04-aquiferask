import argparse
from pathlib import Path

from pypdf import PdfReader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-pages", type=int, default=6000)
    args = parser.parse_args()

    pdf_files = sorted(Path("data/raw").glob("*.pdf"))
    pdf_files += sorted(Path("data/raw/cgwb").glob("*.pdf"))

    documents = []
    total_pages = 0
    total_bytes = 0

    print("AQUIFERASK GROUNDWATER DATASET REPORT")
    print("=" * 45)

    for path in pdf_files:
        try:
            reader = PdfReader(str(path), strict=False)
            pages = len(reader.pages)
            size = path.stat().st_size

            documents.append(
                {
                    "name": path.name,
                    "pages": pages,
                    "size": size,
                }
            )

            total_pages += pages
            total_bytes += size

            print(f"{path.name}: {pages} pages | {size / 1024 / 1024:.2f} MB")
        except Exception as error:
            print(f"ERROR: {path.name}: {error}")

    total_mb = total_bytes / 1024 / 1024
    average_mb_per_page = total_mb / total_pages if total_pages else 0
    estimated_mb = average_mb_per_page * args.full_pages
    gap = max(args.full_pages - total_pages, 0)
    progress = total_pages / args.full_pages * 100 if args.full_pages else 0

    dataset = [
        "# AquiferAsk Dataset",
        "",
        "## Current corpus",
        "",
        f"- PDF documents: {len(documents)}",
        f"- Total pages: {total_pages}",
        f"- Total size: {total_mb:.2f} MB",
        "- Main source: Central Ground Water Board (CGWB)",
        "",
        "## Collected documents",
        "",
        "| Document | Pages | Size (MB) |",
        "|---|---:|---:|",
    ]

    for doc in documents:
        dataset.append(f"| {doc['name']} | {doc['pages']} | {doc['size'] / 1024 / 1024:.2f} |")

    dataset += [
        "",
        "## Licence",
        "",
        "CGWB permits free reproduction of its materials when they are "
        "accurately presented and the source is prominently acknowledged. "
        "Third-party copyrighted material is excluded and requires "
        "permission from its copyright holder.",
        "",
        "## Known gaps",
        "",
        f"- Current corpus has {total_pages} pages; the target is {args.full_pages} pages.",
        f"- Remaining page gap: {gap} pages.",
        "- Only one assessment-year PDF is currently registered.",
        "- The district brochures are historical documents; newer "
        "district-level information is still needed.",
        "- PDF text extraction, OCR checks, and indexing are not yet "
        "included in this collection report.",
        "",
        "## Source list",
        "",
        "See `data/sources.csv` for document URLs and licence notes.",
        "",
    ]

    Path("DATASET.md").write_text("\n".join(dataset), encoding="utf-8")

    capacity = [
        "# AquiferAsk Capacity Report",
        "",
        "## 1. What is the current corpus size?",
        "",
        f"- Documents: {len(documents)} PDFs",
        f"- Pages: {total_pages}",
        f"- Storage: {total_mb:.2f} MB",
        "",
        "## 2. What is the target and how much is missing?",
        "",
        f"- Target: {args.full_pages} pages",
        f"- Collected: {total_pages} pages",
        f"- Remaining: {gap} pages",
        f"- Progress: {progress:.2f}%",
        "",
        "## 3. How much storage may the target require?",
        "",
        f"- Average current storage per page: {average_mb_per_page:.3f} MB",
        f"- Estimated storage for {args.full_pages} pages: "
        f"{estimated_mb:.2f} MB ({estimated_mb / 1024:.2f} GB)",
        "",
        "This is a rough estimate based on the current PDFs. Actual "
        "storage depends on document quality, images, and OCR output.",
        "",
        "## 4. What are the main capacity challenges?",
        "",
        "- Collecting more assessment years and district groundwater reports.",
        "- Checking PDF quality and extracting text from scanned documents.",
        "- OCR may increase storage and processing time.",
        "- Search indexing and future document growth will require "
        "additional storage and processing capacity.",
        "",
        "## Next steps",
        "",
        "- Collect additional CGWB assessment years.",
        "- Add more Tamil Nadu district groundwater reports.",
        "- Extract and validate PDF text.",
        "- Measure indexing time and storage after extraction.",
        "",
    ]

    Path("docs/CAPACITY.md").write_text("\n".join(capacity), encoding="utf-8")

    print("\nReport completed.")
    print(f"Documents: {len(documents)}")
    print(f"Pages: {total_pages}")
    print(f"Size: {total_mb:.2f} MB")
    print("Created DATASET.md and docs/CAPACITY.md")


if __name__ == "__main__":
    main()
