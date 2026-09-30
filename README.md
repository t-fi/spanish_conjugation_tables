# Spanish conjugation project

Conjugation tables for Latin American Spanish (no `vosotros`), usable both online and directly in a local browser.

[Website](https://t-fi.github.io/spanish_conjugation_tables/) · [Regular endings](spanish-conjugation-chart.html) · [Core patterns](spanish-conjugation-cores.html) · [Irregular families](spanish-irregular-verbs/index.html)

- `spanish-conjugation-chart.html` — regular endings chart
- `spanish-conjugation-cores.html` — compact repeated-core overview without person rows
- `spanish-irregular-verbs/index.html` — irregular-family atlas
- `spanish-irregular-verbs/generate.py` — deterministic atlas generator
- `spanish-irregular-verbs/verify.py` — structural and linguistic checks
- `spanish-irregular-verbs/atlas-data.json` — generated paradigms for all indexed family members

Open `index.html` directly with a browser to choose a chart; no server or build step is required.

To regenerate and verify the atlas:

```sh
python3 spanish-irregular-verbs/generate.py
python3 spanish-irregular-verbs/verify.py
```

Run these commands from the project root and commit the regenerated HTML and data together.

GitHub Pages uses the workflow in `.github/workflows/pages.yml`. Set **Settings → Pages → Source** to **GitHub Actions** once; subsequent pushes to `main` verify the atlas and deploy the static HTML. Pull requests run verification without deploying. The published artifact contains only the HTML pages and `.nojekyll`.
