"""
Company sustainability report figures (Google, Microsoft, Meta, etc.).

There is no API for this -- companies publish PDF/HTML sustainability
reports on their own schedule with inconsistent units and disclosure
levels. This is intentional: reconciling this into a clean schema is one
of the genuinely hard, real parts of this project (and a good talking
point in interviews -- "here's how I handled inconsistent disclosure").

Workflow:
1. Manually pull the water-use / PUE figures you need from each report
   (cite the source URL + report year in the `source_url` field below).
2. Enter them in `RAW_ENTRIES`.
3. `load_sustainability_entries()` turns this into the same normalized
   schema used by the other ingesters, so it joins cleanly downstream.

This keeps a paper trail of exactly which number came from which
company's report, which matters if you want to defend a number later
(and matters for basic data provenance hygiene).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class SustainabilityEntry:
    company: str
    facility_region: str  # e.g. "Council Bluffs, IA" or "The Dalles, OR"
    report_year: int
    metric_name: str  # e.g. "water_withdrawal_million_liters", "pue"
    metric_value: float
    unit: str
    source_url: str
    notes: str = ""


# Fill this in as you research each company's report. Left mostly empty
# on purpose -- these are real numbers you should pull and cite yourself
# rather than have fabricated for you.
RAW_ENTRIES: list[SustainabilityEntry] = [
    # Example shape -- replace with real sourced figures:
    # SustainabilityEntry(
    #     company="Google",
    #     facility_region="The Dalles, OR",
    #     report_year=2025,
    #     metric_name="water_withdrawal_million_liters",
    #     metric_value=0.0,  # TODO: pull real figure
    #     unit="million_liters",
    #     source_url="https://sustainability.google/reports/",
    #     notes="TODO: confirm figure is per-facility not company-wide",
    # ),
]


def load_sustainability_entries() -> pd.DataFrame:
    if not RAW_ENTRIES:
        return pd.DataFrame(
            columns=[
                "company",
                "facility_region",
                "report_year",
                "metric_name",
                "metric_value",
                "unit",
                "source_url",
                "notes",
            ]
        )
    return pd.DataFrame([entry.__dict__ for entry in RAW_ENTRIES])


if __name__ == "__main__":
    print(load_sustainability_entries())
