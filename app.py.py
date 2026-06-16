from google.ads.googleads.client import GoogleAdsClient
import pandas as pd
import streamlit as st
import os
import calendar
import smtplib
from email.mime.text import MIMEText
from datetime import date, datetime

API_VERSION = "v24"

BUDGET_FILE = "budgets.csv"
SETTINGS_FILE = "notification_settings.csv"
SENT_ALERTS_FILE = "sent_alerts.csv"

DEFAULT_EMAIL = "peyton@internetsherlock.com"

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


def load_budgets():
    if os.path.exists(BUDGET_FILE):
        df = pd.read_csv(BUDGET_FILE)

        if "Ads Budget" not in df.columns:
            df["Ads Budget"] = 0.0

        if "LSA Budget" not in df.columns:
            df["LSA Budget"] = 0.0

        return df[["Account", "Ads Budget", "LSA Budget"]]

    return pd.DataFrame([
        {"Account": a["name"], "Ads Budget": 0.0, "LSA Budget": 0.0}
        for a in ACCOUNTS
    ])


def save_budgets(df):
    df.to_csv(BUDGET_FILE, index=False)


def load_settings():
    defaults = {
        "notifications_enabled": True,
        "refresh_frequency": "Daily",
        "alert_threshold_percent": 10.0,
        "notification_emails": DEFAULT_EMAIL,
        "sender_email": DEFAULT_EMAIL,
        "app_password": "",
        "notify_over_budget": True,
        "notify_projected_over": True,
        "notify_below_pace": False,
    }

    if os.path.exists(SETTINGS_FILE):
        settings = pd.read_csv(SETTINGS_FILE).iloc[0].to_dict()

        for key, value in defaults.items():
            if key not in settings:
                settings[key] = value

        return settings

    return defaults


def save_settings(settings):
    pd.DataFrame([settings]).to_csv(SETTINGS_FILE, index=False)


def get_expected_pct():
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return today.day / days_in_month * 100


def get_projected_spend(spend):
    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return spend / today.day * days_in_month if today.day > 0 else 0


def get_pace_status(spend, budget, threshold_percent):
    if budget <= 0:
        return "No Budget"

    expected_pct = get_expected_pct()
    actual_pct = spend / budget * 100
    projected = get_projected_spend(spend)

    if actual_pct > 100 + threshold_percent:
        return "Over Budget"

    if projected > budget * (1 + threshold_percent / 100):
        return "Projected Over"

    if actual_pct < expected_pct - threshold_percent:
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


def parse_emails(email_string):
    return [
        email.strip()
        for email in str(email_string).split(",")
        if email.strip()
    ]


def send_email(subject, body, recipients):
    settings = load_settings()

    sender_email = str(settings.get("sender_email", "")).strip()
    app_password = str(settings.get("app_password", "")).strip()

    if not sender_email or not app_password:
        raise ValueError("Missing sender email or Gmail app password.")

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, app_password)
        server.send_message(msg)


def load_sent_alerts():
    if os.path.exists(SENT_ALERTS_FILE):
        return pd.read_csv(SENT_ALERTS_FILE)

    return pd.DataFrame(columns=["date", "account", "type", "status"])


def save_sent_alerts(df):
    df.to_csv(SENT_ALERTS_FILE, index=False)


def send_budget_alerts(alert_df, spend_type):
    if alert_df.empty:
        return 0

    settings = load_settings()

    recipients = parse_emails(settings.get("notification_emails", ""))

    if not recipients:
        return 0

    today_str = str(date.today())
    sent_df = load_sent_alerts()

    new_alerts = []

    for _, row in alert_df.iterrows():
        already_sent = (
            (sent_df["date"] == today_str)
            & (sent_df["account"] == row["Account"])
            & (sent_df["type"] == spend_type)
            & (sent_df["status"] == row["Status"])
        ).any()

        if not already_sent:
            new_alerts.append(row)

    if not new_alerts:
        return 0

    lines = [
        f"{spend_type} budget alerts for {today_str}",
        "",
        "The following accounts need attention:",
        "",
    ]

    for row in new_alerts:
        budget_col = f"{spend_type} Budget"
        spend_col = f"{spend_type} MTD"

        lines.append(
            f"{row['Account']}\n"
            f"Status: {row['Status']}\n"
            f"Budget: ${row[budget_col]:,.2f}\n"
            f"MTD Spend: ${row[spend_col]:,.2f}\n"
            f"% Spent: {row['% Spent']:.1f}%\n"
            f"Projected Spend: ${row['Projected Spend']:,.2f}\n"
        )

        sent_df.loc[len(sent_df)] = {
            "date": today_str,
            "account": row["Account"],
            "type": spend_type,
            "status": row["Status"],
        }

    subject = f"Budget Alert: {len(new_alerts)} {spend_type} account(s)"
    body = "\n".join(lines)

    send_email(subject, body, recipients)
    save_sent_alerts(sent_df)

    return len(new_alerts)


@st.cache_data(ttl=300)
def load_spend_data():
    client = GoogleAdsClient.load_from_storage("google-ads.yaml", version=API_VERSION)
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


def build_table(df, spend_type, budget_col, spend_col, threshold, settings):
    table = df[df["Account Status"] == "ENABLED"].copy()

    table["% Spent"] = table.apply(
        lambda r: r[spend_col] / r[budget_col] * 100
        if r[budget_col] > 0 else 0,
        axis=1
    )

    table["Projected Spend"] = table[spend_col].apply(get_projected_spend)

    table["Status"] = table.apply(
        lambda r: get_pace_status(r[spend_col], r[budget_col], threshold),
        axis=1
    )

    alert_statuses = []

    if bool(settings.get("notify_over_budget", True)):
        alert_statuses.append("Over Budget")

    if bool(settings.get("notify_projected_over", True)):
        alert_statuses.append("Projected Over")

    if bool(settings.get("notify_below_pace", False)):
        alert_statuses.append("Below Pace")

    alerts = table[
        (table[budget_col] > 0)
        & (table["Status"].isin(alert_statuses))
    ]

    clean_table = table[[
        "Account",
        budget_col,
        spend_col,
        "% Spent",
        "Projected Spend",
        "Status"
    ]].sort_values(spend_col, ascending=False)

    return clean_table, alerts


settings = load_settings()
threshold = float(settings["alert_threshold_percent"])

dashboard_tab, lsa_tab, budget_tab, settings_tab = st.tabs(
    ["Dashboard", "LSA", "Budgets", "Notification Settings"]
)

with settings_tab:
    st.subheader("Email Notifications")

    notifications_enabled = st.toggle(
        "Send email alerts",
        value=bool(settings.get("notifications_enabled", True))
    )

    sender_email = st.text_input(
        "Sender Gmail address",
        value=str(settings.get("sender_email", DEFAULT_EMAIL)),
        help="This Gmail account sends the alerts."
    )

    app_password = st.text_input(
        "Gmail app password",
        value=str(settings.get("app_password", "")),
        type="password",
        help="Use a Google App Password, not your normal Gmail password."
    )

    notification_emails = st.text_area(
        "Notification email recipient(s)",
        value=str(settings.get("notification_emails", DEFAULT_EMAIL)),
        help="Separate multiple emails with commas."
    )

    st.subheader("Alert Rules")

    refresh_frequency = st.selectbox(
        "How often should the dashboard check budgets?",
        ["Manual only", "Hourly", "Every 6 hours", "Every 12 hours", "Daily"],
        index=["Manual only", "Hourly", "Every 6 hours", "Every 12 hours", "Daily"].index(
            str(settings.get("refresh_frequency", "Daily"))
        )
    )

    alert_threshold_percent = st.number_input(
        "Alert threshold (%)",
        min_value=1.0,
        max_value=100.0,
        value=float(settings.get("alert_threshold_percent", 10.0)),
        step=1.0
    )

    notify_over_budget = st.checkbox(
        "Notify when account is over budget",
        value=bool(settings.get("notify_over_budget", True))
    )

    notify_projected_over = st.checkbox(
        "Notify when projected spend exceeds budget threshold",
        value=bool(settings.get("notify_projected_over", True))
    )

    notify_below_pace = st.checkbox(
        "Notify when account is below pacing",
        value=bool(settings.get("notify_below_pace", False))
    )

    if st.button("Save notification settings"):
        save_settings({
            "notifications_enabled": notifications_enabled,
            "refresh_frequency": refresh_frequency,
            "alert_threshold_percent": alert_threshold_percent,
            "notification_emails": notification_emails,
            "sender_email": sender_email,
            "app_password": app_password,
            "notify_over_budget": notify_over_budget,
            "notify_projected_over": notify_projected_over,
            "notify_below_pace": notify_below_pace,
        })
        st.success("Notification settings saved.")

    if st.button("Send test email"):
        try:
            recipients = parse_emails(notification_emails)
            send_email(
                "Google Ads Dashboard Test",
                "This is a test email from your Google Ads dashboard.",
                recipients
            )
            st.success("Test email sent.")
        except Exception as e:
            st.error(f"Test email failed: {e}")


with budget_tab:
    st.subheader("Monthly Budgets")

    budget_df = load_budgets()

    edited_budget_df = st.data_editor(
        budget_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "Ads Budget": st.column_config.NumberColumn(
                "Ads Budget",
                format="$%.2f",
                step=100.0
            ),
            "LSA Budget": st.column_config.NumberColumn(
                "LSA Budget",
                format="$%.2f",
                step=100.0
            ),
        }
    )

    if st.button("Save budgets"):
        save_budgets(edited_budget_df)
        st.success("Budgets saved.")


st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if st.button("Refresh data now"):
    st.cache_data.clear()
    st.rerun()


spend_df = load_spend_data()
budget_df = load_budgets()

df = spend_df.merge(budget_df, on="Account", how="left")
df["Ads Budget"] = df["Ads Budget"].fillna(0)
df["LSA Budget"] = df["LSA Budget"].fillna(0)


with dashboard_tab:
    ads_table, ads_alerts = build_table(
        df=df,
        spend_type="Ads",
        budget_col="Ads Budget",
        spend_col="Ads MTD",
        threshold=threshold,
        settings=settings,
    )

    st.metric("Total Ads MTD", f"${ads_table['Ads MTD'].sum():,.2f}")

    if not ads_alerts.empty:
        st.error(f"{len(ads_alerts)} Ads account(s) need attention.")

        if bool(settings.get("notifications_enabled", True)):
            try:
                sent_count = send_budget_alerts(ads_alerts, "Ads")
                if sent_count > 0:
                    st.success(f"Sent {sent_count} Ads alert email(s).")
            except Exception as e:
                st.error(f"Email alert failed: {e}")

    st.dataframe(
        ads_table.style
        .map(color_status, subset=["Status"])
        .format({
            "Ads Budget": "${:,.2f}",
            "Ads MTD": "${:,.2f}",
            "% Spent": "{:.1f}%",
            "Projected Spend": "${:,.2f}",
        }),
        use_container_width=True,
        hide_index=True
    )


with lsa_tab:
    lsa_table, lsa_alerts = build_table(
        df=df,
        spend_type="LSA",
        budget_col="LSA Budget",
        spend_col="LSA MTD",
        threshold=threshold,
        settings=settings,
    )

    st.metric("Total LSA MTD", f"${lsa_table['LSA MTD'].sum():,.2f}")

    if not lsa_alerts.empty:
        st.error(f"{len(lsa_alerts)} LSA account(s) need attention.")

        if bool(settings.get("notifications_enabled", True)):
            try:
                sent_count = send_budget_alerts(lsa_alerts, "LSA")
                if sent_count > 0:
                    st.success(f"Sent {sent_count} LSA alert email(s).")
            except Exception as e:
                st.error(f"Email alert failed: {e}")

    st.dataframe(
        lsa_table.style
        .map(color_status, subset=["Status"])
        .format({
            "LSA Budget": "${:,.2f}",
            "LSA MTD": "${:,.2f}",
            "% Spent": "{:.1f}%",
            "Projected Spend": "${:,.2f}",
        }),
        use_container_width=True,
        hide_index=True
    )