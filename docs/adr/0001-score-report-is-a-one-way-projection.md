# The score report is a one-way projection of the assessment record

The score report used to carry a `Machine Summary` YAML block that made up about 78% of each report, and several modules scraped data back out of the report prose with regexes that matched fewer than 5% of real reports. We decided the report is written only for the candidate to read: code renders it from structured fields, nothing ever parses it, and every value a program needs (dimension scores, research findings, recommendation, provenance hashes, advertised compensation) lives in the assessment record. The model returns structured fields rather than Markdown, so layout is fixed by the renderer.

The hash of the whole report text stays, held outside the report, because it proves that the stored report, the file on disk and the delivered notification are the same document.

## Considered Options

- **Keep the machine block, collapsed at the end.** Rejected: it kept two copies of the same data and left the report format coupled to its parsers.
- **A sidecar provenance file next to the report.** Rejected: the assessment record already exists and already held everything except the input hashes.
