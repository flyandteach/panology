You are producing a research-article summary for the AMRG (Advanced Mobility
Research Group) literature watch, following the AMRG project template
exactly. Use ONLY the article text and figure list provided below -- do not
invent authors, affiliations, venues, findings, or figures that are not
present in the source.

TOPIC AREA FOR THIS SEARCH: {TOPIC_AREA}

ARTICLE FULL TEXT (extracted from the downloaded PDF; may include OCR/layout
artifacts -- read past them):
{ARTICLE_TEXT}

EXTRACTED FIGURES (filename, source page, and any caption text found near it
on that page -- reference these by number in the Summary where relevant,
e.g. "(see Figure 2)"; number them in reading order starting at 1):
{FIGURE_LIST}

SCHOLAR METADATA (use to cross-check/fill gaps, but prefer the article text
itself when they conflict):
{SCHOLAR_METADATA}

---

Produce the summary in Markdown using EXACTLY this structure and these
section headings:

## What?
Describe the subject area of the article and some basics about the study --
an overview/summary of the article's abstract.

## Who?
List the authors and their listed affiliations/employers/schools. If an
affiliation isn't stated in the text, write "not stated in article" rather
than guessing.

## Where?
The publication name in italics (e.g. *Journal of Air Transportation*), and
a link to the article (use the Scholar URL provided in metadata, or the DOI
if present in the text).

## Summary
A paragraph-form summary (no bulleted lists inside this section) covering
the literature review, method/design, and results. Follow it with a
"**Key Takeaways**" bulleted list of practical-application takeaways from
the study.

## Keywords
A comma-separated list of keywords, each prefixed with `#` (e.g.
`#eVTOL, #vertiport-design, #urban-air-mobility`).

Do not include a writing-quality score, fact-check, or references section --
those are computed separately and appended by the pipeline. Return only the
Markdown for the sections above.
