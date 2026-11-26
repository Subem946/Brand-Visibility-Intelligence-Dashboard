import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

st.set_page_config(
    page_title="Brand Visibility & Market Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_db_engine():
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    db_name = os.getenv("MYSQL_DB", "brand_visibility_db")
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"
    return create_engine(url)


@st.cache_data(ttl=300)
def get_filter_metadata():
    """Fetch distinct filter values and min/max bounds directly from MySQL."""
    engine = get_db_engine()
    with engine.connect() as conn:
        brands = pd.read_sql(
            text("SELECT DISTINCT Brand FROM product_listings WHERE Brand IS NOT NULL ORDER BY Brand;"),
            conn,
        )["Brand"].tolist()

        platforms = pd.read_sql(
            text("SELECT DISTINCT platform FROM product_listings WHERE platform IS NOT NULL ORDER BY platform;"),
            conn,
        )["platform"].tolist()

        keywords = pd.read_sql(
            text("SELECT DISTINCT Product FROM product_listings WHERE Product IS NOT NULL ORDER BY Product;"),
            conn,
        )["Product"].tolist()

        bounds = pd.read_sql(
            text("""
                SELECT
                    FLOOR(MIN(price)) AS min_price,
                    CEIL(MAX(price)) AS max_price,
                    FLOOR(MIN(rating) * 10) / 10 AS min_rating,
                    CEIL(MAX(rating) * 10) / 10 AS max_rating
                FROM product_listings;
            """),
            conn,
        ).iloc[0]

    return brands, platforms, keywords, bounds


def query_filtered_data(brands, platforms, keywords, price_range, rating_range):
    """Dynamically build a parameterized SQL query based on active sidebar filters."""
    conditions = [
        "price BETWEEN :min_price AND :max_price",
        "rating BETWEEN :min_rating AND :max_rating",
    ]
    params = {
        "min_price": float(price_range[0]),
        "max_price": float(price_range[1]),
        "min_rating": float(rating_range[0]),
        "max_rating": float(rating_range[1]),
    }

    if brands:
        placeholders = ", ".join([f":brand_{i}" for i in range(len(brands))])
        conditions.append(f"Brand IN ({placeholders})")
        for i, b in enumerate(brands):
            params[f"brand_{i}"] = b

    if platforms:
        placeholders = ", ".join([f":plat_{i}" for i in range(len(platforms))])
        conditions.append(f"platform IN ({placeholders})")
        for i, p in enumerate(platforms):
            params[f"plat_{i}"] = p

    if keywords:
        placeholders = ", ".join([f":kw_{i}" for i in range(len(keywords))])
        conditions.append(f"Product IN ({placeholders})")
        for i, k in enumerate(keywords):
            params[f"kw_{i}"] = k

    where_clause = " AND ".join(conditions)
    sql_query = f"SELECT * FROM product_listings WHERE {where_clause};"

    engine = get_db_engine()
    with engine.connect() as conn:
        df_result = pd.read_sql(text(sql_query), conn, params=params)

    return df_result, sql_query


try:
    all_brands, all_platforms, all_keywords, bounds = get_filter_metadata()
except Exception as e:
    st.error(f"Could not connect to MySQL database. Check your `.env` credentials.\n\nError: {e}")
    st.stop()

st.sidebar.header("🔍 SQL Dynamic Filters")
st.sidebar.caption("Selections dynamically update the MySQL WHERE clause.")

selected_keywords = st.sidebar.multiselect(
    "Keyword / Product Category",
    options=all_keywords,
    default=[],
    placeholder="All Keywords",
)

selected_brands = st.sidebar.multiselect(
    "Brand",
    options=all_brands,
    default=[],
    placeholder="All Brands",
)

selected_platforms = st.sidebar.multiselect(
    "Platform",
    options=all_platforms,
    default=[],
    placeholder="All Platforms",
)

min_p, max_p = float(bounds["min_price"]), float(bounds["max_price"])
selected_price = st.sidebar.slider(
    "Price Range ($)",
    min_value=min_p,
    max_value=max_p,
    value=(min_p, max_p),
)

min_r, max_r = float(bounds["min_rating"]), float(bounds["max_rating"])
selected_rating = st.sidebar.slider(
    "Rating Range (Stars)",
    min_value=min_r,
    max_value=max_r,
    value=(min_r, max_r),
    step=0.1,
)

df, executed_sql = query_filtered_data(
    selected_brands,
    selected_platforms,
    selected_keywords,
    selected_price,
    selected_rating,
)

with st.sidebar.expander("🧾 View Active SQL Query"):
    st.code(executed_sql, language="sql")

VIS_COL = "composite_visibility_score" if "composite_visibility_score" in df.columns else "rank_visibility_score"
DISC_COL = "category_discount_pct" if "category_discount_pct" in df.columns else "title_discount_pct"

st.title("📊 Brand Visibility & E-Commerce Intelligence Dashboard")
st.markdown("Analyze brand share of shelf, search ranking drivers, platform pricing, and discount trends directly from **MySQL**.")

if df.empty:
    st.warning("No products match your current SQL filter combination. Try widening your price/rating range or clearing filters.")
    st.stop()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "1️⃣ Overview",
    "2️⃣ Brand Insights",
    "3️⃣ Pricing Analysis",
    "4️⃣ Platform Analysis",
    "5️⃣ Visibility & Ranking",
    "6️⃣ Product Explorer",
])

with tab1:
    st.subheader("Market Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Products", f"{len(df):,}")
    c2.metric("Avg Price", f"${df['price'].mean():,.2f}")
    c3.metric("Avg Rating", f"{df['rating'].mean():.2f} ★")
    c4.metric("Total Reviews", f"{int(df['review'].sum()):,}")

    st.divider()
    col_a, col_b = st.columns(2)

    with col_a:
        fig_hist = px.histogram(
            df,
            x="price",
            nbins=30,
            title="Price Distribution",
            labels={"price": "Price ($)", "count": "Product Count"},
        )
        fig_hist.update_layout(xaxis_title="Price ($)", yaxis_title="Number of Products")
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_b:
        kw_counts = df["Product"].value_counts().reset_index().rename(columns={"count": "products"})
        fig_kw = px.bar(
            kw_counts,
            x="Product",
            y="products",
            text="products",
            title="Products per Keyword Category",
            labels={"Product": "Keyword / Category", "products": "Product Count"},
        )
        fig_kw.update_traces(textposition="outside")
        fig_kw.update_layout(xaxis_title="Keyword / Category", yaxis_title="Product Count")
        st.plotly_chart(fig_kw, use_container_width=True)

    plat_counts = df["platform"].value_counts()
    top_8_plats = plat_counts.head(8)
    other_count = plat_counts.iloc[8:].sum()
    pie_df = top_8_plats.reset_index().rename(columns={"count": "products"})
    if other_count > 0:
        pie_df = pd.concat(
            [pie_df, pd.DataFrame([{"platform": "Other Platforms", "products": other_count}])],
            ignore_index=True,
        )

    fig_pie = px.pie(
        pie_df,
        names="platform",
        values="products",
        hole=0.4,
        title="Platform Share of Listings",
    )
    fig_pie.update_traces(textinfo="label+percent")
    st.plotly_chart(fig_pie, use_container_width=True)

with tab2:
    st.subheader("Brand Performance & Share of Shelf")
    top_brand = df["Brand"].value_counts().idxmax()
    top_brand_count = df["Brand"].value_counts().max()
    avg_vis = df[VIS_COL].mean() if VIS_COL in df.columns else 0.0

    k1, k2 = st.columns(2)
    k1.metric("Top Brand (Most Listings)", f"{top_brand}", f"{top_brand_count} products")
    k2.metric("Avg Visibility Score", f"{avg_vis:.2f} / 100")

    st.divider()
    b_col1, b_col2 = st.columns(2)

    brand_agg = (
        df.groupby("Brand", as_index=False)
        .agg(
            product_count=("title", "count"),
            avg_rating=("rating", "mean"),
            avg_visibility=(VIS_COL, "mean") if VIS_COL in df.columns else ("rating", "mean"),
        )
        .sort_values(by="product_count", ascending=False)
    )

    with b_col1:
        fig_b_cnt = px.bar(
            brand_agg.head(15),
            x="Brand",
            y="product_count",
            text="product_count",
            title="Top 15 Brands vs. Product Count",
            labels={"Brand": "Brand", "product_count": "Product Count"},
        )
        fig_b_cnt.update_traces(textposition="outside")
        fig_b_cnt.update_layout(xaxis_title="Brand", yaxis_title="Product Count")
        st.plotly_chart(fig_b_cnt, use_container_width=True)

    with b_col2:
        fig_b_rat = px.bar(
            brand_agg.head(15).round(2),
            x="Brand",
            y="avg_rating",
            text="avg_rating",
            title="Top 15 Brands vs. Avg Rating",
            labels={"Brand": "Brand", "avg_rating": "Avg Rating (Stars)"},
        )
        fig_b_rat.update_traces(texttemplate="%{y} ★", textposition="outside")
        fig_b_rat.update_layout(xaxis_title="Brand", yaxis_title="Avg Rating (Stars)", yaxis_range=[0, 5.5])
        st.plotly_chart(fig_b_rat, use_container_width=True)

    top10_pos_df = df[df["position"].notna() & (df["position"] <= 10)]
    if not top10_pos_df.empty:
        top10_brands = (
            top10_pos_df["Brand"]
            .value_counts()
            .head(12)
            .reset_index()
            .rename(columns={"count": "top_10_count"})
        )
        fig_top10 = px.bar(
            top10_brands,
            x="Brand",
            y="top_10_count",
            text="top_10_count",
            color="top_10_count",
            title="Top Brands Appearing in Top 10 Search Positions (position <= 10)",
            labels={"Brand": "Brand", "top_10_count": "Top 10 Appearances"},
        )
        fig_top10.update_traces(textposition="outside")
        fig_top10.update_layout(xaxis_title="Brand", yaxis_title="Top 10 Appearances")
        st.plotly_chart(fig_top10, use_container_width=True)
    else:
        st.info("No ranked products with position <= 10 in the current filter selection.")

with tab3:
    st.subheader("Pricing Strategy & Discount Impact")
    pct_discounted = ((df[DISC_COL] > 0).mean() * 100) if DISC_COL in df.columns else 0.0

    p1, p2, p3 = st.columns(3)
    p1.metric("Avg Price", f"${df['price'].mean():,.2f}")
    p2.metric("Max Price", f"${df['price'].max():,.2f}")
    p3.metric("% Discounted Products", f"{pct_discounted:.1f}%")

    st.divider()
    fig_p_dist = px.box(
        df,
        x="Product",
        y="price",
        color="Product",
        title="Price Distribution Across Keyword Categories",
        labels={"Product": "Keyword Category", "price": "Price ($)"},
    )
    fig_p_dist.update_layout(showlegend=False, xaxis_title="Keyword Category", yaxis_title="Price ($)")
    st.plotly_chart(fig_p_dist, use_container_width=True)

    pr_col1, pr_col2 = st.columns(2)

    with pr_col1:
        ranked_sub = df[df["position"].notna()]
        if not ranked_sub.empty:
            fig_p_rank = px.scatter(
                ranked_sub,
                x="price",
                y="position",
                color="price_range" if "price_range" in df.columns else None,
                hover_data=["Brand", "title", "rating"],
                title="Price vs. Search Ranking (Lower Position = Better Rank)",
                labels={"price": "Price ($)", "position": "Search Rank Position"},
            )
            fig_p_rank.update_yaxes(autorange="reversed")
            fig_p_rank.update_layout(xaxis_title="Price ($)", yaxis_title="Search Rank Position")
            st.plotly_chart(fig_p_rank, use_container_width=True)
        else:
            st.info("No search ranking data available for current filters.")

    with pr_col2:
        fig_p_rat = px.scatter(
            df,
            x="price",
            y="rating",
            color="price_range" if "price_range" in df.columns else None,
            hover_data=["Brand", "title", "review"],
            title="Price vs. Customer Rating",
            labels={"price": "Price ($)", "rating": "Rating (Stars)"},
        )
        fig_p_rat.update_layout(xaxis_title="Price ($)", yaxis_title="Customer Rating (Stars)")
        st.plotly_chart(fig_p_rat, use_container_width=True)

with tab4:
    st.subheader("Retail Platform Comparison")
    plat_summary = (
        df.groupby("platform", as_index=False)
        .agg(
            product_count=("title", "count"),
            avg_price=("price", "mean"),
            avg_rating=("rating", "mean"),
        )
        .sort_values(by="product_count", ascending=False)
    )

    eligible_plats = plat_summary[plat_summary["product_count"] >= 3]
    if eligible_plats.empty:
        eligible_plats = plat_summary
    best_plat_row = eligible_plats.sort_values(by="avg_rating", ascending=False).iloc[0]

    pl1, pl2 = st.columns(2)
    pl1.metric("Total Platforms", f"{df['platform'].nunique()}")
    pl2.metric(
        "Best Platform (Avg Rating)",
        f"{best_plat_row['platform']}",
        f"{best_plat_row['avg_rating']:.2f} ★ ({int(best_plat_row['product_count'])} listings)",
    )

    st.divider()
    top_plats_df = plat_summary.head(12).round(2)

    fig_pl_cnt = px.bar(
        top_plats_df,
        x="platform",
        y="product_count",
        text="product_count",
        title="Top 12 Platforms vs. Product Count",
        labels={"platform": "Retail Platform", "product_count": "Product Count"},
    )
    fig_pl_cnt.update_traces(textposition="outside")
    fig_pl_cnt.update_layout(xaxis_title="Retail Platform", yaxis_title="Product Count")
    st.plotly_chart(fig_pl_cnt, use_container_width=True)

    pl_c1, pl_c2 = st.columns(2)
    with pl_c1:
        fig_pl_price = px.bar(
            top_plats_df.sort_values(by="avg_price", ascending=False),
            x="platform",
            y="avg_price",
            text="avg_price",
            title="Platform vs. Avg Price ($)",
            labels={"platform": "Retail Platform", "avg_price": "Avg Price ($)"},
        )
        fig_pl_price.update_traces(texttemplate="$%{y:.0f}", textposition="outside")
        fig_pl_price.update_layout(xaxis_title="Retail Platform", yaxis_title="Avg Price ($)")
        st.plotly_chart(fig_pl_price, use_container_width=True)

    with pl_c2:
        fig_pl_rat = px.bar(
            top_plats_df.sort_values(by="avg_rating", ascending=False),
            x="platform",
            y="avg_rating",
            text="avg_rating",
            title="Platform vs. Avg Rating (Stars)",
            labels={"platform": "Retail Platform", "avg_rating": "Avg Rating (Stars)"},
        )
        fig_pl_rat.update_traces(texttemplate="%{y} ★", textposition="outside")
        fig_pl_rat.update_layout(xaxis_title="Retail Platform", yaxis_title="Avg Rating (Stars)", yaxis_range=[0, 5.5])
        st.plotly_chart(fig_pl_rat, use_container_width=True)

with tab5:
    st.subheader("Search Ranking & Visibility Drivers")
    v1, v2 = st.columns(2)
    v1.metric("Avg Rating", f"{df['rating'].mean():.2f} ★")
    v2.metric("Avg Visibility Score", f"{df[VIS_COL].mean():.2f} / 100" if VIS_COL in df.columns else "N/A")

    st.divider()
    ranked_df = df[df["position"].notna()].copy()

    if ranked_df.empty:
        st.info("No ranked listings (with search position) match the active filters.")
    else:
        fig_rank_dist = px.histogram(
            ranked_df,
            x="position",
            nbins=20,
            title="Search Ranking Position Distribution",
            labels={"position": "Search Position (1 = Top Rank)", "count": "Number of Products"},
        )
        fig_rank_dist.update_layout(xaxis_title="Search Position (1 = Top Rank)", yaxis_title="Number of Products")
        st.plotly_chart(fig_rank_dist, use_container_width=True)

        vr_c1, vr_c2 = st.columns(2)
        with vr_c1:
            fig_rat_rank = px.scatter(
                ranked_df,
                x="rating",
                y="position",
                color="Brand",
                hover_data=["title", "platform", "price"],
                title="Customer Rating vs. Search Ranking",
                labels={"rating": "Customer Rating (Stars)", "position": "Search Rank Position"},
            )
            fig_rat_rank.update_yaxes(autorange="reversed")
            fig_rat_rank.update_layout(
                showlegend=False,
                xaxis_title="Customer Rating (Stars)",
                yaxis_title="Search Rank Position",
            )
            st.plotly_chart(fig_rat_rank, use_container_width=True)

        with vr_c2:
            fig_rev_bubble = px.scatter(
                ranked_df,
                x="review",
                y="position",
                size="review",
                color="rating",
                hover_data=["Brand", "title", "platform"],
                title="Reviews vs. Search Ranking (Bubble Size = Review Count)",
                labels={"review": "Review Count", "position": "Search Rank Position", "rating": "Rating"},
            )
            fig_rev_bubble.update_yaxes(autorange="reversed")
            fig_rev_bubble.update_layout(xaxis_title="Review Count", yaxis_title="Search Rank Position")
            st.plotly_chart(fig_rev_bubble, use_container_width=True)

with tab6:
    st.subheader("Interactive Product Explorer")

    search_col, toggle_col = st.columns([3, 1])
    with search_col:
        search_text = st.text_input(
            "🔎 Search Product Title or Brand",
            placeholder="Type e.g. Ninja, Air Fryer, Apple, Nike...",
        )
    with toggle_col:
        only_top_performers = st.checkbox(
            "🏆 Top Performers Only",
            help="Filter for Top 10 ranked or Visibility Score >= 70",
        )

    explorer_df = df.copy()

    if search_text.strip():
        mask = (
            explorer_df["title"].str.contains(search_text, case=False, na=False)
            | explorer_df["Brand"].str.contains(search_text, case=False, na=False)
        )
        explorer_df = explorer_df[mask]

    vis_cond = (explorer_df[VIS_COL] >= 70) if VIS_COL in explorer_df.columns else False
    explorer_df["Top_Performer"] = np.where(
        ((explorer_df["position"].notna()) & (explorer_df["position"] <= 10))
        | (vis_cond & (explorer_df["rating"] >= 4.5)),
        "🏆 Top Performer",
        "Standard",
    )

    if only_top_performers:
        explorer_df = explorer_df[explorer_df["Top_Performer"] == "🏆 Top Performer"]

    e1, e2, e3 = st.columns(3)
    e1.metric("Total Products (Filtered)", f"{len(explorer_df):,}")
    e2.metric("Avg Price (Filtered)", f"${explorer_df['price'].mean():,.2f}" if not explorer_df.empty else "$0.00")
    e3.metric("Avg Rating (Filtered)", f"{explorer_df['rating'].mean():.2f} ★" if not explorer_df.empty else "N/A")

    st.divider()

    display_cols = ["Top_Performer", "title", "Brand", "price", "rating", "review", "platform"]
    if DISC_COL in explorer_df.columns:
        display_cols.append(DISC_COL)
    if "position" in explorer_df.columns:
        display_cols.append("position")

    table_df = explorer_df[display_cols].rename(
        columns={
            "Top_Performer": "Status",
            "title": "Title",
            "price": "Price ($)",
            "rating": "Rating",
            "review": "Reviews",
            "platform": "Platform",
            DISC_COL: "Discount (%)",
            "position": "Search Rank",
        }
    )

    def highlight_top_rows(row):
        if row["Status"] == "🏆 Top Performer":
            return ["background-color: rgba(46, 204, 113, 0.18)"] * len(row)
        return [""] * len(row)

    st.dataframe(
        table_df.style.apply(highlight_top_rows, axis=1),
        use_container_width=True,
        height=500,
        hide_index=True,
    )
