import base64
import io
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objs as go

# -------------------------------------------------------------------
# Helper: decode uploaded file
# -------------------------------------------------------------------
def parse_contents(contents):
    content_type, content_string = contents.split(',')
    decoded_bytes = base64.b64decode(content_string)      # bytes
    decoded_str = decoded_bytes.decode('utf-8', errors='ignore')   # string

    # Auto-detect separator from first line
    first_line = decoded_str.split("\n")[0]
    sep = ";" if ";" in first_line else ","

    # Pass string to StringIO
    return pd.read_csv(io.StringIO(decoded_str), sep=sep)

# -------------------------------------------------------------------
# DASH APP
# -------------------------------------------------------------------
app = Dash(__name__)

app.layout = html.Div([
    html.H1("Gyroscope Data Viewer"),

    html.H3("Upload Gyroscope Raw Data CSV"),
    dcc.Upload(
        id="upload-raw",
        children=html.Div(["Drag & Drop or Click to Select RAW CSV"]),
        style={
            "width": "60%", "height": "60px", "lineHeight": "60px",
            "borderWidth": "1px", "borderStyle": "dashed",
            "textAlign": "center"
        }
    ),

    html.H3("Upload Metadata CSV (START / PAUSE)"),
    dcc.Upload(
        id="upload-meta",
        children=html.Div(["Drag & Drop or Click to Select META CSV"]),
        style={
            "width": "60%", "height": "60px", "lineHeight": "60px",
            "borderWidth": "1px", "borderStyle": "dashed",
            "textAlign": "center"
        }
    ),

    html.Hr(),

    html.Div(id="file-status", style={"font-weight": "bold", "color": "#333"}),

    html.H4("Selected Time Range (seconds):"),
    html.Div(id="slider-values", style={"margin-bottom": "20px"}),

    dcc.RangeSlider(
        id='trim-slider',
        min=0, max=1,
        value=[0, 1],
        step=0.01,
        allowCross=False,
        tooltip={"always_visible": True, "placement": "bottom"},
        marks=None,
    ),

    dcc.Graph(id='gyro-plot'),

    html.H3("Statistics"),
    html.Pre(id="stats-output")
])


# -------------------------------------------------------------------
# CALLBACK: Process CSV files and update plot
# -------------------------------------------------------------------
@app.callback(
    [
        Output("gyro-plot", "figure"),
        Output("stats-output", "children"),
        Output("slider-values", "children"),
        Output("trim-slider", "min"),
        Output("trim-slider", "max"),
        Output("trim-slider", "value"),
        Output("file-status", "children")
    ],
    [
        Input("trim-slider", "value"),
        Input("upload-raw", "contents"),
        Input("upload-meta", "contents")
    ],
    [
        State("upload-raw", "filename"),
        State("upload-meta", "filename")
    ]
)
def update_all(trim_range, raw_contents, meta_contents, raw_name, meta_name):
    print("Callback triggered, trim_range:", trim_range)
    # -------------------------------
    # No files uploaded yet
    # -------------------------------
    if raw_contents is None or meta_contents is None:
        fig = go.Figure()
        fig.update_layout(title="Upload Both CSV Files To Begin")
        return (
            fig, "No data loaded.", "", 0, 1, [0, 1],
            "Please upload BOTH raw and meta CSV files."
        )

    # -------------------------------
    # Parse files
    # -------------------------------
    try:
        df_raw = parse_contents(raw_contents)
        df_meta = parse_contents(meta_contents)
    except Exception as e:
        fig = go.Figure()
        return (
            fig,
            "Error reading files.",
            "",
            0, 1, [0, 1],
            f"Error: {str(e)}"
        )

    # Normalize raw column names
    df_raw.columns = [c.strip() for c in df_raw.columns]

    # ------------------------------------
    # Extract metadata START & PAUSE times
    # ------------------------------------
    df_meta.columns = [c.strip(";") for c in df_meta.columns]
    try:
        start_system_time = float(df_meta.iloc[0]["system time"])
        pause_system_time = float(df_meta.iloc[1]["system time"])
    except Exception as e:
        fig = go.Figure()
        return (
            fig,
            "Invalid META file format.",
            "",
            0, 1, [0, 1],
            f"Meta file error: {e}"
        )

    # Convert UNIX → datetime
    start_dt = datetime.fromtimestamp(start_system_time)
    pause_dt = datetime.fromtimestamp(pause_system_time)

    # ------------------------------------
    # Build true timestamps
    # ------------------------------------
    if "Time (s)" not in df_raw.columns:
        fig = go.Figure()
        return (
            fig,
            "Missing 'Time (s)' in raw data.",
            "",
            0, 1, [0, 1],
            "RAW file missing required column."
        )

    df_raw["true_time"] = df_raw["Time (s)"].apply(
        lambda x: start_dt + timedelta(seconds=float(x))
    )

    # ------------------------------------
    # Slider bounds
    # ------------------------------------
    t_min = 0
    t_max = float(df_raw["Time (s)"].max())

    if trim_range is None:
        trim_range = [0, t_max]

    tmin, tmax = trim_range
    print("Before bounds check tmin:", tmin, "tmax:", tmax, "trim_range:", trim_range)
    # Ensure slider stays in range
    tmin = max(0, tmin)
    tmax = min(t_max, tmax)

    # ------------------------------------
    # Slice data for trimmed interval
    # ------------------------------------
    dff = df_raw[(df_raw["Time (s)"] >= tmin) & (df_raw["Time (s)"] <= tmax)]

    # ------------------------------------
    # Build plot
    # ------------------------------------
    fig = go.Figure()
    gyro_cols = [
        'Gyroscope x (rad/s)',
        'Gyroscope y (rad/s)',
        'Gyroscope z (rad/s)',
        'Absolute (rad/s)'
    ]

    for col in gyro_cols:
        if col in dff.columns:
            fig.add_trace(go.Scatter(
                x=dff["true_time"],
                y=dff[col],
                mode="lines",
                name=col
            ))

    fig.update_layout(
        title="Gyroscope Measurements",
        xaxis_title="True Time",
        yaxis_title="Angular Velocity (rad/s)",
        hovermode="x unified"
    )

    # ------------------------------------
    # Stats
    # ------------------------------------
    stats_text = dff[gyro_cols].agg(['mean', 'std']).to_string()

    # ------------------------------------
    # Slider text
    # ------------------------------------
    slider_text = (
        f"Start: {tmin:.3f} s   |   End: {tmax:.3f} s   |   Window: {tmax - tmin:.3f} s"
    )

    # ------------------------------------
    # Status
    # ------------------------------------
    status = f"Loaded RAW: {raw_name}   |   META: {meta_name}"
    print("at the end tmin:", tmin, "tmax:", tmax, "trim_range:", trim_range, "t_min", t_min, "t_max", t_max)
    return (
        fig,
        stats_text,
        slider_text,
        t_min,
        t_max,
        [tmin, tmax],
        status
    )

if __name__ == "__main__":
    app.run(debug=True)
