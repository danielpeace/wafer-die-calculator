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

## Linting

```bash
python3 -m pip install ruff
ruff check wafer_calculator.py
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

## Feedback (Slack/Discord)

If `FEEDBACK_WEBHOOK_URL` is set, feedback submissions are sent to that webhook.
Otherwise they are written to `FEEDBACK_PATH` (default: `/tmp/feedback.jsonl`).

Example for Render:
- Add environment variable `FEEDBACK_WEBHOOK_URL` with your Slack/Discord webhook URL.
- Optional: set `FEEDBACK_PATH` if you want file output on a writable path.

Spam protection:
- Basic rate limit: 10 submissions/minute per IP
- Hidden honeypot field rejects bot submissions
