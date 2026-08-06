"""Readers and writers.

Named ``fileio`` rather than ``io`` deliberately: a top-level package named
``io`` shadows the stdlib module of the same name (docs/method/TOOLING.md).

This layer owns every external format: CSV text, the NGS GEOID18 binary grid,
and the generated report. The computation core never imports it.
"""
