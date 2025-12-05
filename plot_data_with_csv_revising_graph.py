import base64
import io
import hashlib
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objs as go

# ---------------------------
# Helper: parse uploaded CSV
# ---------------------------
def parse_contents(contents):
    if contents is None:
        return None
    content_type, content_string = contents.split(',')
    decoded_bytes = base64.b64decode(content_string)
    decoded_str = decoded_bytes.decode('utf-8', errors='ignore')

    # detect separator by first non-empty line
    first_line = ""
    for line in decoded_str.splitlines():
        if line.strip() != "":
            first_line = line
            break

    sep = ";" if ";" in first_line else ","
    return pd.read_csv(io.StringIO(decoded_str), sep=sep)


# ---------------------------
# Helper: stable UI token
# ---------------------------
def make_uirevision_token(raw_name, raw_len):
    token = f"{raw_name}_{raw_len}"
    return hashlib.md5(token.encode()).hexdigest()


# ---------------------------
# Build app
# ---------------------------
app = Dash(__name__)
server = app.server

app.layout = html.Div([
    html.H1("Gyroscope Data Viewer (Upload RAW + META)"),

    # Uploads side-by-side
    html.Div([
        html.Div([
            html.H3("Upload Gyroscope RAW CSV"),
            dcc.Upload(
                id="upload-raw",
                children=html.Div(["Drag & Drop or Click to Select RAW CSV"]),
                style={
                    "width": "100%", "height": "60px", "lineHeight": "60px",
                    "borderWidth": "1px", "borderStyle": "dashed",
                    "textAlign": "center", "borderRadius": "4px"
                },
                multiple=False
            ),
            html.Div(id="raw-file-name", style={"marginTop": "6px", "fontSize": "12px"})
        ], style={"flex": "1", "marginRight": "10px"}),

        html.Div([
            html.H3("Upload Metadata CSV (START / PAUSE)"),
            dcc.Upload(
                id="upload-meta",
                children=html.Div(["Drag & Drop or Click to Select META CSV"]),
                style={
                    "width": "100%", "height": "60px", "lineHeight": "60px",
                    "borderWidth": "1px", "borderStyle": "dashed",
                    "textAlign": "center", "borderRadius": "4px"
                },
                multiple=False
            ),
            html.Div(id="meta-file-name", style={"marginTop": "6px", "fontSize": "12px"})
        ], style={"flex": "1", "marginLeft": "10px"}),
    ], style={"display": "flex", "flexDirection": "row", "width": "100%", "marginBottom": "12px"}),

    # Stores
    dcc.Store(id="store-raw-json"),
    dcc.Store(id="store-meta-json"),
    dcc.Store(id="store-uirev"),
    dcc.Store(id="ui-store", storage_type="memory"),     # <--- Persistent UI state

    html.Hr(),

    # Slider
    html.Div([
        html.Div("Selected Time Range (seconds):", style={"fontWeight": "600"}),
        html.Div(id="slider-values", style={"marginBottom": "6px"}),
        dcc.RangeSlider(
            id="trim-slider",
            min=0, max=1,
            value=[0, 1],
            step=0.0001,
            allowCross=False,
            tooltip={"always_visible": True},
            marks=None
        )
    ], style={"marginBottom": "12px"}),

    # Graph
    dcc.Graph(
        id="gyro-graph",
        config={"displayModeBar": True, "scrollZoom": True},
        style={"height": "620px"}
    ),

    html.Div([
        html.H3("Statistics"),
        html.Pre(id="stats-output", style={"whiteSpace": "pre-wrap"})
    ], style={"marginTop": "12px"}),

    html.Div(id="status-output", style={"marginTop": "12px", "color": "#333"})
], style={"maxWidth": "1200px", "margin": "12px auto", "padding": "6px"})


# ---------------------------
# Upload handler
# ---------------------------
@app.callback(
    [
        Output("store-raw-json", "data"),
        Output("store-meta-json", "data"),
        Output("store-uirev", "data"),
        Output("raw-file-name", "children"),
        Output("meta-file-name", "children"),
        Output("trim-slider", "min"),
        Output("trim-slider", "max"),
        Output("trim-slider", "value"),
        Output("status-output", "children"),
        Output("ui-store", "data"),    # RESET UI STATE ON NEW UPLOAD
    ],
    [Input("upload-raw", "contents"), Input("upload-meta", "contents")],
    [State("upload-raw", "filename"), State("upload-meta", "filename")]
)
def handle_uploads(raw_contents, meta_contents, raw_filename, meta_filename):
    if raw_contents is None or meta_contents is None:
        return [None, None, None, "", "", 0, 1, [0, 1],
                "Waiting for both files...", {}]

    # RAW
    try:
        df_raw = parse_contents(raw_contents)
    except Exception as e:
        return [None, None, None, "", "", 0, 1, [0, 1],
                f"Error parsing RAW: {e}", {}]

    # META
    try:
        df_meta = parse_contents(meta_contents)
    except Exception as e:
        return [None, None, None, raw_filename or "", "",
                0, 1, [0, 1], f"Error parsing META: {e}", {}]

    df_raw.columns = [c.strip().strip('"') for c in df_raw.columns]
    df_meta.columns = [c.strip().strip('"') for c in df_meta.columns]

    # Find START/PAUSE
    event_col = next((c for c in df_meta.columns if "event" in c.lower()), None)
    sys_col = next((c for c in df_meta.columns if "system" in c.lower()), None)

    if event_col is None or sys_col is None:
        return [None, None, None, raw_filename or "", meta_filename or "",
                0, 1, [0, 1], "META missing necessary columns.", {}]

    start_time = float(df_meta[df_meta[event_col] == "START"][sys_col].iloc[0])
    pause_time = float(df_meta[df_meta[event_col] == "PAUSE"][sys_col].iloc[0])

    start_dt = datetime.utcfromtimestamp(start_time)

    # RAW time
    time_col = next((c for c in df_raw.columns if "time" in c.lower()), None)
    df_raw["Time (s)"] = df_raw[time_col].astype(float)
    df_raw["true_time"] = df_raw["Time (s)"].apply(lambda x: start_dt + timedelta(seconds=x))

    # JSON safe
    df_store = df_raw.copy()
    df_store["true_time"] = df_store["true_time"].astype(str)

    uirev = make_uirevision_token(raw_filename, len(df_raw))

    t_min, t_max = 0.0, float(df_raw["Time (s)"].max())

    return [
        df_store.to_dict("list"),
        {"start": start_time, "pause": pause_time},
        uirev,
        f"RAW: {raw_filename}", f"META: {meta_filename}",
        t_min, t_max, [t_min, t_max],
        "Files loaded successfully.",
        {}  # 🔥 reset UI-state
    ]


# ---------------------------
# MAIN CALLBACK (LEGACY RESET FIXED)
# ---------------------------
@app.callback(
    [
        Output("gyro-graph", "figure"),
        Output("stats-output", "children"),
        Output("slider-values", "children"),
        Output("ui-store", "data"),
    ],
    [
        Input("trim-slider", "value"),
        Input("store-raw-json", "data"),
        Input("store-meta-json", "data"),
        Input("gyro-graph", "relayoutData"),
        Input("gyro-graph", "restyleData"),
        Input("store-uirev", "data"),
        State("ui-store", "data"),
    ],
    prevent_initial_call=False
)
def update_graph(trim_range, raw_json, meta_json,
                 relayout, restyle, uirev_token, ui_state):

    if raw_json is None:
        return go.Figure(), "", "", ui_state

    # Restore DataFrame
    df = pd.DataFrame(raw_json)
    df["true_time"] = pd.to_datetime(df["true_time"])
    df["Time (s)"] = df["Time (s)"].astype(float)

    # Slider
    t_min, t_max = 0, df["Time (s)"].max()
    t0, t1 = trim_range
    dff = df[(df["Time (s)"] >= t0) & (df["Time (s)"] <= t1)]

    # Build plot
    fig = go.Figure()
    gyro_cols = [
        'Gyroscope x (rad/s)',
        'Gyroscope y (rad/s)',
        'Gyroscope z (rad/s)',
        'Absolute (rad/s)'
    ]
    gyro_cols = [c for c in gyro_cols if c in dff.columns]

    for col in gyro_cols:
        fig.add_trace(go.Scatter(
            x=dff["true_time"], y=dff[col],
            mode="lines", name=col
        ))

    # === UI STATE UPDATE ===
    # relayoutData → zoom & pan
    if relayout:
        if "xaxis.range" in relayout:
            ui_state["xrange"] = relayout["xaxis.range"]
        if "yaxis.range" in relayout:
            ui_state["yrange"] = relayout["yaxis.range"]

    # restyleData → legend visibility
    if restyle and isinstance(restyle, list) and len(restyle) == 2:
        prop, idxs = restyle
        if "visible" in prop:
            if "visible" not in ui_state:
                ui_state["visible"] = {}
            for i, tr in enumerate(idxs):
                ui_state["visible"][tr] = prop["visible"][i]

    # === Apply stored UI state ===
    if "xrange" in ui_state:
        fig.update_xaxes(range=ui_state["xrange"])
    if "yrange" in ui_state:
        fig.update_yaxes(range=ui_state["yrange"])
    if "visible" in ui_state:
        for tr, vis in ui_state["visible"].items():
            if tr < len(fig.data):
                fig.data[tr].visible = vis

    fig.update_layout(
        uirevision=uirev_token,
        title="Gyroscope Data",
        hovermode="x unified",
        xaxis_title="Time",
        yaxis_title="Angular velocity (rad/s)"
    )

    # Stats
    stats = dff[gyro_cols].describe().loc[["mean", "std"]].to_string()

    return fig, stats, f"{t0:.3f}–{t1:.3f} s", ui_state


if __name__ == "__main__":
    app.run(debug=True)
