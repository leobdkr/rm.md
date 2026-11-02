# md2rmdoc

Markdown → `.rmdoc` for the reMarkable Paper Pro. Renders the md to a PDF sized
to the screen, then wraps it in the zip layout xochitl expects.

```
./md2rmdoc.py notes.md                        # -> notes.rmdoc
./md2rmdoc.py notes.md -n "Nice Title" -o out.rmdoc
./md2rmdoc.py notes.md -- --toc -V mainfont=Palatino
```

## Needs

pandoc, xelatex, and `sudo tlmgr install fvextra hyphenat`. Without those two
packages it should work, but long lines in code blocks and long `inline_code` get cut off at the
page edge. The script detects them and degrades quietly, so check them first if
text goes missing.

## Defaults

Charter 12pt, page 179.7×239.6mm (the Paper Pro's 1620×2160 @ 229dpi), margins
`left=14mm,right=30mm`. The wide right side is a gutter to write in. Works out
to ~71 characters per line.

Anything after `--` goes to pandoc and overrides the defaults; `--paper`,
`--margin`, `--font-size` and `--pdf-engine` are there for the common tweaks.
Font sizes above 12pt need `-- -V documentclass=extarticle`.
