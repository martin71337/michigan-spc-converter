"""Pure computation core.

Everything in this subpackage is stdlib-only and side-effect free: no Qt, no
file I/O, no network, no third-party geodesy library. Every empirical constant
carries its citation to NOAA Manual NOS NGS 5 in an adjacent comment.

This rule is machine-enforced by ``tests/test_architecture.py``.
"""
