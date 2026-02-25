import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

TARGET_HZ = 200

# ---------- Load original data ----------
df = pd.read_csv("flight.csv")

# Convert timestamp from microseconds to seconds (relative to start)
t_us = df["timestamp"].values.astype(np.float64)
t_original = (t_us - t_us[0]) / 1e6  # seconds from launch

# ---------- Build uniform 200 Hz time base ----------
t_start = t_original[0]
t_end = t_original[-1]
t_200hz = np.arange(t_start, t_end, 1.0 / TARGET_HZ)

# Columns to interpolate (skip index 'n' and 'timestamp')
data_columns = [
    "accx", "accy", "accz",
    "gyrx", "gyry", "gyrz",
    "haccx", "haccy", "haccz",
    "baro_alt", "baro_press", "baro_temp",
    "latitude", "longitude", "gps_altitude",
]

# ---------- Interpolate each column ----------
interpolated = {"timestamp_s": t_200hz}

for col in data_columns:
    y = df[col].values.astype(np.float64)
    f = interp1d(t_original, y, kind="cubic", fill_value="extrapolate")
    interpolated[col] = f(t_200hz)

df_interp = pd.DataFrame(interpolated)

print(f"Original : {len(df):>7,} samples @ ~50 Hz, duration {t_end - t_start:.2f} s")
print(f"Interpolated: {len(df_interp):>7,} samples @ {TARGET_HZ} Hz, duration {t_200hz[-1] - t_200hz[0]:.2f} s")

# ---------- Save interpolated CSV ----------
df_interp.to_csv("flight_200hz.csv", index=False)
print("Saved interpolated data to flight_200hz.csv")

# ---------- Plot comparison ----------
# Pick a few representative channels to visualise
plot_channels = [
    ("accx", "Accelerometer X (m/s²)"),
    ("accy", "Accelerometer Y (m/s²)"),
    ("accz", "Accelerometer Z (m/s²)"),
    ("gyrx", "Gyroscope X (°/s)"),
    ("baro_alt", "Barometric Altitude (m)"),
    ("baro_press", "Barometric Pressure (hPa)"),
]

fig, axes = plt.subplots(len(plot_channels), 1, figsize=(14, 3.2 * len(plot_channels)),
                         sharex=True, constrained_layout=True)

for ax, (col, label) in zip(axes, plot_channels):
    # Original (scatter so individual samples are visible)
    ax.scatter(t_original, df[col].values, s=4, alpha=0.5, label="Original 50 Hz", zorder=3)
    # Interpolated (line)
    ax.plot(t_200hz, interpolated[col], linewidth=0.6, color="tab:orange",
            label="Interpolated 200 Hz", zorder=2)
    ax.set_ylabel(label, fontsize=9)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, linewidth=0.3, alpha=0.6)

axes[-1].set_xlabel("Time (s)")
fig.suptitle("50 Hz Original vs 200 Hz Cubic Interpolation", fontsize=13, fontweight="bold")
plt.savefig("interpolation_comparison.png", dpi=150)
print("Saved plot to interpolation_comparison.png")
plt.show()

# ---------- Zoomed-in view (first 2 seconds) ----------
zoom_end = 2.0  # seconds
mask_orig = t_original <= zoom_end
mask_interp = t_200hz <= zoom_end

fig2, axes2 = plt.subplots(len(plot_channels), 1, figsize=(14, 3.2 * len(plot_channels)),
                           sharex=True, constrained_layout=True)

for ax, (col, label) in zip(axes2, plot_channels):
    ax.scatter(t_original[mask_orig], df[col].values[mask_orig],
               s=20, alpha=0.7, label="Original 50 Hz", zorder=3, edgecolors="k", linewidths=0.3)
    ax.plot(t_200hz[mask_interp], interpolated[col][mask_interp],
            linewidth=1.0, color="tab:orange", label="Interpolated 200 Hz", zorder=2)
    ax.set_ylabel(label, fontsize=9)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, linewidth=0.3, alpha=0.6)

axes2[-1].set_xlabel("Time (s)")
fig2.suptitle(f"Zoomed: First {zoom_end:.0f}s — 50 Hz vs 200 Hz Interpolation",
              fontsize=13, fontweight="bold")
plt.savefig("interpolation_comparison_zoomed.png", dpi=150)
print("Saved zoomed plot to interpolation_comparison_zoomed.png")
plt.show()
