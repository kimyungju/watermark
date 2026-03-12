"""Shared constants for watermark detection and removal."""

import re

# Known watermark platform patterns (StuDocu, Scribd, CourseHero, etc.)
PLATFORM_PATTERNS = re.compile(
    r"(studocu|scribd|coursehero|chegg|bartleby|"
    r"lOMoARcPSD|"
    r"messages\.downloaded_by|messages\.pdf_cover|messages\.studocu|"
    r"downloaded\s+by|uploaded\s+by|"
    r"this\s+document\s+is\s+available\s+on|"
    r"get\s+the\s+app|"
    r"not[\s_]sponsored[\s_]or[\s_]endorsed)",
    re.IGNORECASE,
)

# Classic watermark keywords
CLASSIC_WATERMARK_PATTERNS = re.compile(
    r"\b(DRAFT|CONFIDENTIAL|SAMPLE|COPY|DO NOT DISTRIBUTE|WATERMARK|PREVIEW)\b",
    re.IGNORECASE,
)

# Legitimate repeated text to ignore
IGNORE_COMMON_TEXT = re.compile(
    r"^(\d{1,4}|[ivxlcdm]+|page\s*\d+|©.*|\s*)$",
    re.IGNORECASE,
)
