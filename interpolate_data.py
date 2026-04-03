import numpy as np
import pandas as pd

INPUT_FILE  = "sim_flight_data/packets_1.csv"
OUTPUT_FILE = "sim_flight_data/packets_1_200hz.csv"
INPUT_HZ    = 100   # nominal input rate
TARGET_HZ   = 200   # desired output rate

# ---------- Load original data ----------
df = pd.read_csv(INPUT_FILE, skipinitialspace=True)

# timestamp is in microseconds (absolute); convert to seconds from first sample
t_us = df["timestamp"].values.astype(np.float64)
t_original = (t_us - t_us[0]) / 1e6   # seconds from start

# ---------- Build uniform TARGET_HZ time base ----------
t_start = t_original[0]
t_end   = t_original[-1]
t_new   = np.arange(t_start, t_end, 1.0 / TARGET_HZ)

# ---------- Source → destination column mapping ----------
# keys   = column names in packets_1.csv
# values = column names required in the output CSV
COL_MAP = {
    "acc_y"          : "accy",
    "acc_x"          : "accx",
    "acc_z"          : "accz",
    "gyr_x"          : "gyrx",
    "gyr_y"          : "gyry",
    "gyr_z"          : "gyrz",
    "hacc_y"         : "haccy",
    "hacc_x"         : "haccx",
    "hacc_z"         : "haccz",
    "altitude_agl"   : "baro_alt",
    "pressure"       : "baro_press",
    "temperature"    : "baro_temp",
    "lat"            : "latitude",
    "lon"            : "longitude",
    "altitude_msl"   : "gps_altitude",
}

# Required output column order (must match exactly)
OUTPUT_COLUMNS = [
    "timestamp_s",
    "accy", "accx", "accz",
    "gyrx", "gyry", "gyrz",
    "haccy", "haccx", "haccz",
    "baro_alt", "baro_press", "baro_temp",
    "latitude", "longitude", "gps_altitude",
]

# ---------- Interpolate each source column and store under output name ----------
interpolated = {"timestamp_s": t_new}

for src_col, dst_col in COL_MAP.items():
    if src_col not in df.columns:
        print(f"WARNING: source column '{src_col}' not found — filling '{dst_col}' with zeros")
        interpolated[dst_col] = np.zeros(len(t_new))
    else:
        y = df[src_col].values.astype(np.float64)
        interpolated[dst_col] = np.interp(t_new, t_original, y)

# Build output DataFrame in the required column order
df_interp = pd.DataFrame(interpolated)[OUTPUT_COLUMNS]

print(f"Original    : {len(df):>7,} samples @ ~{INPUT_HZ} Hz, duration {t_end - t_start:.2f} s")
print(f"Interpolated: {len(df_interp):>7,} samples @ {TARGET_HZ} Hz, duration {t_new[-1] - t_new[0]:.2f} s")
print(f"Output columns: {list(df_interp.columns)}")

# ---------- Save interpolated CSV ----------
df_interp.to_csv(OUTPUT_FILE, index=False)
print(f"Saved interpolated data to {OUTPUT_FILE}")

# ---------- Optional: plot comparison (requires matplotlib) ----------
try:
    import matplotlib.pyplot as plt

    # Plot using output column names (already renamed in interpolated dict)
    plot_channels = [
        ("accx",      "Accelerometer X (m/s²)"),
        ("accy",      "Accelerometer Y (m/s²)"),
        ("accz",      "Accelerometer Z (m/s²)"),
        ("gyrx",      "Gyroscope X (°/s)"),
        ("baro_alt",  "Altitude AGL (m)"),
        ("baro_press","Barometric Pressure (hPa)"),
    ]
    plot_channels = [(c, l) for c, l in plot_channels if c in interpolated]

    fig, axes = plt.subplots(len(plot_channels), 1,
                             figsize=(14, 3.2 * len(plot_channels)),
                             sharex=True, constrained_layout=True)

    for ax, (col, label) in zip(axes, plot_channels):
        ax.scatter(t_original, df[col].values, s=4, alpha=0.5,
                   label=f"Original {INPUT_HZ} Hz", zorder=3)
        ax.plot(t_new, interpolated[col], linewidth=0.6, color="tab:orange",
                label=f"Interpolated {TARGET_HZ} Hz", zorder=2)
        ax.set_ylabel(label, fontsize=9)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, linewidth=0.3, alpha=0.6)

    axes[-1].set_xlabel("Time (s)")
    fig.suptitle(f"{INPUT_HZ} Hz Original vs {TARGET_HZ} Hz Linear Interpolation",
                 fontsize=13, fontweight="bold")
    plt.savefig("sim_flight_data/interpolation_comparison.png", dpi=150)
    print("Saved plot to sim_flight_data/interpolation_comparison.png")
    plt.show()

    # Zoomed-in view (first 2 seconds)
    zoom_end    = 2.0
    mask_orig   = t_original <= zoom_end
    mask_interp = t_new <= zoom_end

    fig2, axes2 = plt.subplots(len(plot_channels), 1,
                                figsize=(14, 3.2 * len(plot_channels)),
                                sharex=True, constrained_layout=True)

    for ax, (col, label) in zip(axes2, plot_channels):
        ax.scatter(t_original[mask_orig], df[col].values[mask_orig],
                   s=20, alpha=0.7, label=f"Original {INPUT_HZ} Hz",
                   zorder=3, edgecolors="k", linewidths=0.3)
        ax.plot(t_new[mask_interp], interpolated[col][mask_interp],
                linewidth=1.0, color="tab:orange",
                label=f"Interpolated {TARGET_HZ} Hz", zorder=2)
        ax.set_ylabel(label, fontsize=9)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, linewidth=0.3, alpha=0.6)

    axes2[-1].set_xlabel("Time (s)")
    fig2.suptitle(f"Zoomed: First {zoom_end:.0f}s — {INPUT_HZ} Hz vs {TARGET_HZ} Hz Interpolation",
                  fontsize=13, fontweight="bold")
    plt.savefig("sim_flight_data/interpolation_comparison_zoomed.png", dpi=150)
    print("Saved zoomed plot to sim_flight_data/interpolation_comparison_zoomed.png")
    plt.show()

except ImportError:
    print("matplotlib not available — skipping plots.")
