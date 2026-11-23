import csv
import re
from pathlib import Path

from pypdf import PdfReader

PDF_PATH = Path("data/raw/cdsco/nlem2022.pdf")
OUTPUT_PATH = Path("data/processed/nlem2022_medicines.csv")

START_PAGE = 85  # PDF page 86
END_PAGE = 101  # PDF page 101, exclusive

MEDICINE_PATTERN = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")
SUBITEM_PATTERN = re.compile(r"^\s*([a-z])[\).]\s*(.+?)\s*$", re.IGNORECASE)


def clean(value):
    return " ".join(value.replace("\xa0", " ").split())


def extract_medicines():
    reader = PdfReader(str(PDF_PATH))
    medicines = []
    current_medicine = None

    for page_number in range(START_PAGE, END_PAGE):
        text = reader.pages[page_number].extract_text() or ""

        for line in text.splitlines():
            line = clean(line)

            if not line or line.startswith("Alphabetical List of Medicines"):
                continue

            medicine_match = MEDICINE_PATTERN.match(line)

            if medicine_match:
                if current_medicine:
                    medicines.append(current_medicine)

                current_medicine = {
                    "sr_no": int(medicine_match.group(1)),
                    "medicine_name": clean(medicine_match.group(2)),
                    "sub_items": [],
                }
                continue

            subitem_match = SUBITEM_PATTERN.match(line)

            if subitem_match and current_medicine:
                current_medicine["sub_items"].append(clean(subitem_match.group(2)))

    if current_medicine:
        medicines.append(current_medicine)

    return medicines


def main():
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    medicines = extract_medicines()

    if len(medicines) != 384:
        raise ValueError(f"Expected 384 medicines, found {len(medicines)}")

    expected = list(range(1, 385))
    actual = [item["sr_no"] for item in medicines]

    if actual != expected:
        raise ValueError("Medicine serial numbers are missing or out of order")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["sr_no", "medicine_name", "sub_items"],
        )
        writer.writeheader()

        for medicine in medicines:
            writer.writerow(
                {
                    "sr_no": medicine["sr_no"],
                    "medicine_name": medicine["medicine_name"],
                    "sub_items": " | ".join(medicine["sub_items"]),
                }
            )

    print("NLEM extraction successful!")
    print("Total medicines:", len(medicines))
    print("First medicine:", medicines[0])
    print("Last medicine:", medicines[-1])
    print("CSV saved:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
