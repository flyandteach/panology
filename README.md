# Aviation Futures Intelligence Agent

A beginner-friendly Streamlit app for tracking aviation technology, infrastructure, policy, and market signals.

## What it does

- Stores aviation futures topics in a watchlist
- Scores each topic by signal strength and confidence
- Classifies items as High, Medium, or Low priority
- Generates a downloadable Markdown report
- Runs locally or on Streamlit Community Cloud

## Local setup

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the app:

```bash
python -m streamlit run app.py
```

## Streamlit Cloud deployment

1. Create a public GitHub repository.
2. Upload `app.py`, `requirements.txt`, `README.md`, and the `data` folder.
3. Go to Streamlit Community Cloud.
4. Select the repository.
5. Set the main file path to `app.py`.
6. Deploy.

## Important limitation

This MVP does not automatically browse the web or verify current facts. It is a manual intelligence-tracking and reporting tool.
