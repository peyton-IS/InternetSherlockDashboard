from google.ads.googleads.client import GoogleAdsClient
import pandas as pd
import streamlit as st
import calendar
from datetime import date, datetime

API_VERSION = "v24"
DEFAULT_BUDGET_FILE = "budgets.csv"

config = {
    "developer_token": st.secrets["developer_token"],
    "client_id": st.secrets["client_id"],
    "client_secret": st.secrets["client_secret"],
    "refresh_token": st.secrets["refresh_token"],
    "login_customer_id": st.secrets["login_customer_id"],
    "use_proto_plus": st.secrets["use_proto_plus"],
}

ACCOUNTS = [
    {"name": "Action Target - Range Site", "id": "5060680905"},
    {"name": "Action Target - Shop Site", "id": "5836612939"},
    {"name": "BCR Law Partners", "id": "5493058442"},
    {"name": "Davids Roofing", "id": "9720922890"},
    {"name": "Doors West - Main", "id": "4432784941"},
    {"name": "Everlight Roofing", "id": "6220466684"},
    {"name": "Everlight Solar", "id": "2180505076"},
    {"name": "Jewett Roofing", "id": "6433427355"},
    {"name": "North Kit Roofing - Primary", "id": "6533233386"},
    {"name": "Pinnacle Roofing - Lexington", "id": "2802577211"},
    {"name": "Pinnacle Roofing - Louisville", "id": "2905271937"},
    {"name": "Pope Tech", "id": "4094989713"},
    {"name": "Ready Set Grow - Main", "id": "8143425694"},
    {"name": "Snowy Peak Films", "id": "5295445807"},
    {"name": "Strength Roofing - Alabama", "id": "1511090156"},
    {"name": "Strength Roofing - Mississippi", "id": "7888320092"},
    {"name": "Tech Legion", "id": "3072478788"},
]

st.set_page_config(page_title="Google Ads Dashboard", layout="wide")
st.title("Google Ads MTD Spend Dashboard")


def default_budget_df():
    return pd.DataFrame([
        {"Account": a["name"], "Ads Budget": 0, "LSA Budget": 0}
        for a in ACCOUNTS
    ])


def clean_budget_df(df):
    required = ["Account", "Ads Budget", "LSA Budget"]

    for col in required:
        if col not in df.columns:
            if col == "Account":
                df[col] = ""
            else:
                df[col] = 0

    df = df[required].copy()
    df["Ads Budget"] = pd.to_numeric(df["Ads Budget"], errors="coerce").fillna(0)
    df["LSA Budget"] = pd.to_numeric(df["LSA Budget"], errors="coerce").fillna(0)

    return df


def get_expected_pct():
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return today.day / days_in_month * 100


def get_projected_spend(spend):
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return spend / today.day * days_in_month if today.day > 0 else 0


def get_pace_status(spend, budget):
    if budget <= 0:
        return "No Budget"

    expected_pct = get_expected_pct()
    actual_pct = spend / budget * 100
    projected = get_projected_spend(spend)

    if actual_pct > 110:
        return "Over Budget"

    if projected > budget * 1.10:
        return "Projected Over"

    if actual_pct < expected_pct - 10:
        return "Below Pace"

    return "On Pace"


def color_status(val):
    if val in ["Over Budget", "Projected Over"]:
        return "background-color: #ffd6d6; color: #111111; font-weight: 600;"
    if val == "Below Pace":
        return "background-color: #fff3cd; color: #111111; font-weight: 600;"
    if val == "On Pace":
        return "background-color: #d8f5dc; color: #111111; font-weight: 600;"
    return "color: inherit;"


@st.cache_data(ttl=300)
def load_spend_data():
    client = GoogleAdsClient.load_from_dict(config, version=API_VERSION)
    ga_service = client.get_service("GoogleAdsService")

    rows = []

    query = """
    SELECT
      customer.status,
      campaign.advertising_channel_type,
      metrics.cost_micros
    FROM campaign
    WHERE segments.date DURING THIS_MONTH
    """

    for account in ACCOUNTS:
        try:
            ads_spend = 0.0
            lsa_spend = 0.0
            status = "UNKNOWN"

            response = ga_service.search_stream(
                customer_id=account["id"],
                query=query
            )

            for batch in response:
                for row in batch.results:
                    spend = row.metrics.cost_micros / 1_000_000
                    channel = row.campaign.advertising_channel_type.name
                    status = row.customer.status.name

                    if channel == "LOCAL_SERVICES":
                        lsa_spend += spend
                    else:
                        ads_spend += spend

            rows.append({
                "Account": account["name"],
                "Account ID": account["id"],
                "Account Status": status,
                "Ads MTD": ads_spend,
                "LSA MTD": lsa_spend,
            })

        except Exception as e:
            rows.append({
                "Account": account["name"],
                "Account ID": account["id"],
                "Account Status": "ERROR",
                "Ads MTD": 0.0,
                "LSA MTD": 0.0,
                "Error": str(e)[:150],
            })

    return pd.DataFrame(rows)


def build_table(df, budget_col, spend_col):
    table = df[df["Account Status"] == "ENABLED"].copy()

    table["% Spent"] = table.apply(
        lambda r: r[spend_col] / r[budget_col] * 100
        if r[budget_col] > 0 else 0,
        axis=1
    )

    table["Projected Spend"] = table[spend_col].apply(get_projected_spend)

    table["Status"] = table.apply(
        lambda r: get_pace_status(r[spend_col], r[budget_col]),
        axis=1
    )

    return table[[
        "Account",
        budget_col,
        spend_col,
        "% Spent",
        "Projected Spend",
        "Status"
    ]].sort_values(spend_col, ascending=False)


dashboard_tab, lsa_tab, budget_tab = st.tabs(["Dashboard", "LSA", "Budgets"])

with budget_tab:
    st.subheader("Budget Source")

    budget_source = st.radio(
        "Choose how to load budgets",
        ["Upload CSV", "Google Sheet CSV URL", "Default blank budgets"]
    )

    budget_df = default_budget_df()

    if budget_source == "Upload CSV":
        uploaded_file = st.file_uploader("Upload budgets CSV", type=["csv"])

        if uploaded_file:
            budget_df = clean_budget_df(pd.read_csv(uploaded_file))
            st.success("Budget CSV loaded.")

    elif budget_source == "Google Sheet CSV URL":
        sheet_url = st.text_input(
            "Google Sheet CSV URL",
            help="Use a published/export CSV URL."
        )

        if sheet_url:
            try:
                budget_df = clean_budget_df(pd.read_csv(sheet_url))
                st.success("Google Sheet budgets loaded.")
            except Exception as e:
                st.error(f"Could not load Google Sheet: {e}")

    else:
        budget_df = default_budget_df()

    st.subheader("Current Budgets")
    st.dataframe(
        budget_df.style.format({
            "Ads Budget": "${:,.0f}",
            "LSA Budget": "${:,.0f}",
        }),
        use_container_width=True,
        hide_index=True
    )

st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if st.button("Refresh data now"):
    st.cache_data.clear()
    st.rerun()

spend_df = load_spend_data()

df = spend_df.merge(budget_df, on="Account", how="left")
df["Ads Budget"] = df["Ads Budget"].fillna(0)
df["LSA Budget"] = df["LSA Budget"].fillna(0)

with dashboard_tab:
    ads_table = build_table(df, "Ads Budget", "Ads MTD")

    st.metric("Total Ads MTD", f"${ads_table['Ads MTD'].sum():,.0f}")

    st.dataframe(
        ads_table.style
        .map(color_status, subset=["Status"])
        .format({
            "Ads Budget": "${:,.0f}",
            "Ads MTD": "${:,.0f}",
            "% Spent": "{:.0f}%",
            "Projected Spend": "${:,.0f}",
        }),
        use_container_width=True,
        hide_index=True
    )

with lsa_tab:
    lsa_table = build_table(df, "LSA Budget", "LSA MTD")

    st.metric("Total LSA MTD", f"${lsa_table['LSA MTD'].sum():,.0f}")

    st.dataframe(
        lsa_table.style
        .map(color_status, subset=["Status"])
        .format({
            "LSA Budget": "${:,.0f}",
            "LSA MTD": "${:,.0f}",
            "% Spent": "{:.0f}%",
            "Projected Spend": "${:,.0f}",
        }),
        use_container_width=True,
        hide_index=True
    )
