import numpy as np
import streamlit as st

import charts
from core import CATEGORIES, HELP, ICONS, SHORT, STREAMS, classify, load, ordered, shortlist

st.set_page_config(page_title="DU College & Course Predictor", layout="wide")
data = load()

st.title("DU College & Course Predictor")
st.caption("Built on the official 2026 Round 1, Round 2 and Spot Round cutoffs, with 2025 as the trend check. Use it to plan 2027 admissions.")

# ---------- Sidebar: your score + filters ----------
cats = [c for c in CATEGORIES if c in data["category"].unique()]
with st.sidebar:
    score = st.number_input("Your CUET score (out of 1000)", 0.0, 1000.0, 700.0, 1.0)
    category = st.selectbox("Category", cats, format_func=CATEGORIES.get)
    streams = st.multiselect("Stream", STREAMS, placeholder="All streams")
    ctype = st.radio("College type", ["All", "Women's colleges", "Co-ed colleges"])
    evening = st.toggle("Include evening colleges", True)
    query = st.text_input("Search course or college", placeholder="e.g. computer science, hindu")

d = data[data["category"] == category]
if streams:
    d = d[d["stream"].isin(streams)]
if ctype != "All":
    d = d[d["college"].str.contains(r"\(W\)") == (ctype == "Women's colleges")]
if not evening:
    d = d[~d["college"].str.contains("Evening")]
for word in query.lower().split():
    d = d[(d["college"] + " " + d["course"]).str.lower().str.contains(word, regex=False)]
res = classify(d, score)  # adds tier, margin, verdict

NUM = st.column_config.NumberColumn
CONFIG = {"verdict": "Verdict", "college": "College", "course": "Course",
          "r1": NUM("Round 1 cutoff", format="%.1f", help="2026 Round 1 minimum allocation score"),
          "margin": NUM("Your margin", format="%+.1f", help="Your score minus the Round 1 cutoff"),
          "r2": NUM("Round 2 cutoff", format="%.1f"), "spot": NUM("Spot cutoff", format="%.1f"),
          "r1_25": NUM("2025 R1 (ref.)", format="%.1f"), "yoy": NUM("Δ vs 2025", format="%+.1f")}


def show(df, columns, **kw):
    st.dataframe(df[columns], hide_index=True, width="stretch", column_config=CONFIG, **kw)


tab_pred, tab_cmp, tab_trend, tab_col, tab_about = st.tabs(["Predictor", "Compare colleges", "Trends", "Colleges", "About the data"])

# ---------- Predictor ----------
with tab_pred:
    counts = res["tier"].value_counts()
    tier = st.segmented_control("Show", [0, 1, 2, 3], default=0, label_visibility="collapsed",
                                format_func=lambda i: f"{ICONS[i]} {SHORT[i]} ({counts.get(i, 0)})") or 0
    st.caption(f"{len(res):,} programmes match in {CATEGORIES[category]}. {HELP[tier]} {counts.get(4, 0)} more are out of reach (hidden).")
    out = ordered(res[res["tier"] == tier])
    show(out, ["verdict", "college", "course", "r1", "margin", "r2", "spot", "r1_25", "yoy"], height=460)
    st.download_button("⬇️ Download these results (CSV)", out.to_csv(index=False), "du_predictions.csv", "text/csv")

    st.subheader("Smart shortlist")
    st.caption("In priority order: colleges you are safe at in Round 1, then close Round 1 calls, Round 2 plays and reaches. One course per college in each bucket.")
    k = st.slider("Picks per bucket", 3, 8, 5)
    for col, (name, picks) in zip(st.columns(4), shortlist(res, k).items()):
        col.markdown(f"**{name}**")
        for r in picks.itertuples():
            r2 = f" · R2 {r.r2:.0f}" if r.r2 == r.r2 else ""
            col.container(border=True).markdown(f"**{r.college}**  \n{r.course}  \nRound 1 cutoff {r.r1:.0f}{r2}")
        if picks.empty:
            col.caption("Nothing in this bucket")

# ---------- Compare one course across colleges ----------
with tab_cmp:
    st.subheader("One course, every college")
    pool = res.dropna(subset=["r1"])
    courses = sorted(pool["course"].unique())
    if courses:
        favourite = "B.Sc. (Hons.) Computer Science"
        course = st.selectbox("Course (type to search)", courses, index=courses.index(favourite) if favourite in courses else 0)
        one = pool[pool["course"] == course]
        st.plotly_chart(charts.ladder(one, score), width="stretch")
        st.caption("Grey line = how far the cutoff fell from Round 1 to Round 2. Hollow circle = 2025 Round 1, for pattern only.")
        show(one.sort_values("r1"), ["verdict", "college", "r1", "r2", "spot", "r1_25", "yoy"])
    else:
        st.info("No programmes match the current filters.")

# ---------- Trends ----------
with tab_trend:
    tcat = st.selectbox("Category for trends", cats, format_func=CATEGORIES.get, key="tcat")
    t = data[data["category"] == tcat]
    both = t.dropna(subset=["yoy"])  # courses present in both years
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Programmes in both years", len(both))
    c2.metric("Median change, 2025→2026 R1", f"{both['yoy'].median():+.1f}")
    c3.metric("Programmes that rose", f"{(both['yoy'] > 0).mean():.0%}")
    c4.metric("Median Round 1→2 change", f"{t['r1_to_r2'].median():+.1f}")
    left, right = st.columns(2)
    
    st.plotly_chart(charts.year_scatter(both), width="stretch")
    left, right = st.columns(2)
    
    main = data[data["category"].isin(["UR", "EWS", "OBC", "SC", "ST"])]
    right.markdown("**Median 2026 Round 1 cutoff by category**")
    right.bar_chart(main.groupby("category")["r1"].median().reindex(["UR", "EWS", "OBC", "SC", "ST"]).round(1))

# ---------- Colleges ----------
with tab_col:
    ccat = st.selectbox("Category", cats, format_func=CATEGORIES.get, key="ccat")
    cd = data[data["category"] == ccat]
    summary = cd.groupby("college").agg(programmes=("course", "count"), median_r1=("r1", "median"), highest=("r1", "max"),
                                        lowest=("r1", "min"), yoy=("yoy", "median")).reset_index()
    summary["type"] = np.where(summary["college"].str.contains(r"\(W\)"), "Women's", "Co-ed")
    search = st.text_input("Search colleges", key="cq")
    summary = summary[summary["college"].str.contains(search, case=False, regex=False)]
    st.dataframe(summary.sort_values("median_r1", ascending=False)[["college", "type", "programmes", "median_r1", "highest", "lowest", "yoy"]],
                 hide_index=True, width="stretch", height=380,
                 column_config={"college": "College", "type": "Type",
                                "programmes": NUM("Courses with cutoffs", format="%d", help="Courses at this college with a 2026 Round 1 cutoff in the selected category"),
                                "median_r1": NUM("Median 2026 R1", format="%.0f"), "highest": NUM("Highest", format="%.0f"),
                                "lowest": NUM("Lowest", format="%.0f"), "yoy": NUM("Median Δ vs 2025", format="%+.1f")})
    st.caption("Courses with cutoffs = how many courses at that college have a 2026 Round 1 cutoff in the selected category, so it changes with the category. It is not a rank or a score.")
    pick = st.selectbox("Open a college", sorted(summary["college"]))
    show(ordered(classify(cd[cd["college"] == pick], score)).sort_values("tier", kind="stable"), ["verdict", "course", "r1", "r2", "spot", "r1_25"])

# ---------- About ----------
with tab_about:
    st.markdown(f"""
**Data.** Official DU minimum allocation scores: 2026 Round 1, Round 2 and Spot Round (primary), 2025 Round 1 (reference and trends).
{len(data):,} college × course × category records, {data['college'].nunique()} colleges, {data['course'].nunique()} courses.

**Verdicts** (judged against 2026): 🟢 score ≥ Round 1 cutoff · 🟡 ≥ Round 2 cutoff · 🔵 ≥ Spot cutoff · 🟠 within 30 marks below the Round 2 cutoff · ⚪ further below.
"Safe" means 15+ marks above the Round 1 cutoff. Both numbers are constants at the top of `core.py`.

**Caveats.** Spot cutoffs exist only where seats remained, so treat them as a bonus. Some BA Programme combinations were renamed between years.
Two years of data show a pattern, not a forecast. Confirm on the official DU CSAS portal.

**Updating.** Put the new PDFs in a folder and run `python scripts/build_data.py <folder>`.
""")
