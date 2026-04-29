# Eval Datasets

Datasets store compact, high-signal behavior cases.

Each case should include:
- stable `id`,
- input fixture references or inline input,
- expected classification,
- expected primary root-cause file/line when applicable,
- expected evidence behavior,
- known failure modes,
- `must_pass` flag.

Use real failures first, then constrained synthetic cases for coverage gaps.
