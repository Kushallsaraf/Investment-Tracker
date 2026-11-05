<!-- Placeholder. Replace this file with your own analysis prompt; {ticker} is filled in. -->
Analyze {ticker} using the Investment Tracker tools. Use only the data the tools return, and
cite the as-of date for each figure. If a value is NOT AVAILABLE, say so; do not estimate it.

1. get_quote and get_chart_summary: the price, trend, and technical setup.
2. get_fundamentals and get_peers: valuation against its own history and against peers.
3. get_insider_activity: what insiders have done in the last 90 days.
4. get_news_sentiment: recent headlines, their sentiment trend, and any 8-K filings.
5. get_my_notes and get_position: what I have already written and decided.

Then give a short bull case and bear case, and list what would change your view.

Finish by asking whether I want you to save an exit plan (target, stop, and review date with
your reasoning) using save_exit_plan. It is saved as a proposal I review in the dashboard.
