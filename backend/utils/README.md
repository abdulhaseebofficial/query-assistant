# backend/utils/

Small, general-purpose helper code that doesn't belong to any one specific feature lives here.

## What's in this folder

| File | What it does |
|---|---|
| `chart_utils.py` | Looks at a query's results and figures out whether they can be drawn as a chart. If they can, it picks which column should be the numbers (the values) and which should be the labels, and hands back a simple bundle of data that the chart drawing code (`frontend/templates/partials/_chart.html`) uses to draw a bar, line, or pie chart. |
