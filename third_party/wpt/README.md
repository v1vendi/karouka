# The vendored WPT subset

A subset of [web-platform-tests](https://github.com/web-platform-tests/wpt), copied byte for byte
at the upstream commit in [`WPT_COMMIT`](WPT_COMMIT). The files keep their upstream license:
[`LICENSE.md`](LICENSE.md) (3-Clause BSD, web-platform-tests contributors).

**This directory is the subset.** Nothing is filtered again at run time: adding or removing a test
is a reviewable diff to this tree. The runners apply only a document-shape rule:

- `tools/wpt.py` (the reftest suite) runs every `.html`/`.htm`/`.xht`/`.xhtml` file outside a
  `support/` or `reference/` directory that carries a `<link rel="match">` or `<link rel="mismatch">`.
  Ratchet: `tests/wpt/known_failures.txt`.
- `tools/wpt_dom.py` (the testharness.js suite) runs the documents under `dom/nodes/`,
  `css/css-scroll-snap/`, `css/cssom-view/`, `html/dom/elements/the-innertext-and-outertext-properties/`,
  `html/semantics/scripting-1/` and `css/css-transforms/transform-hit-testing.html`, scored per
  subtest. Ratchet: `tests/wpt/known_failures_dom.txt`.

Both run through `tools/dev.sh wpt`; see `tools/wpt.py`'s docstring for the rules.

`tests/wpt/corpus.pin` records the git tree hash of this directory. `tools/wpt_vendor.sh --check`
(run by `tools/dev.sh check`) verifies the committed tree matches it; any edit here, this file
included, needs the pin updated in the same commit.
