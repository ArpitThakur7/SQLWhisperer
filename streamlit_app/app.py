"""SQLWhisperer — Streamlit Interactive Web Interface.

Provides direct in-browser database connection management, schema inspection,
model selection, auto-charting, and conversational SQL querying.
"""

import hashlib
import os
from pathlib import Path
import httpx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.visualization.auto_chart import (
    detect_best_chart,
    create_plotly_figure,
    calculate_data_stats,
    generate_visual_insights,
    PALETTES,
)

# ── Config ────────────────────────────────────────────────────────

API_URL = os.getenv("API_URL", "http://localhost:8000/api/v1")
REQUEST_TIMEOUT = 120

# ── Page Setup ────────────────────────────────────────────────────

st.set_page_config(
    page_title="SQLWhisperer — Natural Language to SQL",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────

st.markdown(
    """
    <style>
        /* Background */
        .stApp {
            background: linear-gradient(135deg, #0d0b21 0%, #1e1b4b 50%, #17153a 100%);
        }

        /* Metric cards */
        [data-testid="stMetricValue"] {
            font-size: 1.3rem;
            font-weight: 700;
            color: #818cf8;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.8rem;
            color: #94a3b8;
        }

        /* Code blocks */
        .stCodeBlock {
            border: 1px solid rgba(129, 140, 248, 0.25);
            border-radius: 8px;
        }

        /* Sidebar styling */
        [data-testid="stSidebar"] {
            background: #0f172a;
            border-right: 1px solid rgba(255, 255, 255, 0.08);
        }

        /* Buttons */
        .stButton > button {
            border-radius: 8px;
            transition: all 0.2s ease;
        }
        .stButton > button:hover {
            border-color: #818cf8;
            box-shadow: 0 0 10px rgba(129, 140, 248, 0.3);
        }

        /* Hide Streamlit header/footer */
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session State Initialisation ──────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "custom_db_url" not in st.session_state:
    st.session_state.custom_db_url = "sqlite:///./data/demo_ecommerce.db"

if "connected_db_status" not in st.session_state:
    st.session_state.connected_db_status = None

if "schema_cache" not in st.session_state:
    st.session_state.schema_cache = None

if "custom_api_key" not in st.session_state:
    st.session_state.custom_api_key = ""


# ── Helper API Client ─────────────────────────────────────────────


def api_request(method: str, endpoint: str, **kwargs) -> dict | list | None:
    """Send HTTP request to backend with clean error handling."""
    try:
        url = f"{API_URL}{endpoint}"
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            if method == "GET":
                resp = client.get(url, **kwargs)
            else:
                resp = client.post(url, **kwargs)
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        return None
    except httpx.HTTPStatusError as exc:
        st.error(f"API Error ({exc.response.status_code}): {exc.response.text}")
        return None
    except Exception as exc:
        st.error(f"Request failed: {exc}")
        return None


# ── Result Renderer ───────────────────────────────────────────────


def render_result(result: dict, key_suffix: str | int | None = None) -> None:
    """Render metrics, generated SQL, interactive tables/charts, and summaries."""
    # Deterministic result ID for persistent widget states
    qid = result.get("query_id")
    if key_suffix is not None:
        ruid = f"s{key_suffix}_{qid or '0'}"
    elif qid:
        ruid = f"qid_{qid}"
    else:
        q_raw = f"{result.get('question', '')}|{result.get('sql', '')}|{result.get('row_count', 0)}"
        ruid = f"h_{hashlib.md5(q_raw.encode('utf-8')).hexdigest()[:10]}"

    # 1. Performance & Confidence Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📊 Rows", result.get("row_count", 0))
    col2.metric("⚡ Time", f"{result.get('execution_time_ms', 0):.0f}ms")
    col3.metric("🎯 Confidence", f"{result.get('confidence', 0):.0%}")
    col4.metric("🔄 Retries", result.get("refinement_count", 0))

    # 2. Generated SQL
    with st.expander("📝 Generated SQL Query", expanded=True):
        st.code(result.get("sql", ""), language="sql")

    # 3. Results Table & Auto-Visualizations
    results = result.get("results", [])
    if results:
        raw_rows = [r.get("data", r) if isinstance(r, dict) else r for r in results]
        df = pd.DataFrame(raw_rows)

        tab_table, tab_chart = st.tabs(["📋 Table View", "📈 Auto-Chart Studio"])

        with tab_table:
            st.dataframe(df, use_container_width=True)
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download as CSV",
                data=csv_bytes,
                file_name="sqlwhisperer_query_results.csv",
                mime="text/csv",
                key=f"dl_{ruid}",
            )

        with tab_chart:
            if df.empty:
                st.info("No data available to visualize.")
            else:
                rec = detect_best_chart(df, question=result.get("question", ""))
                all_cols = df.columns.tolist()
                num_cols = df.select_dtypes(include=["number"]).columns.tolist()

                # ── Statistical KPI Summary Ribbon ────────────────
                stats = calculate_data_stats(df, rec.y_col)
                if "total" in stats:
                    st1, st2, st3, st4 = st.columns(4)
                    st1.metric(
                        label=f"Σ Total {stats.get('metric', '').replace('_', ' ').title()}",
                        value=f"{stats['total']:,.0f}" if stats["total"] >= 100 else f"{stats['total']:,.2f}",
                    )
                    st2.metric(
                        label=f"μ Average",
                        value=f"{stats['mean']:,.2f}",
                    )
                    st3.metric(
                        label=f"↑ Peak ({stats.get('peak_label', '')[:12]})",
                        value=f"{stats['max']:,.0f}" if stats["max"] >= 100 else f"{stats['max']:,.2f}",
                    )
                    st4.metric(
                        label="N Rows Analyzed",
                        value=f"{stats['row_count']:,}",
                    )
                    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

                # ── Widget Session-State Keys ─────────────────────
                key_ctype = f"ctype_{ruid}"
                key_cx = f"cx_{ruid}"
                key_cy = f"cy_{ruid}"
                key_pal = f"pal_{ruid}"
                key_trend = f"trend_{ruid}"

                # ── Studio Controls Toolbar ───────────────────────
                chart_options = [
                    "Auto (Recommended)",
                    "Treemap",
                    "Heatmap",
                    "Funnel",
                    "Choropleth",
                    "Area",
                    "Line",
                    "Pie",
                    "Bar",
                    "Scatter",
                    "Box",
                    "Metric",
                ]
                y_choices = num_cols if num_cols else all_cols

                col_info, col_popover = st.columns([3, 1])
                with col_info:
                    st.caption(
                        f"✨ **AI Visualizer Insight**: *{rec.reason}* "
                        f"| Recommendation: `{rec.chart_type.upper()}` ({int(rec.confidence * 100)}% match)"
                    )
                with col_popover:
                    with st.popover("⚙️ Customize Visual"):
                        x_default_idx = (
                            all_cols.index(rec.x_col)
                            if rec.x_col in all_cols
                            else 0
                        )
                        y_default_idx = (
                            y_choices.index(rec.y_col)
                            if rec.y_col in y_choices
                            else 0
                        )
                        st.selectbox(
                            "📊 Chart Type",
                            chart_options,
                            key=key_ctype,
                        )
                        st.selectbox(
                            "X-Axis / Category",
                            all_cols,
                            index=x_default_idx if all_cols else 0,
                            key=key_cx,
                        )
                        st.selectbox(
                            "Y-Axis / Measure",
                            y_choices,
                            index=y_default_idx if y_choices else 0,
                            key=key_cy,
                        )
                        st.selectbox(
                            "Theme Palette",
                            list(PALETTES.keys()),
                            key=key_pal,
                        )
                        st.checkbox(
                            "📈 Show Trendline / Moving Avg",
                            value=False,
                            key=key_trend,
                        )

                # Read effective values from session_state (persists across reruns
                # even when the popover is closed and widgets don't render)
                chosen_chart = st.session_state.get(key_ctype, "Auto (Recommended)")
                custom_x = st.session_state.get(key_cx, rec.x_col)
                custom_y = st.session_state.get(key_cy, rec.y_col)
                chosen_palette = st.session_state.get(key_pal, "Cyberpunk Neon")
                show_trend = st.session_state.get(key_trend, False)

                # Determine effective parameters
                override_type = None if chosen_chart.startswith("Auto") else chosen_chart.lower()
                active_palette = chosen_palette

                try:
                    fig = create_plotly_figure(
                        df,
                        rec=rec,
                        override_type=override_type,
                        override_x=custom_x,
                        override_y=custom_y,
                        palette_name=active_palette,
                        show_trendline=show_trend,
                    )
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        config={
                            "displayModeBar": True,
                            "toImageButtonOptions": {
                                "format": "png",
                                "filename": "sqlwhisperer_analytics",
                                "height": 600,
                                "width": 1000,
                                "scale": 2,
                            },
                        },
                    )

                    # Automated Analytical Highlights
                    insights = generate_visual_insights(df, rec, stats)
                    if insights:
                        st.markdown("##### 💡 Key Analytical Highlights")
                        for ins in insights:
                            st.markdown(f"- {ins}")

                    # Interactive HTML export
                    html_bytes = fig.to_html(include_plotlyjs="cdn").encode("utf-8")
                    st.download_button(
                        label="🌐 Download Interactive Chart (HTML)",
                        data=html_bytes,
                        file_name="sqlwhisperer_chart.html",
                        mime="text/html",
                        key=f"html_dl_{ruid}",
                    )
                except Exception as chart_err:
                    st.warning(f"Could not render visual: {chart_err}")
                    st.dataframe(df, use_container_width=True)

    elif result.get("success"):
        st.info("Query executed successfully but returned zero rows.")

    # 4. Plain-English Summary
    explanation = result.get("explanation", "")
    if explanation:
        with st.expander("💡 Plain-English Summary", expanded=True):
            st.markdown(explanation)

    # 5. Error banner (if failed)
    if not result.get("success") and result.get("error"):
        st.error(f"⚠️ Query Error: {result.get('error')}")


# ── Sidebar Controls ──────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔮 SQLWhisperer")
    st.caption("Natural Language → Production SQL")

    # API Status check
    health = api_request("GET", "/health")
    if health:
        cache_badge = "⚡ Redis Active" if health.get("redis_connected") else "🧠 In-Memory Cache"
        st.success(f"🟢 Connected ({health.get('dialect', 'Auto')}) • {cache_badge}")
    else:
        st.error("🔴 API Offline — Start with `run.bat` or `uvicorn src.api.app:app`")

    st.divider()

    # ── Database Connection Manager ───────────────────────────────
    st.markdown("### 🔌 Database Connection")

    conn_mode = st.radio(
        "Source",
        ["📦 Demo SQLite", "🔗 Custom URL", "📁 Upload SQLite File"],
        horizontal=True,
    )

    if conn_mode == "📦 Demo SQLite":
        db_url_input = "sqlite:///./data/demo_ecommerce.db"
        st.caption("Using embedded e-commerce dataset (Customers, Products, Orders).")
    elif conn_mode == "🔗 Custom URL":
        db_url_input = st.text_input(
            "Connection String",
            value=st.session_state.custom_db_url,
            placeholder="postgresql://user:pass@host:5432/dbname",
            help="Supports PostgreSQL, SQLite, MySQL, and DuckDB SQLAlchemy connection strings.",
        )
    else:  # Upload file
        uploaded_file = st.file_uploader("Upload .db or .sqlite", type=["db", "sqlite", "sqlite3"])
        if uploaded_file is not None:
            if st.button("📥 Import & Connect Database"):
                with st.spinner("Uploading and introspecting database..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                    upload_res = api_request("POST", "/db/upload", files=files)
                    if upload_res and upload_res.get("success"):
                        st.session_state.custom_db_url = upload_res["database_url"]
                        st.session_state.connected_db_status = upload_res
                        st.session_state.schema_cache = None
                        st.success(f"Loaded {uploaded_file.name} ({upload_res.get('table_count')} tables)!")
                    else:
                        st.error("Failed to upload database file.")
        db_url_input = st.session_state.custom_db_url

    # Test / Apply Connection Button
    if st.button("⚡ Connect / Test Link", use_container_width=True):
        with st.spinner("Testing connection..."):
            test_res = api_request("POST", "/db/test", json={"database_url": db_url_input})
            if test_res and test_res.get("success"):
                st.session_state.custom_db_url = db_url_input
                st.session_state.connected_db_status = test_res
                # Invalidate schema cache to refresh
                st.session_state.schema_cache = None
                st.success(f"Connected! Dialect: {test_res.get('dialect')} ({test_res.get('table_count')} tables)")
            else:
                err_msg = test_res.get("error") if test_res else "Unable to reach database"
                st.error(f"Connection failed: {err_msg}")

    st.divider()

    # ── Database Schema Browser ───────────────────────────────────
    st.markdown("### 🗄️ Schema Explorer")

    if st.session_state.schema_cache is None and health:
        schema_data = api_request("GET", "/db/schema", params={"database_url": st.session_state.custom_db_url})
        if schema_data:
            st.session_state.schema_cache = schema_data

    if st.session_state.schema_cache:
        for table in st.session_state.schema_cache:
            t_name = table["name"]
            r_count = table.get("row_count", 0)
            with st.expander(f"📁 {t_name} ({r_count:,} rows)"):
                # Column list
                cols = table.get("columns", [])
                col_text = []
                for c in cols:
                    pk_marker = "🔑 " if c.get("primary_key") else ""
                    col_text.append(f"- {pk_marker}`{c['name']}` ({c['type']})")
                st.markdown("\n".join(col_text))

                # Sample data button
                sample_rows = table.get("sample_rows", [])
                if sample_rows:
                    st.caption("Sample Data:")
                    st.dataframe(pd.DataFrame(sample_rows), use_container_width=True)
    else:
        st.caption("Connect to a database to browse tables and columns.")

    st.divider()

    # ── LLM & Provider Settings ───────────────────────────────────
    with st.expander("⚙️ LLM Provider & Free Models", expanded=True):
        provider_display = st.selectbox(
            "AI Provider",
            [
                "⚡ Groq (100% Free & Ultra-Fast)",
                "🌐 Google Gemini (Free Tier)",
                "💻 Ollama (100% Free & Offline / No Key)",
                "🔓 OpenRouter (Free Community Models)",
                "🔑 OpenAI (Paid: GPT-4o)",
            ],
            index=0,
        )

        if "Groq" in provider_display:
            st.session_state.selected_provider = "groq"
            st.markdown("👉 [Get a Free Groq API Key (instant)](https://console.groq.com/keys)")
            groq_key = st.text_input(
                "Groq API Key",
                type="password",
                placeholder="gsk_...",
                value=st.session_state.custom_api_key,
                help="100% Free, no credit card required.",
            )
            st.session_state.custom_api_key = groq_key
            st.session_state.selected_model = st.selectbox(
                "Model",
                ["openai/gpt-oss-120b", "qwen-2.5-coder-32b", "qwen/qwen3.6-27b"],
            )

        elif "Gemini" in provider_display:
            st.session_state.selected_provider = "gemini"
            st.markdown("👉 [Get a Free Gemini Key](https://aistudio.google.com/app/apikey)")
            gemini_key = st.text_input(
                "Gemini API Key",
                type="password",
                placeholder="AIzaSy...",
                value=st.session_state.custom_api_key,
            )
            st.session_state.custom_api_key = gemini_key
            st.session_state.selected_model = st.selectbox(
                "Model",
                ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
            )

        elif "Ollama" in provider_display:
            st.session_state.selected_provider = "ollama"
            st.caption("💻 Runs on your machine with 0 keys. Run in terminal: `ollama run qwen2.5-coder:7b`")
            st.session_state.custom_api_key = ""
            st.session_state.selected_model = st.text_input("Ollama Model", value="qwen2.5-coder:7b")

        elif "OpenRouter" in provider_display:
            st.session_state.selected_provider = "openrouter"
            st.markdown("👉 [Get an OpenRouter Key](https://openrouter.ai/keys)")
            or_key = st.text_input("OpenRouter Key", type="password", value=st.session_state.custom_api_key)
            st.session_state.custom_api_key = or_key
            st.session_state.selected_model = st.selectbox(
                "Model",
                ["meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-r1:free"],
            )

        else:
            st.session_state.selected_provider = "openai"
            oai_key = st.text_input(
                "OpenAI Key",
                type="password",
                placeholder="sk-...",
                value=st.session_state.custom_api_key,
                help="Uses key from .env if left blank.",
            )
            st.session_state.custom_api_key = oai_key
            st.session_state.selected_model = st.selectbox(
                "Model",
                ["gpt-4o", "gpt-4o-mini", "o3-mini"],
            )

    st.divider()

    # ── Quick Prompts & Actions ───────────────────────────────────
    st.markdown("### 💡 Quick Starters")
    starters = [
        "Top 5 products by revenue",
        "Active customers in the US",
        "Total orders by status",
        "Average order value by customer tier",
    ]
    for q in starters:
        if st.button(q, use_container_width=True):
            st.session_state["queued_prompt"] = q

    st.divider()

    # ── Architecture Visualizer Shortcut ─────────────────────────
    st.markdown("### 🏛️ System Architecture")
    visualizer_path = Path(__file__).resolve().parent.parent / "architecture_visualizer.html"
    if st.button("🌐 Open Visualizer in Browser", use_container_width=True):
        if os.name == "nt":
            os.startfile(str(visualizer_path))
        st.toast("Opened Architecture Visualizer!", icon="🚀")

    if st.session_state.messages:
        if st.button("🗑️ Clear Chat History", use_container_width=True):
            st.session_state.messages = []
            st.rerun()


# ── Main Tabs: Chat Interface, History & Architecture Visualizer ──

tab_chat, tab_erd, tab_federation, tab_history, tab_arch = st.tabs([
    "💬 Query Assistant",
    "📐 Schema ERD",
    "🌐 Multi-DB Federation",
    "📜 Query History",
    "🏛️ System Architecture Visualizer",
])

with tab_chat:
    st.markdown(
        """
        <div style='text-align: center; margin-bottom: 2rem;'>
            <h1 style='background: linear-gradient(90deg, #818cf8, #c084fc);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            font-size: 2.4rem; margin-bottom: 0.3rem;'>
            Ask Your Database in Plain English
            </h1>
            <p style='color: #94a3b8; font-size: 1.05rem;'>
            Natural language &rarr; self-healing SQL with auto-visualizations and plain-English summaries
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Display existing messages
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and "result" in msg:
                render_result(msg["result"], key_suffix=idx)
            else:
                st.markdown(msg["content"])

with tab_erd:
    st.markdown("### 📐 Interactive Entity-Relationship Diagram (ERD)")
    st.caption("Visual database schema topology mapping tables, column data types, primary keys (🔑), and foreign key link bridges (🔗).")

    col_erd1, col_erd2 = st.columns([6, 2])
    with col_erd2:
        if st.button("🔄 Refresh ERD", key="btn_refresh_erd", use_container_width=True):
            st.rerun()

    erd_params = {"database_url": st.session_state.custom_db_url} if st.session_state.custom_db_url else {}
    erd_res = api_request("GET", "/db/erd", params=erd_params)
    if erd_res and "dot" in erd_res:
        em1, em2, em3 = st.columns(3)
        em1.metric("Tables Mapped", erd_res.get("table_count", 0))
        em2.metric("FK Relationships", erd_res.get("relationship_count", 0))
        em3.metric("Renderer", "Graphviz DOT")

        st.graphviz_chart(erd_res["dot"], use_container_width=True)

        if erd_res.get("relationships"):
            with st.expander("🔗 Discovered Foreign Key Link Bridges"):
                st.dataframe(
                    [
                        {
                            "Source Table": r["from_table"],
                            "Foreign Key": r["from_column"],
                            "Target Table": r["to_table"],
                            "Primary Key": r["to_column"],
                        }
                        for r in erd_res["relationships"]
                    ],
                    use_container_width=True,
                )
    else:
        st.info("Loading or unable to generate ERD. Make sure database connection is active.")

with tab_federation:
    st.markdown("### 🌐 Multi-Database Federation (DuckDB)")
    st.caption("Execute simultaneous cross-database queries across multiple disjoint catalogs (e.g. SQLite demo DB, history audit, and external files) in an in-memory DuckDB virtual engine.")

    cat_res = api_request("GET", "/federation/catalogs")
    if cat_res and "catalogs" in cat_res:
        st.markdown("**Attached Virtual Catalogs:**")
        cat_items = list(cat_res["catalogs"].items())
        cols = st.columns(max(1, len(cat_items)))
        for i, (cat_name, cat_tables) in enumerate(cat_items):
            cols[i % len(cols)].info(f"📁 **{cat_name}** ({len(cat_tables)} tables)\n`{', '.join(cat_tables[:4])}`")

    fed_sql_default = "SELECT p.name, p.category, p.price\nFROM ecommerce.products p\nORDER BY p.price DESC\nLIMIT 5;"
    fed_sql = st.text_area("Federated SQL Query", value=fed_sql_default, height=120)

    if st.button("⚡ Run Federated Query", key="btn_run_fed"):
        with st.spinner("Executing federated query across catalogs..."):
            fed_result = api_request("POST", "/federation/query", json={"sql": fed_sql, "max_rows": 100})
            if fed_result and "results" in fed_result:
                st.success(f"Execution: {fed_result.get('execution_time_ms', 0)}ms | Rows: {fed_result.get('row_count', 0)}")
                st.dataframe(fed_result["results"], use_container_width=True)
            else:
                st.error("Federated query execution failed.")

with tab_history:
    st.markdown("### 📜 Past Query Runs & Audit Log")
    st.caption("View recent questions, generated SQL, success status, and re-run any past question with one click.")
    history_records = api_request("GET", "/history", params={"limit": 30})
    if history_records:
        for item in history_records:
            icon = "✅" if item.get("was_successful") else "❌"
            q_text = item.get("question", "")
            created_str = str(item.get("created_at", ""))[:19]
            with st.expander(f"{icon} {q_text[:75]} — {created_str}"):
                st.markdown(f"**Question:** {q_text}")
                if item.get("sql"):
                    st.code(item.get("sql"), language="sql")
                hc1, hc2 = st.columns([2, 5])
                if hc1.button("🔄 Re-run Prompt", key=f"rerun_{item.get('id')}"):
                    st.session_state["queued_prompt"] = q_text
                    st.rerun()
                hc2.caption(f"Confidence score: {item.get('confidence', 0.0):.0%}")
    else:
        st.info("No query history recorded yet. Ask a question to begin building your audit log.")

with tab_arch:
    visualizer_path = Path(__file__).resolve().parent.parent / "architecture_visualizer.html"
    col_v1, col_v2 = st.columns([6, 2])
    with col_v1:
        st.markdown("### 🏛️ SQLWhisperer Interactive Architecture Visualizer")
        st.caption("Deeply designed interactive blueprint: Click nodes to inspect schemas, explore the self-healing state machine, or run the live pipeline simulator.")
    with col_v2:
        if st.button("↗️ Open in New Window", key="btn_open_visualizer", use_container_width=True):
            if os.name == "nt":
                os.startfile(str(visualizer_path))
            st.toast("Opened Architecture Visualizer in browser!", icon="🌐")

    if visualizer_path.is_file():
        with open(visualizer_path, "r", encoding="utf-8") as f:
            visualizer_html = f.read()
        components.html(visualizer_html, height=1100, scrolling=True)
    else:
        st.error(f"Visualizer file not found at: {visualizer_path}")

# Check for queued prompt from sidebar buttons
queued_prompt = st.session_state.pop("queued_prompt", None)
user_prompt = st.chat_input("Ask a question about your database (e.g. 'Show monthly revenue for 2024')...")

active_prompt = user_prompt or queued_prompt

if active_prompt:
    # 1. User message
    st.session_state.messages.append({"role": "user", "content": active_prompt})
    with tab_chat:
        with st.chat_message("user"):
            st.markdown(active_prompt)

        # 2. Assistant execution with live SSE stage streaming
        with st.chat_message("assistant"):
            payload = {
                "question": active_prompt,
                "database_url": st.session_state.custom_db_url,
                "llm_provider": getattr(st.session_state, "selected_provider", "openai"),
                "model": getattr(st.session_state, "selected_model", ""),
            }
            if st.session_state.custom_api_key:
                payload["api_key"] = st.session_state.custom_api_key

            response = None
            with st.status("🔮 Running self-healing query pipeline...", expanded=True) as status_box:
                try:
                    import httpx
                    stream_url = f"{API_BASE_URL}/query/stream"
                    with httpx.Client(timeout=45.0) as client:
                        with client.stream("POST", stream_url, json=payload) as r:
                            for raw_line in r.iter_lines():
                                if raw_line.startswith("data: "):
                                    event = json.loads(raw_line[6:])
                                    stage = event.get("stage", "")
                                    msg = event.get("message", "")
                                    if stage == "complete":
                                        response = event.get("result")
                                        status_box.update(label="✅ Query Complete!", state="complete", expanded=False)
                                    elif stage == "cache_hit":
                                        status_box.update(label="⚡ Instant Cache Hit", state="complete", expanded=False)
                                    elif stage == "error":
                                        status_box.update(label=f"❌ Error: {event.get('error', msg)}", state="error")
                                    else:
                                        status_box.write(f"• **{stage.capitalize()}**: {msg}")
                except Exception as stream_err:
                    status_box.write(f"Streaming fallback: {stream_err}")
                    response = api_request("POST", "/query", json=payload)
                    status_box.update(label="✅ Query Complete", state="complete", expanded=False)

            if response:
                st.session_state.messages.append({"role": "assistant", "result": response})
                render_result(response, key_suffix=len(st.session_state.messages) - 1)

                # Feedback buttons
                qid = response.get("query_id")
                if qid:
                    fb_c1, fb_c2, _ = st.columns([1, 1, 6])
                    if fb_c1.button("👍 Useful", key=f"up_{qid}"):
                        api_request("POST", "/feedback", json={"query_id": qid, "feedback": "positive", "rating": "up"})
                        st.toast("Feedback saved! Few-shot memory updated.", icon="✅")
                    if fb_c2.button("👎 Poor", key=f"down_{qid}"):
                        api_request("POST", "/feedback", json={"query_id": qid, "feedback": "negative", "rating": "down"})
                        st.toast("Feedback recorded for self-healing improvement.", icon="ℹ️")
            else:
                st.error("Failed to receive a response from SQLWhisperer backend.")
