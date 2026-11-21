import glob
import os
import pandas as pd
import matplotlib.pyplot as plt
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

INPUT_DIR = "raw_shift_logs"
OUTPUT_DIR = "outputs"
ASSETS_DIR = "assets"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

csv_files = sorted(glob.glob(os.path.join(INPUT_DIR, "shift_log_*.csv")))
if not csv_files:
    raise FileNotFoundError(f"No CSV files found in '{INPUT_DIR}/'. Run generate_shift_logs.py first.")

raw_df = pd.concat([pd.read_csv(f) for f in csv_files], ignore_index=True)

validation_errors = raw_df[
    (raw_df["Downtime_Min"] < 0)
    | (raw_df["Downtime_Min"] > raw_df["Planned_Time_Min"])
    | (raw_df["Scrap_Units"] > raw_df["Total_Units"])
    | (raw_df["Total_Units"] < 0)
]

valid_df = raw_df.drop(validation_errors.index).copy()

valid_df["Operating_Time_Min"] = valid_df["Planned_Time_Min"] - valid_df["Downtime_Min"]
valid_df["Availability"] = valid_df["Operating_Time_Min"] / valid_df["Planned_Time_Min"]

ideal_units = (valid_df["Operating_Time_Min"] * 60) / valid_df["Ideal_Cycle_Sec"]
valid_df["Performance"] = (valid_df["Total_Units"] / ideal_units).fillna(0).clip(upper=1.0)

valid_df["Good_Units"] = valid_df["Total_Units"] - valid_df["Scrap_Units"]
valid_df["Quality"] = (valid_df["Good_Units"] / valid_df["Total_Units"]).fillna(0)

valid_df["OEE"] = valid_df["Availability"] * valid_df["Performance"] * valid_df["Quality"]

machine_summary = (
    valid_df.groupby("Machine_ID", as_index=False)
    .agg(
        Total_Shifts=("Date", "count"),
        Planned_Hours=("Planned_Time_Min", lambda x: round(x.sum() / 60, 1)),
        Downtime_Hours=("Downtime_Min", lambda x: round(x.sum() / 60, 1)),
        Total_Units=("Total_Units", "sum"),
        Scrap_Units=("Scrap_Units", "sum"),
        Availability=("Availability", "mean"),
        Performance=("Performance", "mean"),
        Quality=("Quality", "mean"),
        OEE=("OEE", "mean"),
    )
    .sort_values("OEE", ascending=True)
)

shift_matrix = (
    valid_df.pivot_table(
        index="Machine_ID",
        columns="Shift",
        values="OEE",
        aggfunc="mean",
    )
    .reindex(columns=["Morning", "Afternoon", "Night"])
    .reset_index()
)

downtime_pareto = (
    valid_df[valid_df["Downtime_Reason"] != "None"]
    .groupby("Downtime_Reason", as_index=False)
    .agg(
        Incidents=("Downtime_Min", "count"),
        Total_Downtime_Hours=("Downtime_Min", lambda x: round(x.sum() / 60, 1)),
    )
    .sort_values("Total_Downtime_Hours", ascending=False)
)

excel_path = os.path.join(OUTPUT_DIR, "Monthly_OEE_Executive_Report.xlsx")
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    machine_summary.to_excel(writer, sheet_name="Machine_OEE_Summary", index=False)
    shift_matrix.to_excel(writer, sheet_name="Shift_OEE_Matrix", index=False)
    downtime_pareto.to_excel(writer, sheet_name="Downtime_Pareto", index=False)
    valid_df.to_excel(writer, sheet_name="Validated_Shift_Logs", index=False)
    validation_errors.to_excel(writer, sheet_name="Audit_Rejected_Rows", index=False)

wb = load_workbook(excel_path)
header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
header_font = Font(color="FFFFFF", bold=True)
thin_border = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)

pct_columns = {"Availability", "Performance", "Quality", "OEE", "Morning", "Afternoon", "Night"}

for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    headers = [cell.value for cell in ws[1]]
    for col_idx, cell in enumerate(ws[1], start=1):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows(min_row=2):
        for col_idx, cell in enumerate(row, start=1):
            cell.border = thin_border
            if headers[col_idx - 1] in pct_columns and isinstance(cell.value, (int, float)):
                cell.number_format = "0.0%"
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = max_len + 4

wb.save(excel_path)

plt.style.use("seaborn-v0_8-whitegrid")

fig, ax = plt.subplots(figsize=(9, 4.8))
plot_df = shift_matrix.set_index("Machine_ID") * 100
plot_df.plot(kind="bar", ax=ax, color=["#2B5C8F", "#4F81BD", "#C0504D"], width=0.72)
ax.set_title("Monthly Average OEE (%) by Machine & Shift", fontsize=13, fontweight="bold", pad=12)
ax.set_ylabel("OEE (%)", fontsize=11)
ax.set_xlabel("")
ax.set_ylim(0, 105)
ax.axhline(85, color="#2E7D32", linestyle="--", linewidth=1.2, label="World-Class OEE Benchmark (85%)")
plt.xticks(rotation=0)
ax.legend(frameon=True, facecolor="white")
plt.tight_layout()
plt.savefig(os.path.join(ASSETS_DIR, "oee_by_machine_shift.png"), dpi=300)
plt.close()

fig, ax = plt.subplots(figsize=(8.5, 4.2))
pareto_sorted = downtime_pareto.sort_values("Total_Downtime_Hours", ascending=True)
bars = ax.barh(pareto_sorted["Downtime_Reason"], pareto_sorted["Total_Downtime_Hours"], color="#1F4E78", height=0.55)
ax.set_title("Total Unplanned Downtime Hours by Root Cause", fontsize=13, fontweight="bold", pad=12)
ax.set_xlabel("Downtime Hours (30-Day Period)", fontsize=11)
for bar in bars:
    width = bar.get_width()
    ax.text(width + 0.8, bar.get_y() + bar.get_height() / 2, f"{width:.1f} hrs", va="center", fontsize=10)
ax.set_xlim(0, pareto_sorted["Total_Downtime_Hours"].max() * 1.18)
plt.tight_layout()
plt.savefig(os.path.join(ASSETS_DIR, "downtime_pareto.png"), dpi=300)
plt.close()

print(f"Processed {len(csv_files)} daily logs ({len(valid_df)} valid rows, {len(validation_errors)} rejected).")
print(f"Excel report saved to: {excel_path}")
print(f"Charts saved to: {ASSETS_DIR}/")