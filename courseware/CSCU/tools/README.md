# tools — Word-guide builder

`build-docx.py` regenerates every CSCU workshop and Technical-Track `.docx`
from its markdown guide master, in the course design (cover block, styled
tables, restarting step numbering, callouts, embedded diagrams). Each
`[SCREENSHOT: ...]` marker in the markdown becomes an amber placeholder box —
replace those with real captures in Word.

```powershell
python build-docx.py     # rebuilds all guides in place (requires pillow)
```

The markdown masters remain the authoritative source: edit the `.md`,
re-run the builder, re-paste screenshots. `template.docx` carries the course
styles, numbering, header and footer; per-document cover text and header
titles are configured in the `DOCS` list at the bottom of the script.
