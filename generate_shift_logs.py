import os
import random
from datetime import datetime, timedelta
import pandas as pd

output_dir = "raw_shift_logs"
os.makedirs(output_dir, exist_ok=True)

machines = ["CNC-Mill-01", "CNC-Mill-02", "Press-Line-A", "Assembly-Cell-B"]
shifts = ["Morning", "Afternoon", "Night"]
downtime_reasons = [
    "None",
    "Tooling Changeover",
    "Unplanned Maintenance",
    "Material Starvation",
    "Sensor Calibration",
]

start_date = datetime(2026, 10, 1)
random.seed(42)

for day in range(30):
    current_date = start_date + timedelta(days=day)
    date_str = current_date.strftime("%Y-%m-%d")
    records = []

    for shift in shifts:
        for machine in machines:
            planned_time_min = 480  # 8-hour shift

            # Inject realistic bottleneck on Press-Line-A during Night shift
            if machine == "Press-Line-A" and shift == "Night":
                downtime_min = random.randint(45, 110)
                reason = random.choice(["Unplanned Maintenance", "Sensor Calibration"])
            else:
                downtime_min = random.choices([0, random.randint(10, 40)], weights=[0.6, 0.4])[0]
                reason = "None" if downtime_min == 0 else random.choice(downtime_reasons[1:])

            operating_time_min = planned_time_min - downtime_min
            ideal_cycle_time_sec = 30  # 2 units per minute ideal rate

            performance_factor = random.uniform(0.88, 0.99)
            total_units = int((operating_time_min * 60 / ideal_cycle_time_sec) * performance_factor)

            defect_rate = random.uniform(0.01, 0.045)
            scrap_units = int(total_units * defect_rate)

            records.append({
                "Date": date_str,
                "Shift": shift,
                "Machine_ID": machine,
                "Planned_Time_Min": planned_time_min,
                "Downtime_Min": downtime_min,
                "Downtime_Reason": reason,
                "Ideal_Cycle_Sec": ideal_cycle_time_sec,
                "Total_Units": total_units,
                "Scrap_Units": scrap_units
            })

    df = pd.DataFrame(records)
    file_path = os.path.join(output_dir, f"shift_log_{date_str}.csv")
    df.to_csv(file_path, index=False)

print(f"Generated 30 daily shift log CSVs in '{output_dir}/'.")