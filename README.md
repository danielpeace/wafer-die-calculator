# Wafer Die Calculator

Web-based GUI for calculating dies per wafer with symmetrical placement, SEMI standards, and GDSII export.

## Features
- Centered symmetrical die placement
- SEMI standard wafer sizes (flat/notch)
- Zoomable/pannable canvas view
- GDSII + PNG export
- Optional partial die inclusion
- Layer/datatype configuration with KLayout `.lyp` import

## Run locally

```bash
python3 wafer_calculator.py
```

Open: http://localhost:5000

## Tests

```bash
python3 tests.py
```

## Deploy to Render

This repo includes a `render.yaml` and respects `PORT`.

1. Push to GitHub
2. Render: **New > Web Service**
3. Select the repo
4. Render will pick up `render.yaml` automatically

Start command:
```bash
python3 wafer_calculator.py
```

## Notes
- Browser controls the save location for downloads. The filename box sets the download name.
- GDS layer numbers/datatype can be edited in the Layer Visibility panel.
