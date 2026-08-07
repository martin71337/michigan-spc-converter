#!/usr/bin/env bash
# Probe 7: second mutation round - unit and zone field selection in the panel,
# plus the GUI seams the first round did not reach.
set -u
ROOT="/c/Users/marti/AppData/Local/Temp/claude/C--claude-projects-coord-convert/a60a51ed-42f6-47c2-9551-b32bac810042/scratchpad/mut"
cd "$ROOT" || exit 1

run() {
  out=$(QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -m pytest -q --no-header \
        -p no:cacheprovider 2>&1 | tail -3)
  echo "--- $1"
  echo "$out" | tr -d '\r' | grep -E "passed|failed|error" | head -2
}

M() {
  local name="$1" file="$2" old="$3" new="$4"
  cp "$file" "$file.bak"
  py - "$file" "$old" "$new" <<'PY'
import sys, io
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
s = io.open(path, encoding="utf-8").read()
if old not in s:
    print("!! PATTERN NOT FOUND in", path); sys.exit(3)
io.open(path, "w", encoding="utf-8").write(s.replace(old, new, 1))
PY
  run "$name"
  cp "$file.bak" "$file"; rm -f "$file.bak"
}

M "N1 GEODETIC_TO_ZONE INPUT units line names the OUTPUT unit" michspc/gui/results_model.py \
  'ResultValue(UNITS_LABEL, _units_text(settings.input_unit)),
            ),
        )
        target = ResultSection(' \
  'ResultValue(UNITS_LABEL, _units_text(settings.output_unit)),
            ),
        )
        target = ResultSection('

M "N2 ZONE_TO_GEODETIC INPUT block uses the OUTPUT unit" michspc/gui/results_model.py \
  '*_grid_values(
                    settings.source_zone,
                    settings.input_unit,
                    point.row.northing,' \
  '*_grid_values(
                    settings.source_zone,
                    settings.output_unit,
                    point.row.northing,'

M "N3 ZONE_TO_ZONE INPUT block uses the OUTPUT unit" michspc/gui/results_model.py \
  '*_grid_values(
                settings.source_zone,
                settings.input_unit,
                point.row.northing,' \
  '*_grid_values(
                settings.source_zone,
                settings.output_unit,
                point.row.northing,'

M "N4 ZONE_TO_ZONE INPUT block names the TARGET zone" michspc/gui/results_model.py \
  '*_grid_values(
                settings.source_zone,' \
  '*_grid_values(
                settings.target_zone,'

M "N5 typed_point_source always says GRID" michspc/gui/single_point.py \
  'if self.from_zone.currentData() == GEODETIC:
            return pnezd.TYPED_POINT_SOURCE_GEODETIC
        return pnezd.TYPED_POINT_SOURCE_GRID' \
  'return pnezd.TYPED_POINT_SOURCE_GRID'

M "N6 convert() no longer clears a previous result on refusal" michspc/gui/single_point.py \
  '        self.result = None
        self.last_failure = None
        self._render_sections(None)

        try:' \
  '        self.last_failure = None

        try:'

M "N7 elevation field text ignored (always blank)" michspc/gui/single_point.py \
  'self.elevation_edit.text(),
                source=self.typed_point_source(),' \
  '"",
                source=self.typed_point_source(),'

M "N8 single_point settings uses a fabricated input_path" michspc/gui/single_point.py \
  'input_path=None,
            output_directory=None,' \
  'input_path=__import__("pathlib").Path("typed.txt"),
            output_directory=None,'

M "N9 Copy all stays enabled after a refusal" michspc/gui/single_point.py \
  'self.copy_all_button.setEnabled(sections is not None)' \
  'self.copy_all_button.setEnabled(True)'

M "N10 longitude relevance ignores ZONE_TO_GEODETIC" michspc/gui/controls.py \
  'return direction in (
        Direction.GEODETIC_TO_ZONE,
        Direction.ZONE_TO_GEODETIC,
    )' \
  'return direction is Direction.GEODETIC_TO_ZONE'

M "N11 clipboard_text joins with a comma not a tab" michspc/gui/results_model.py \
  'lines.extend(f"{value.label}\t{value.text}" for value in section.values)' \
  'lines.extend(f"{value.label},{value.text}" for value in section.values)'

M "N12 single_point_sections accepts a multi-point job" michspc/gui/results_model.py \
  'if len(result.points) != 1:' \
  'if False:'
