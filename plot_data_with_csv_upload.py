import base64
import io
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objs as go
from zoneinfo import ZoneInfo
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
    html.H1("Data Viewer"),
    html.Div([
        # Raw Data Upload
        html.Div([
            html.H3("Upload Raw Data CSV"),
            dcc.Upload(
                id="upload-raw",
                children=html.Div(["Drag & Drop or Click to Select RAW CSV"]),
                style={
                    "width": "100%",
                    "height": "60px",
                    "lineHeight": "60px",
                    "borderWidth": "1px",
                    "borderStyle": "dashed",
                    "textAlign": "center"
                }
            )
        ], style={"flex": "1", "margin-right": "10px"}),

        # Meta Data Upload
        html.Div([
            html.H3("Upload Metadata CSV (time info)"),
            dcc.Upload(
                id="upload-meta",
                children=html.Div(["Drag & Drop or Click to Select META CSV"]),
                style={
                    "width": "100%",
                    "height": "60px",
                    "lineHeight": "60px",
                    "borderWidth": "1px",
                    "borderStyle": "dashed",
                    "textAlign": "center"
                }
            )
        ], style={"flex": "1", "margin-left": "10px"}),

    ], style={"display": "flex", "flex-direction": "row", "width": "100%"}),

    html.Hr(),

    html.Div(id="file-status", style={"font-weight": "bold", "color": "#333"}),

    html.H4("Selected Time Range (seconds):"),
    html.Div(id="slider-values", style={"margin-bottom": "20px"}),

    dcc.RangeSlider(
        id='trim-slider',
        min=0, max=1,
        value=[0, 1],
        step=0.1,
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

    start_dt = datetime.fromtimestamp(start_system_time, ZoneInfo("Europe/Berlin"))
    pause_dt = datetime.fromtimestamp(pause_system_time, ZoneInfo("Europe/Berlin"))

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
    # Determine measurement type
    # ------------------------------------    
    measurement_type = "Unknown"
    y_axis_title = "NA"
    if dff.columns[1].lower().startswith("gyro"):
        measurement_type = "Gyroscope"
        y_axis_title = "Angular Velocity (rad/s)"
    elif dff.columns[1].lower().startswith("accel"):
        measurement_type = "Accelerometer"
        y_axis_title = "Acceleration (m/s²)"


    # ------------------------------------
    # Build plot
    # ------------------------------------
    fig = go.Figure()

    if(measurement_type=="Gyroscope"):
        wx = np.array(dff["Gyroscope x (rad/s)"])  # rad/s
        wy = np.array(dff["Gyroscope y (rad/s)"])
        wz = np.array(dff["Gyroscope z (rad/s)" ])
        # 1) magnitude
        w_mag = np.sqrt(wx**2 + wy**2 + wz**2)

        # 2) integrate each component to get angle (trapezoidal integration)
        angle_x = np.zeros_like(wx)
        angle_y = np.zeros_like(wy)
        angle_z = np.zeros_like(wz)
        for i in range(1, len(dff["Time (s)"])):
            dt = dff["Time (s)"].iloc[i] - dff["Time (s)"].iloc[i-1]
            angle_x[i] = angle_x[i-1] + 0.5*(wx[i-1] + wx[i])*dt
            angle_y[i] = angle_y[i-1] + 0.5*(wy[i-1] + wy[i])*dt
            angle_z[i] = angle_z[i-1] + 0.5*(wz[i-1] + wz[i])*dt

        angle_mag = np.sqrt(angle_x**2 + angle_y**2 + angle_z**2)
        # Add angle data to dff for plotting
        dff["Angle x (rad)"] = angle_x
        dff["Angle y (rad)"] = angle_y  
        dff["Angle z (rad)"] = angle_z
        dff["Angle magnitude (rad)"] = angle_mag

    data_cols = list() 
    for col in dff.columns:
        if not "time" in col.lower():
            data_cols.append(col)

    for col in data_cols:
        if col in dff.columns:
            fig.add_trace(go.Scatter(
                x=dff["true_time"],
                y=dff[col],
                mode="lines",
                name=col
            ))
        if col.lower().startswith("absolute"):
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
        title=f"{measurement_type} Measurements",
        xaxis_title="Time",
        yaxis_title=y_axis_title,
        hovermode="x unified"
    )

    # ------------------------------------
    # Stats
    # ------------------------------------
    stats_text = dff[data_cols].agg(['mean', 'std']).to_string()

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
