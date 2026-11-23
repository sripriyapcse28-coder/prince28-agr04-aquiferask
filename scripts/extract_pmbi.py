import csv
import re
from pathlib import Path

from pypdf import PdfReader

PDF_PATH = Path("data/raw/pmbi/pmbi-products.pdf")
OUTPUT_PATH = Path("data/processed/pmbi_products.csv")

NAME_START = 40
UNIT_START = 70

ROW_PATTERN = re.compile(r"^\s*(\d+)\s+(\d+)\s+")
PRICE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*$")


def clean(value):
    return " ".join(value.replace("\xa0", " ").split())


def parse_block(lines, page_number):
    row_indexes = [i for i, line in enumerate(lines) if ROW_PATTERN.match(line)]

    if not row_indexes:
        return None

    if len(row_indexes) != 1:
        raise ValueError(f"Multiple product rows in one block on page {page_number}")

    row_index = row_indexes[0]
    row_line = lines[row_index]

    match = ROW_PATTERN.match(row_line)
    serial = int(match.group(1))
    drug_code = int(match.group(2))

    price_match = PRICE_PATTERN.search(row_line)

    if not price_match:
        raise ValueError(f"Missing MRP for product {serial}")

    name_parts = []
    unit_parts = []

    for index, line in enumerate(lines):
        name_part = clean(line[NAME_START:UNIT_START])

        if name_part:
            name_parts.append(name_part)

        if index == row_index:
            unit_part = clean(line[UNIT_START : price_match.start()])
        else:
            unit_part = clean(line[UNIT_START:])

        if unit_part:
            unit_parts.append(unit_part)

    return {
        "sr_no": serial,
        "drug_code": drug_code,
        "generic_name": clean(" ".join(name_parts)),
        "unit_size": clean(" ".join(unit_parts)),
        "mrp_inr": price_match.group(1),
    }


def extract_products():
    reader = PdfReader(str(PDF_PATH))
    products = []

    for page_number, page in enumerate(reader.pages, start=1):
        lines = page.extract_text(extraction_mode="layout").splitlines()

        block = []

        for line in lines:
            if not line.strip():
                if block:
                    product = parse_block(block, page_number)
                    if product:
                        products.append(product)
                    block = []
            else:
                block.append(line)

        if block:
            product = parse_block(block, page_number)
            if product:
                products.append(product)

    return products


def main():
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    products = extract_products()

    if len(products) != 2439:
        raise ValueError(f"Expected 2439 products, found {len(products)}")

    expected = list(range(1, 2440))
    actual = [item["sr_no"] for item in products]

    if actual != expected:
        raise ValueError("Product serial numbers are missing or out of order")

    for item in products:
        if not item["generic_name"] or not item["unit_size"]:
            raise ValueError(f"Missing name or unit size for product {item['sr_no']}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "sr_no",
                "drug_code",
                "generic_name",
                "unit_size",
                "mrp_inr",
            ],
        )
        writer.writeheader()
        writer.writerows(products)

    print("Extraction successful!")
    print("Total products:", len(products))
    print("First product:", products[0])
    print("Second product:", products[1])
    print("Third product:", products[2])
    print("Last product:", products[-1])
    print("CSV saved:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
