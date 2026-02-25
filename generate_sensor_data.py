import numpy as np
import pandas as pd
from rocketpy import Environment, SolidMotor, Rocket, Flight
from rocketpy.sensors import Accelerometer, Barometer, Gyroscope, GnssReceiver

def generate_sensor_data(output_file="flight_computer_data.csv", freq_hz=200):
    # 1. Setup Simulation Environment
    env = Environment(latitude=32.990254, longitude=-106.974998, elevation=1400)
    env.set_atmospheric_model(type="standard_atmosphere")
    
    # 2. Setup Rocket
    # We create a simple motor with a synthetic thrust curve to avoid external files
    # Thrust curve: 3 seconds burn, constant 2000 N
    motor = SolidMotor(
        thrust_source="Cesaroni_4263L1350-P.eng",
        burn_time=3.284,
        grain_number=1,
        grain_density=1256.7753406541794,
        grain_initial_inner_radius=0.01875,
        grain_outer_radius=0.0375,
        grain_initial_height=0.486,
        nozzle_radius=0.028125,
        nozzle_position=0,
        throat_radius=0.01875,
        grain_separation=0,
        grains_center_of_mass_position=0.243,
        dry_inertia=(0, 0, 0),
        center_of_dry_mass_position=0,
        dry_mass=0,
    )

    rocket = Rocket(
        radius=0.047,
        mass=10.6462,
        inertia=(6.6986, 6.6986, 0.040824),
        power_off_drag=0.4, # Constant Cd to avoid external files
        power_on_drag=0.4,
        center_of_mass_without_motor=1.3957,
        coordinate_system_orientation="tail_to_nose"
    )
    rocket.set_rail_buttons(1.5957, 1.1957)
    rocket.add_motor(motor, position=0.7146163949)
    rocket.add_nose(length=0.27, kind="vonKarman", position=2.5214)
    rocket.add_trapezoidal_fins(
        n=4, root_chord=0.2, tip_chord=0.118, span=0.117, position=0.9134
    )

    parameters = {
        "cd_s_drogue": [1.0],
        "cd_s_main": [4.0],
        "lag_rec": [1.5]
    }
    
    drogue = rocket.add_parachute(
        "Drogue",
        cd_s=parameters.get("cd_s_drogue")[0],
        trigger="apogee",
        sampling_rate=105,
        lag=parameters.get("lag_rec")[0],
        noise=(0, 8.3, 0.5),
    )
    main = rocket.add_parachute(
        "Main",
        cd_s=parameters.get("cd_s_main")[0],
        trigger=300.00,
        sampling_rate=105,
        lag=parameters.get("lag_rec")[0],
        noise=(0, 8.3, 0.5),
    )

    # 3. Add Sensors to the Rocket
    # We configure them with sampling rates and variances to simulate realistic avionics noise.
    
    # Low-G Accelerometer
    acc = Accelerometer(
        sampling_rate=freq_hz, 
        name="LowG_Accel", 
        noise_variance=[0.01, 0.01, 0.01] # (m/s^2)^2
    )
    
    # High-G Accelerometer
    # Adding higher variance for realistic scale
    hacc = Accelerometer(
        sampling_rate=freq_hz, 
        name="HighG_Accel", 
        noise_variance=[0.25, 0.25, 0.25]
    )
    
    # Gyroscope
    gyro = Gyroscope(
        sampling_rate=freq_hz, 
        name="Gyro", 
        noise_variance=[0.0025, 0.0025, 0.0025] # (rad/s)^2
    )
    
    # Barometer
    baro = Barometer(
        sampling_rate=freq_hz, 
        name="Baro", 
        noise_variance=400.0 # Pa^2 (approx 0.2 hPa variance)
    )
    
    # GNSS Receiver
    gps = GnssReceiver(
        sampling_rate=freq_hz, 
        name="GPS", 
        position_accuracy=2.0, # meters variance conceptually
        altitude_accuracy=5.0
    )

    # Attach all to the rocket at the CG 
    rocket.add_sensor(acc, position=(0,0,0))
    rocket.add_sensor(hacc, position=(0,0,0))
    rocket.add_sensor(gyro, position=(0,0,0))
    rocket.add_sensor(baro, position=(0,0,0))
    rocket.add_sensor(gps, position=(0,0,0))

    # 4. Predict Flight
    # High inclination and a small rail for standard launch
    print(f"Simulating Flight with Sensors attached at {freq_hz} Hz...")
    flight = Flight(
        rocket=rocket, 
        environment=env, 
        rail_length=5.2, 
        inclination=85, 
        heading=0,
        terminate_on_apogee=False # Stop at apogee to keep data length reasonable
    )

    # 5. Extract Sensor Data
    # The sensors' self.measured_data contains tuples over time depending on the sensor type:
    # Accelerometer / Gyro: (time, x, y, z)
    # Barometer: (time, pressure, temperature) (Note: Baro gives pressure and temperature depending on implementation, let's look at it)
    # Depending on RocketPy version, the output tuple varies, let's assemble it robustly.
    
    # Turn Measured Data into DataFrames
    df_acc = pd.DataFrame(acc.measured_data, columns=["timestamp_s", "accx", "accz", "accy"]).set_index("timestamp_s")
    df_hacc = pd.DataFrame(hacc.measured_data, columns=["timestamp_s", "haccx", "haccz", "haccy"]).set_index("timestamp_s")
    df_gyro = pd.DataFrame(gyro.measured_data, columns=["timestamp_s", "gyrx", "gyrz", "gyry"]).set_index("timestamp_s")
    
    # Barometer usually returns (time, pressure_Pa). In RocketPy, measured_data is [time, P]
    # Let's verify the columns based on the first item
    baro_cols = ["timestamp_s", "baro_press"] # typically Pa
    if len(baro.measured_data[0]) > 2:
        baro_cols.append("baro_temp")
    df_baro = pd.DataFrame(baro.measured_data, columns=baro_cols).set_index("timestamp_s")
    
    # GPS usually returns (time, lat, lon, alt)
    df_gps = pd.DataFrame(gps.measured_data, columns=["timestamp_s", "latitude", "longitude", "gps_altitude"]).set_index("timestamp_s")

    # Combine all sensor Dataframes onto the same time index
    # We use join or concat since they all share the exact same timestamps generated by the 200 Hz sampling rate
    df = df_acc.join([df_gyro, df_hacc, df_baro, df_gps], how="outer")
    
    # Forward fill to handle any minute numerical sync issues, and reset index
    df = df.ffill().reset_index()

    # Clamp low-g accelerometer readings to +-16g (16 * 9.80665 m/s^2)
    acc_limit = 16 * 9.80665
    for col in ["accx", "accy", "accz"]:
        if col in df.columns:
            df[col] = df[col].clip(lower=-acc_limit, upper=acc_limit)

    # Clamp high-g accelerometer readings to +-320g (320 * 9.80665 m/s^2)
    hacc_limit = 320 * 9.80665
    for col in ["haccx", "haccy", "haccz"]:
        if col in df.columns:
            df[col] = df[col].clip(lower=-hacc_limit, upper=hacc_limit)

    # Clamp gyroscope readings to +-4000 dps (4000 * pi / 180 rad/s)
    gyro_limit = 4000 * np.pi / 180
    for col in ["gyrx", "gyry", "gyrz"]:
        if col in df.columns:
            df[col] = df[col].clip(lower=-gyro_limit, upper=gyro_limit)

    # 6. Format Data to output specification
    # User requested: timestamp_s,accy,accx,accz,gyrx,gyry,gyrz,haccy,haccx,haccz,baro_alt,baro_press,baro_temp,latitude,longitude,gps_altitude
    
    # Convert Units to Match Expected
    # Barometer is usually Pa, convert to hPa/mbar
    if "baro_press" in df.columns:
        df["baro_press"] /= 100.0
    
    # If Barometer didn't output temperature natively in the measured_data, we calculate it from altitude/environment
    if "baro_temp" not in df.columns:
        # Re-derive from flight model for mock data
        # using the z height which we get from gps or flight profile
        z_heights = [flight.z(t) for t in df["timestamp_s"]]
        temp_K = [env.temperature(env.elevation + z) for z in z_heights]
        # Adding some noise to match our previous mock format
        df["baro_temp"] = np.array(temp_K) - 273.15 + np.random.normal(0, 0.1, len(temp_K))
        
    # User format demands `baro_alt` which isn't natively measured by a barometer object but inferred
    # We will derive naive baro_alt from standard atmosphere pressure reverse
    # Altitude = 44330 * (1 - (P/P0)^(1/5.255))
    P0_hPa = env.pressure(env.elevation) / 100.0  # reference pad pressure
    df["baro_alt"] = 44330 * (1 - (df["baro_press"] / P0_hPa)**(1/5.255))
    
    # Format GPS coords (usually decimal degrees to huge int scale in raw avionics: 1e7)
    df["latitude"] *= 1e7
    df["longitude"] *= 1e7
    df["gps_altitude"] *= 1000 # mm
    
    # Reorder Columns
    expected_cols = [
        "timestamp_s","accy","accx","accz",
        "gyrx","gyry","gyrz",
        "haccy","haccx","haccz",
        "baro_alt","baro_press","baro_temp",
        "latitude","longitude","gps_altitude"
    ]
    df = df[expected_cols]

    # Save to CSV
    df.to_csv(output_file, index=False, float_format='%.6f')
    print(f"Successfully generated {output_file} from {len(df)} measurements.")

if __name__ == "__main__":
    generate_sensor_data()
