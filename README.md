# Bus delay risk in Luxembourg

This project predicts whether a bus stop event in Luxembourg will be delayed, using data collected directly from a public-transport API. It compares a logistic regression baseline against tree-based models and ends with a Random Forest that flags high-risk stop events for operations teams.

## Data

The data covers roughly 7 to 8 weeks, from 25 July to 16 September 2025, and contains about 7.4 million stop events. It was collected with a small set of Python scripts that poll a public-transport API at regular intervals and store the results in a local SQLite database. From there, a SQL-to-CSV step produces one clean dataset that both the EDA and the modeling notebooks reuse, so every chart and every model in this project comes from the same source of truth.

The modeling table has 13 features. Every one of them is leakage-safe: it only uses information that is known before the bus arrives at the stop (route, stop, time of day, weekday, weather, and similar). Delays are not rare in this data: about 36% of stop events are delayed, so accuracy is a misleading metric here. The project is scored on F1 instead.

Only public transport operators are named in the data and in this repo (for example AVL and TICE). No employer names, personal data, API URLs, or API keys are included anywhere.

## Project structure

```
bus-delay-risk-luxembourg/
├── data/
│   ├── bus_delays_sample.csv        # full raw export, not included in this repo
│   ├── df_model_delay.csv           # full modeling table, not included in this repo
│   └── sample/
│       ├── bus_delays_sample_small.csv   # small public sample, same class balance
│       └── weather_lux_hourly_2025-08-17_2025-09-16.csv
├── notebooks/
│   ├── 01_data_understanding.ipynb  # loads from the private SQLite database
│   ├── 02_eda_delay.ipynb           # exploratory analysis, builds the modeling table
│   ├── 03_model_delay.ipynb         # logistic regression, Random Forest, evaluation
│   ├── 04_weather_download.ipynb    # pulls hourly weather from Open-Meteo
│   └── Slides.ipynb                 # generates the charts used in the deck
├── src/
│   ├── collect_realtime.py          # fetches live departures from the transport API
│   └── collect_gtfs.py              # downloads and imports the public GTFS feed
├── outputs/
│   ├── figures/                     # chart HTML files used in the deck
│   └── deck/                        # the presentation deck and its assets
├── README.md
├── LICENSE
├── requirements.txt
├── .env.example
└── .gitignore
```

`data/bus_delays_sample.csv` and `data/df_model_delay.csv` hold the full collected data and are not part of this repo. They stay on the author's machine. `data/sample/` has a small public stand-in instead.

## How to run

```bash
git clone <this-repo-url>
cd bus-delay-risk-luxembourg
pip install -r requirements.txt
```

Then open the notebooks in order with Jupyter:

```bash
jupyter lab notebooks/
```

`01_data_understanding.ipynb` needs the private, cleaned SQLite database (`transport_data_clean.db`), described above in the Data section, and will not run without it. To follow the rest of the pipeline (notebooks 02 to 04 and `Slides.ipynb`), point the data paths at `data/sample/bus_delays_sample_small.csv` instead of the full raw file. The sample keeps the same class balance, about 36% delayed and 64% on-time, but it is a few thousand rows, not 7.4 million. It is there so you can run and read the code, not to reproduce the headline result below.

`src/collect_realtime.py` needs `HAFAS_ACCESS_ID` and `HAFAS_BASE_URL` environment variables. The base URL is not hardcoded in this repo, pending confirmation of whether HAFAS's terms of service allow publishing it. Copy `.env.example` to `.env` and fill in your own values; both `src/collect_realtime.py` and `src/collect_gtfs.py` load `.env` automatically. `src/collect_gtfs.py` only calls a public, keyless feed, so it runs without any env vars set.

## Results

A Random Forest outperformed the logistic regression baseline. At a decision threshold of about 0.46, it catches roughly 83% of real delays. The output is a simple green, yellow, red alert list, meant to be rolled out gradually: first as a shadow run alongside current operations, then a pilot with a limited group, then a full rollout if it holds up.

Charts for class balance, delay patterns by hour and route, and model evaluation (confusion matrix, ROC, precision-recall, feature importance) are in `outputs/figures/`. The full deck, with narration, is in `outputs/deck/index_tv.html`, with a printable version in `outputs/deck/bus_delays_lux.pdf`. To rebuild the PNG export and PDF with `outputs/deck/export_slides.py`, install Playwright's browser binaries first with `playwright install chromium`.

### Where this can't be trusted yet

This model has two real limits, and they matter more than any chart:

- **No real-time signals.** There is no live traffic, GPS, or AVL data feeding the model. It cannot see an accident or a breakdown happening right now, only the patterns that tend to surround delays.
- **Short collection window.** The data spans about 7 to 8 weeks. That is not enough to see a full year of seasonality, so the model's behavior outside this window is untested.

There is also a gap in the pipeline worth being upfront about: the step that turned the raw collected database into the cleaned database used by the notebooks was a manual SQL pass, not a saved script. The collection scripts in `src/` are real and reusable, but that cleaning step would need to be rebuilt and scripted to fully automate the pipeline end to end.

Given these limits, the practical use of this model is as a support tool for operations teams, not a replacement for real-time monitoring. Retraining on a longer window, and adding real-time traffic or GPS/AVL data, are the most useful next steps.

## Tech

Python, pandas, scikit-learn, SQL.
