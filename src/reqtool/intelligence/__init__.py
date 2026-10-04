"""
reqtool.intelligence
====================
Duplicate detection, test generation and the audit package, one module each (ARC-14).
"""

from .duplicates import DuplicateDetector, detect_duplicate_requirements
from .testgen import generate_test_cases_from_spec
from .audit import generate_audit_package

__all__ = ["DuplicateDetector", "detect_duplicate_requirements", "generate_test_cases_from_spec",
           "generate_audit_package"]
