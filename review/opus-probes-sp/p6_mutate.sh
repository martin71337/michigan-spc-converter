#!/usr/bin/env bash
# Probe 6: seed defects into a COPY of the repo and see whether the suite fires.
set -u
ROOT="/c/Users/marti/AppData/Local/Temp/claude/C--claude-projects-coord-convert/a60a51ed-42f6-47c2-9551-b32bac810042/scratchpad/mut"
cd "$ROOT" || exit 1

run() {  # $1 = name
  out=$(QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 py -m pytest -q --no-header \
        -p no:cacheprovider 2>&1 | tail -3)
  code=$?
  echo "--- $1"
  echo "$out" | tr -d '\r' | grep -E "passed|failed|error" | head -2
}

apply() { # file, python-replacement via sed -i
  :
}

restore() {
  cp "$1.bak" "$1"
}

M() { # name file old new
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
  restore "$file"
  rm -f "$file.bak"
}

M "M1 lon DD ignores the chosen convention" michspc/gui/results_model.py \
  'fmt.longitude(conversion.longitude, positive_west=positive_west),' \
  'fmt.longitude(conversion.longitude),'

M "M2 longitude_dms hemisphere hardwired W" michspc/fileio/formatting.py \
  'hemisphere = "W" if value < 0 else "E"' \
  'hemisphere = "W"'

M "M3 _dms_magnitude rounds AFTER the split" michspc/fileio/formatting.py \
  'total_seconds = round(magnitude * 3600.0, seconds_decimals)' \
  'total_seconds = magnitude * 3600.0'

M "M4 parse_typed_point stops quoting" michspc/fileio/pnezd.py \
  "return '\"' + text.replace('\"', '\"\"') + '\"'" \
  'return text'

M "M5 zone_to_zone INPUT shows the TARGET factor" michspc/gui/results_model.py \
  'ResultValue(
                GRID_FACTOR_LABEL, fmt.factor(conversion.source_scale_factor)
            ),' \
  'ResultValue(
                GRID_FACTOR_LABEL, fmt.factor(conversion.target_scale_factor)
            ),'

M "M6 latitude_dms drops to 4 decimals" michspc/fileio/formatting.py \
  'def latitude_dms(value: float | None, seconds_decimals: int = 5) -> str:' \
  'def latitude_dms(value: float | None, seconds_decimals: int = 4) -> str:'

M "M7 job.run pathless guard deleted" michspc/job.py \
  'if source is None and settings.input_path is None:' \
  'if False:'

M "M8 output_stem pathless guard deleted" michspc/fileio/exports.py \
  'if settings.input_path is None:' \
  'if False:'

M "M9 form_is_complete ignores the second field" michspc/gui/single_point.py \
  'return bool(self.first_edit.text().strip()) and bool(
            self.second_edit.text().strip()
        )' \
  'return bool(self.first_edit.text().strip())'

M "M10 geodetic->geodetic becomes a job" michspc/gui/controls.py \
  'if source_data == GEODETIC and target_data == GEODETIC:
        return None' \
  'if False:
        return None'

M "M11 GEODETIC_TO_ZONE INPUT elevation uses OUTPUT unit" michspc/gui/results_model.py \
  'fmt.coordinate(point.row.elevation, settings.input_unit),' \
  'fmt.coordinate(point.row.elevation, settings.output_unit),'

M "M12 build_report pathless guard deleted" michspc/fileio/report.py \
  'if settings.input_path is None or settings.output_directory is None:' \
  'if False:'

M "M13 copy_value copies the LABEL not the value" michspc/gui/single_point.py \
  'self._set_clipboard(self.panel.values[index].text)' \
  'self._set_clipboard(self.panel.values[index].label)'

M "M14 warnings row dropped from zone_to_geodetic OUTPUT" michspc/gui/results_model.py \
  'ResultValue(UNITS_LABEL, _units_text(settings.output_unit)),
                warnings,' \
  'ResultValue(UNITS_LABEL, _units_text(settings.output_unit)),'

M "M15 typed point id becomes empty-ish" michspc/fileio/pnezd.py \
  'TYPED_POINT_ID = "1"' \
  'TYPED_POINT_ID = "P"'

M "M16 archive_path pathless guard deleted" michspc/fileio/exports.py \
  'if result.settings.output_directory is None:' \
  'if False:'
