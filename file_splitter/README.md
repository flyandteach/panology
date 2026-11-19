# File Splitter

Splits large documents into multiple files that are each **under 10 MB**. It
splits on the document's own structure where it can, so every part opens
normally on its own.

| File type | How it is split | Each part is… |
|---|---|---|
| `.pdf` | By page | a normal PDF with a range of pages |
| `.docx`, `.docm` | By paragraph/table (top-level blocks) | a Word file with the same styles, headers and footers, and only the images it uses |
| `.pptx`, `.pptm` | By slide | a PowerPoint file with the same masters/theme, and only the media its slides use |
| `.csv`, `.tsv` | By row; the header row is repeated in every part; quoted fields that contain line breaks are never cut | a valid CSV |
| `.txt`, `.md`, `.log`, `.jsonl`, `.sql`, … | By line | a text file |
| Anything else (`.zip`, `.xlsx`, video, …) | Raw bytes | **not** openable alone; rejoin with `join` |

The size is checked by actually writing each part, so the limit is exact, not
an estimate. "10MB" means 10,000,000 bytes, which is below 10 MiB too, so the
parts satisfy either definition. Each part is kept strictly smaller than the limit.

## Install

```bash
pip install -r file_splitter/requirements.txt
```

Needs Python 3.9+, `pypdf` and `lxml`. Run the commands from the repository root.

## Split files

```bash
python -m file_splitter split path/to/big.pdf
```

Parts go to `path/to/big_split/` as `big_part01of06.pdf`, `big_part02of06.pdf`,
…, plus `big.pdf.manifest.json`, which lists every part with its size and
SHA-256 checksum.

More examples:

```bash
# Several files, or a whole folder (add -r to include subfolders), into one output folder
python -m file_splitter split report.pdf manual.docx data.csv -o split_output
python -m file_splitter split ~/Documents/to_send -r -o split_output

# A different limit, e.g. for an email system that caps attachments at 8 MB
python -m file_splitter split big.pdf --max-size 8MB

# Force a strategy, e.g. treat a .dat export as text with 2 header lines
python -m file_splitter split export.dat --mode text --header-lines 2
```

Files already under the limit are skipped (use `--force` to process them anyway).

## Automate: watch a folder

Drop files into an inbox folder and they are split automatically:

```bash
python -m file_splitter watch inbox outbox
```

* Every 5 seconds (`--interval`) it scans `inbox/`. A file is processed only
  once its size has stopped changing, so files still being copied are not
  touched.
* Parts for `inbox/report.pdf` go to `outbox/report/` (or straight into
  `outbox/` with `--flat`). Files already under the limit are copied there unchanged.
* The original moves to `inbox/_processed/` on success or `inbox/_failed/` on error.

To run it on a schedule instead of continuously (cron, Task Scheduler, CI),
use `--once`, which processes whatever is in the inbox and exits:

```bash
python -m file_splitter watch inbox outbox --once
```

## Rejoin byte-split files

Files split as raw bytes (`report.zip.part001`, `.part002`, …) are put back with:

```bash
python -m file_splitter join split_output/report.zip.part* -o report.zip
```

`cat report.zip.part* > report.zip` (macOS/Linux) or
`copy /b report.zip.part001+report.zip.part002 report.zip` (Windows) also work.
Compare the result with `source_sha256` in the manifest to confirm it is identical.

## Limits

* A single page, slide or paragraph that is itself over the limit (for
  example, one huge photo) can't be made smaller by splitting. It is written
  to its own part, flagged `OVER LIMIT` in the output, and the command exits
  with status 1. Compress that image and run the splitter again.
* Password-protected PDFs must be decrypted first.
* Excel (`.xlsx`) files fall back to byte splitting. Export the sheet to CSV
  first if you need parts that open on their own.
* Word parts each start a new file mid-document, so automatic numbering,
  tables of contents and cross-references only cover the content in that
  part. Footnotes, comments and styles are kept in every part.
* PowerPoint hyperlinks that jump to a slide in a *different* part are not
  handled (this case hasn't been tested); PowerPoint may offer to repair that part.

## Tests

```bash
python -m pytest file_splitter/tests
```

The tests generate PDF, Word, PowerPoint, CSV, text and binary files and check
that every part is under the limit, opens on its own, and that no content is
lost or duplicated. The PowerPoint and Word tests need `python-pptx` and
`python-docx`, and the PDF test needs `reportlab`; each is skipped if missing.
