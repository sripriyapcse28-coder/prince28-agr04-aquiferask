"""Structured metadata contract for AquiferAsk documents."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

Short = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]

Values = Annotated[
    list[Short],
    Field(default_factory=list, max_length=8),
]

AssessmentYear = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^\d{4}(-\d{2})?$",
        min_length=4,
        max_length=7,
    ),
]

Kind = Literal[
    "guideline",
    "rule",
    "notice",
    "list",
    "report",
    "faq",
    "form",
    "tutorial",
    "reference",
    "other",
]


class DocMeta(BaseModel):
    """Metadata extracted from one AquiferAsk groundwater document."""

    model_config = ConfigDict(extra="forbid")

    # Common document fields
    doc_kind: Kind
    year: int | None = Field(default=None, ge=1950, le=2027)
    language: Literal["en", "ta", "hi", "other"]
    summary: str = Field(min_length=20, max_length=300)
    topics: Annotated[list[Short], Field(min_length=1, max_length=6)]

    # AquiferAsk-specific fields
    assessment_year: Annotated[
        list[AssessmentYear],
        Field(default_factory=list, max_length=8),
    ]
    district: Values
    block: Values
    category: Annotated[
        list[
            Literal[
                "Safe",
                "Semi-Critical",
                "Critical",
                "Over-exploited",
            ]
        ],
        Field(default_factory=list, max_length=8),
    ]
    recharge_mcm: Values

    @field_validator("topics")
    @classmethod
    def tidy_topics(cls, value: list[str]) -> list[str]:
        """Lowercase topics and remove duplicates."""
        return list(dict.fromkeys(topic.lower() for topic in value))
