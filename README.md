# AquiferAsk

Answers groundwater questions for Tamil Nadu blocks: status category, extraction levels and recharge advice, from CGWB reports.

**Status:** Day 1 foundation (FastAPI skeleton, quality gates). Live URL from Day 5.

## Who it's for

Panchayat engineer in a water-stressed block of Ramanathapuram planning recharge structures.

## The problem

Groundwater information for Tamil Nadu blocks is available in large CGWB reports. It is difficult for engineers to find accurate information for a particular block and assessment year. Groundwater categories such as Safe, Semi-critical, Critical and Over-exploited may change over time. Engineers need an easy way to check extraction levels and understand groundwater conditions. AquiferAsk helps them find this information and provides useful recharge advice.

## Data sources

CGWB Dynamic Ground Water Resources reports (several assessment years), Tamil Nadu district groundwater brochures, aquifer mapping (NAQUIM) reports, Master Plan for Artificial Recharge.

- https://cgwb.gov.in/
- https://indiawris.gov.in/
- Terms: Public CGWB reports.

## Hardest problem (my interview story)

Year-specific tables: a block's category and stage of extraction change across assessments. Answers must name the year, pull the right table row and compute changes in code.

## Signature feature

Block trend card: pick a block and see its category and stage of extraction across assessment years.

## Target metric


## Target metric

Block-level numbers exact for 95%+ of 50 lookups.

Performance targets are set at 500 ms for record lookups and 6 seconds for full answers to allow sufficient time for retrieving and processing large CGWB groundwater reports.


## Run it locally

```bash
uv sync
cp .env.example .env   # Windows: copy .env.example .env
uv run uvicorn aquiferask.api.main:create_app --factory --reload
