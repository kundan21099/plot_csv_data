import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dash import Dash, dcc, html, Input, Output
import plotly.graph_objs as go

# ------------------------------------------------------------
# 1. LOAD RAW DATA
# ------------------------------------------------------------
raw_path = "Raw_Data.csv"   # <-- adapt if needed
df = pd.read_csv(raw_path)

# Column names should contain something like:
# Time (s), Gyroscope x (rad/s), Gyroscope y (rad/s), Gyroscope z (rad/s), Absolute (rad/s)

# Normalize column names
df.columns = [c.strip() for c in df.columns]

# ------------------------------------------------------------
# 2. META DATA (from user text)
# ------------------------------------------------------------

start_system_time = 1764846926.548
pause_system_time = 1764846935.845

# Convert UNIX timestamps to datetime
start_dt = datetime.utcfromtimestamp(start_system_time)
pause_dt = datetime.utcfromtimestamp(pause_system_time)

# ------------------------------------------------------------
# 3. BUILD TRUE TIMESTAMPS
# ------------------------------------------------------------
df["true_time"] = df["Time (s)"].apply(lambda x: start_dt + timedelta(seconds=float(x)))

# Verification check
computed_end_time = df["true_time"].iloc[-1]
print("Start time:", start_dt)
print("Computed last time:", computed_end_time)
print("Pause time:", pause_dt)
print("Difference sec:", (pause_dt - computed_end_time).total_seconds())

# ------------------------------------------------------------
# 4. Compute statistics
# ------------------------------------------------------------
gyro_cols = [
    'Gyroscope x (rad/s)',
    'Gyroscope y (rad/s)',
    'Gyroscope z (rad/s)',
    'Absolute (rad/s)'
]

stats = df[gyro_cols].agg(['mean', 'std'])

print("\n=== Stats ===")
print(stats)

# ------------------------------------------------------------
# 5. DASH APP
# ------------------------------------------------------------
app = Dash(__name__)

app.layout = html.Div([
    html.H1("Gyroscope Data Visualization"),

    html.Div("Trim time range (seconds):"),
    html.Div(id="slider-values", style={"margin-bottom": "20px"}),
    dcc.RangeSlider(
        id='trim-slider',
        min=0,
        max=df["Time (s)"].max(),
        value=[0, df["Time (s)"].max()],
        step=0.01,
        allowCross=False,
        tooltip={"always_visible": True, "placement": "bottom"},
        marks=None   # Remove clutter for large datasets
    ),

    dcc.Graph(id='gyro-plot'),

    html.H3("Statistics"),
    html.Pre(id="stats-output")
])


@app.callback(
    [Output("gyro-plot", "figure"), Output("stats-output", "children"), Output("slider-values", "children")],
    [Input("trim-slider", "value")]
)
def update_plot(trim_range):

    tmin, tmax = trim_range
    dff = df[(df["Time (s)"] >= tmin) & (df["Time (s)"] <= tmax)]

    fig = go.Figure()

    # Add gyro traces
    for col in gyro_cols:
        fig.add_trace(go.Scatter(
            x=dff["true_time"],
            y=dff[col],
            mode='lines',
            name=col
        ))

        # Add mean line
        fig.add_trace(go.Scatter(
            x=dff["true_time"],
            y=[dff[col].mean()] * len(dff),
            mode='lines',
            name=f"{col} mean",
            line=dict(dash='dash'),
            visible='legendonly'
        ))

        # Add STD band (±1σ)
        fig.add_trace(go.Scatter(
            x=dff["true_time"],
            y=[dff[col].mean() + dff[col].std()] * len(dff),
            mode='lines',
            name=f"{col} +1σ",
            line=dict(dash='dot'),
            visible='legendonly'
        ))

        fig.add_trace(go.Scatter(
            x=dff["true_time"],
            y=[dff[col].mean() - dff[col].std()] * len(dff),
            mode='lines',
            name=f"{col} -1σ",
            line=dict(dash='dot'),
            visible='legendonly'
        ))

    fig.update_layout(
        title="Gyroscope Measurements",
        xaxis_title="Time (True Timestamp)",
        yaxis_title="Angular Velocity (rad/s)",
        hovermode="x unified"
    )

    # Updated stats
    stats_text = dff[gyro_cols].agg(['mean', 'std']).to_string()
    slider_text = f"Start: {tmin:.3f} s   |   End: {tmax:.3f} s   |   Window: {tmax - tmin:.3f} s"
    return fig, stats_text, slider_text


if __name__ == "__main__":
    app.run(debug=True)
