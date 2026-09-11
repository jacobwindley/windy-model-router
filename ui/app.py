import json

import httpx
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html
from dash.exceptions import PreventUpdate

ROUTER_URL = "http://localhost:8000"

# Status/ink colors reused verbatim from the project's validated dataviz palette
# (references/palette.md) rather than picked ad hoc. Kept here (not just in
# style.css) because the Plotly figure below sets them from Python.
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_MUTED = "#898781"
BASELINE = "#c3c2b7"
STATUS_GOOD = "#0ca30c"
FILL_MATCHED = "rgba(12,163,12,0.10)"
FILL_PENDING = "rgba(137,135,129,0.08)"

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    },
}
# 1x1 transparent PNG, embedded so the "image content" toggle needs no network access.
TINY_PNG_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PAD_TEXT = "filler " * 9000

app = Dash(__name__, title="windy-model-router")


def render_message(message: dict) -> html.Div:
    is_user = message["role"] == "user"
    return html.Div(
        className=f"msg msg-{'user' if is_user else 'assistant'}",
        children=[
            html.Span("you" if is_user else "assistant", className="msg-label"),
            html.Div(message["content"], className="msg-bubble"),
        ],
    )


def render_route_detail(route_info: dict | None):
    if route_info is None:
        return html.P("No routing decision yet — send a message.", className="route-empty")

    decision = route_info["decision"]
    meta = route_info["metadata"]
    rows = [
        ("rule", decision["rule_id"]),
        ("reason", decision["reason"]),
        ("routed to", decision["routed_model"]),
        ("tokens", meta["token_count"]),
        ("messages", meta["message_count"]),
        ("tools", meta["tool_count"]),
        ("multimodal", meta["has_multimodal"]),
    ]
    return html.Table(
        [html.Tr([html.Td(label), html.Td(str(value))]) for label, value in rows],
        className="route-detail-table",
    )


def build_pipeline_figure(route_info: dict | None) -> go.Figure:
    fig = go.Figure()

    if route_info is None:
        fig.update_layout(
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            height=200,
            margin=dict(l=20, r=20, t=20, b=20),
            annotations=[
                dict(
                    text="Send a message to see the routing decision",
                    x=0.5,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    font=dict(color=INK_MUTED, size=13),
                )
            ],
        )
        return fig

    tiers = route_info["tiers"]
    decision = route_info["decision"]
    xs = [1, 2, 3]

    fill_colors, border_colors, labels, hover_texts = [], [], [], []
    for tier in tiers:
        matched = tier["status"] == "matched"
        fill_colors.append(FILL_MATCHED if matched else FILL_PENDING)
        border_colors.append(STATUS_GOOD if matched else INK_MUTED)
        status_label = "✓ matched" if matched else "not yet implemented"
        labels.append(f"Tier {tier['tier']}<br>{tier['name']}<br><span style='font-size:11px'>{status_label}</span>")
        hover_texts.append(
            f"Rule: {decision['rule_id']}<br>{decision['reason']}<br>Routed to: {decision['routed_model']}"
            if matched
            else "Not implemented yet"
        )

    for i in range(len(xs) - 1):
        fig.add_annotation(
            x=xs[i + 1] - 0.32,
            y=0,
            ax=xs[i] + 0.32,
            ay=0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=2,
            arrowcolor=BASELINE,
            text="",
        )

    fig.add_trace(
        go.Scatter(
            x=xs,
            y=[0, 0, 0],
            mode="markers+text",
            marker=dict(size=110, symbol="square", color=fill_colors, line=dict(width=3, color=border_colors)),
            text=labels,
            textposition="middle center",
            textfont=dict(color=INK_PRIMARY, size=13),
            hovertext=hover_texts,
            hoverinfo="text",
            showlegend=False,
        )
    )

    fig.update_xaxes(visible=False, range=[0.3, 3.7])
    fig.update_yaxes(visible=False, range=[-1, 1])
    fig.update_layout(
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        margin=dict(l=20, r=20, t=20, b=20),
        height=200,
    )
    return fig


app.layout = html.Div(
    className="app-shell",
    children=[
        html.Header(
            className="app-header",
            children=[
                html.H1("windy-model-router", className="brand"),
                html.P(
                    [
                        "routing demo — talks to ",
                        html.Code(ROUTER_URL),
                        " like any other client and reads its ",
                        html.Code("X-Route-Info"),
                        " response header.",
                    ],
                    className="subtitle",
                ),
            ],
        ),
        dcc.Store(id="messages", data=[]),
        dcc.Loading(
            type="dot",
            color="#2a78d6",
            children=html.Div(
                className="layout-grid",
                children=[
                    html.Div(
                        children=[
                            html.Details(
                                className="settings",
                                children=[
                                    html.Summary("router api key (optional)"),
                                    html.Div(
                                        className="api-key-row",
                                        children=[
                                            dcc.Input(
                                                id="api-key",
                                                type="password",
                                                placeholder="only needed if ROUTER_API_KEY is set",
                                                persistence=True,
                                                persistence_type="local",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dcc.Checklist(
                                id="demo-toggles",
                                className="demo-toggles",
                                options=[
                                    {"label": "include a tool call", "value": "tool"},
                                    {"label": "include image content", "value": "image"},
                                    {"label": "pad prompt over 8000 tokens", "value": "pad"},
                                ],
                                value=[],
                            ),
                            html.Div(id="chat-log", className="chat-log panel"),
                            html.Div(
                                className="composer-row",
                                children=[
                                    html.Span(">", className="composer-caret"),
                                    dcc.Input(
                                        id="composer",
                                        type="text",
                                        placeholder="ask something, then press enter",
                                        className="composer-input",
                                        autoComplete="off",
                                        autoFocus=True,
                                    ),
                                    html.Button("Send", id="send", n_clicks=0, className="btn-send"),
                                ],
                            ),
                        ],
                    ),
                    html.Aside(
                        className="inspector panel",
                        children=[
                            html.H2("why this model?", className="panel-title"),
                            dcc.Graph(
                                id="pipeline-diagram",
                                figure=build_pipeline_figure(None),
                                config={"displayModeBar": False},
                            ),
                            html.Div(id="route-detail", children=render_route_detail(None)),
                        ],
                    ),
                ],
            ),
        ),
        html.Div(id="scroll-anchor", style={"display": "none"}),
    ],
)

app.clientside_callback(
    """
    function(children) {
        var el = document.getElementById('chat-log');
        if (el) { el.scrollTop = el.scrollHeight; }
        return '';
    }
    """,
    Output("scroll-anchor", "children"),
    Input("chat-log", "children"),
)


@app.callback(
    Output("messages", "data"),
    Output("chat-log", "children"),
    Output("pipeline-diagram", "figure"),
    Output("route-detail", "children"),
    Output("composer", "value"),
    Input("send", "n_clicks"),
    Input("composer", "n_submit"),
    State("composer", "value"),
    State("demo-toggles", "value"),
    State("api-key", "value"),
    State("messages", "data"),
    prevent_initial_call=True,
)
def on_send(n_clicks, n_submit, composer_value, toggles, api_key, messages):
    user_text = (composer_value or "").strip()
    if not user_text:
        raise PreventUpdate

    toggles = toggles or []
    messages = messages or []

    history = [{"role": m["role"], "content": m["content"]} for m in messages]

    content: str | list[dict] = user_text
    if "pad" in toggles:
        content = f"{user_text} {PAD_TEXT}"
    if "image" in toggles:
        content = [
            {"type": "text", "text": content if isinstance(content, str) else user_text},
            {"type": "image_url", "image_url": {"url": TINY_PNG_DATA_URI}},
        ]

    body = {
        "model": "auto",
        "messages": history + [{"role": "user", "content": content}],
        "stream": False,
    }
    if "tool" in toggles:
        body["tools"] = [TOOL_DEF]

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    route_info = None
    try:
        resp = httpx.post(f"{ROUTER_URL}/v1/chat/completions", json=body, headers=headers, timeout=60)
    except httpx.RequestError as exc:
        assistant_text = f"⚠ Could not reach the router at {ROUTER_URL}: {exc}"
    else:
        raw_route_info = resp.headers.get("X-Route-Info")
        route_info = json.loads(raw_route_info) if raw_route_info else None

        if resp.status_code == 200:
            reply = resp.json()["choices"][0]["message"]
            if reply.get("content"):
                assistant_text = reply["content"]
            elif reply.get("tool_calls"):
                calls = ", ".join(
                    f"{c['function']['name']}({c['function']['arguments']})" for c in reply["tool_calls"]
                )
                assistant_text = f"🔧 Model requested a tool call: {calls}"
            else:
                assistant_text = "(empty response)"
        else:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                detail = resp.text
            assistant_text = f"⚠ Upstream error {resp.status_code}: {detail}"

    new_messages = messages + [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_text},
    ]

    return (
        new_messages,
        [render_message(m) for m in new_messages],
        build_pipeline_figure(route_info),
        render_route_detail(route_info),
        "",
    )


if __name__ == "__main__":
    app.run(debug=True, port=8050)
