# Task 1 Report: Enhance AnalyzerAgent Structured Metrics Extraction

## What Was Implemented

Enhanced the `StructuredMetric` schema and `AnalyzerAgent` to extract richer structured metrics with time granularity and comparison data.

### Schema Changes (`backend/app/schemas/agent.py`)

Added three new fields to `StructuredMetric`:
- `period_granularity: str = ""` — time granularity of data points (year/quarter/month/week)
- `yoy_data: Optional[List[MetricDataPoint]] = None` — year-over-year comparison data
- `qoq_data: Optional[List[MetricDataPoint]] = None` — quarter-over-quarter comparison data

All fields are optional with backward-compatible defaults.

### Analyzer Changes (`backend/app/agents/analyzer.py`)

- **`_build_prompt`**: Updated prompt instructions to request `period_granularity`, `yoy_data`, and `qoq_data` from the LLM. Added JSON example showing the new fields.
- **`_parse_structured_metrics`**: Extended to parse the three new fields from raw LLM output. Validates `period_granularity` against allowed values (falls back to empty string). Requires `yoy_data`/`qoq_data` to have >= 2 data points (otherwise set to None).

### Test File (`backend/test_analyzer_metrics.py`)

20 tests covering:
- `MetricDataPoint` basic construction
- `period_granularity` for all valid values + default + invalid fallback
- `yoy_data` and `qoq_data` defaults, with data, insufficient points rejection
- Full object construction with all fields
- Backward compatibility (no new fields = defaults)
- `_parse_structured_metrics` integration tests for all new fields

## Test Results

All 20 tests passed in 0.88s.

## Files Changed

1. `backend/app/schemas/agent.py` — added 3 fields to `StructuredMetric`
2. `backend/app/agents/analyzer.py` — updated `_build_prompt` and `_parse_structured_metrics`
3. `backend/test_analyzer_metrics.py` — new test file (20 tests)

## Self-Review Findings

- The `_parse_structured_metrics` enforces >= 2 data points for `yoy_data`/`qoq_data` to ensure chartability. This is consistent with the existing `data_points` minimum.
- Invalid `period_granularity` values fall back to empty string rather than raising, matching the defensive parsing pattern used for `metric_type` and `chart_type_hint`.
- No changes to `_extract_metrics_from_text` (regex fallback) since it doesn't produce comparison data.

## Issues or Concerns

None. All changes are backward-compatible — existing consumers of `StructuredMetric` will see empty/default values for the new fields.
