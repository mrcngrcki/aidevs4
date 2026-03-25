import os
import json

def process_sensors():
    base_dir = "xxx"
    sensors_dir = os.path.join(base_dir, "sensors")
    output_file = os.path.join(base_dir, "valid_files.json")

    # Mapping field name to its range and the sensor type prefix
    norms = {
        "temperature": (553, 873, "temperature_K"),
        "pressure": (60, 160, "pressure_bar"),
        "water": (5.0, 15.0, "water_level_meters"),
        "voltage": (229.0, 231.0, "voltage_supply_v"),
        "humidity": (40.0, 80.0, "humidity_percent")
    }

    valid_files = []
    invalid_files = []

    if not os.path.exists(sensors_dir):
        print(f"Directory not found: {sensors_dir}")
        return

    files = [f for f in os.listdir(sensors_dir) if f.endswith(".json")]
    files.sort()

    for filename in files:
        filepath = os.path.join(sensors_dir, filename)
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                invalid_files.append(filename)
                continue

        sensor_type_str = data.get("sensor_type", "")
        active_sensors = [s.strip() for s in sensor_type_str.split("/") if s.strip()]

        is_valid = True
        
        for sensor_name, (low, high, field_name) in norms.items():
            value = data.get(field_name, 0)
            
            if sensor_name in active_sensors:
                if not (low <= value <= high):
                    is_valid = False
                    break
            else:
                if value != 0:
                    is_valid = False
                    break
        
        if is_valid:
            valid_files.append(filename)
        else:
            invalid_files.append(filename)

    with open(output_file, 'w') as f:
        json.dump(valid_files, f, indent=2)

    invalid_output_file = os.path.join(base_dir, "invalid_files.json")
    with open(invalid_output_file, 'w') as f:
        json.dump(invalid_files, f, indent=2)

    # Operator notes analysis
    # Structure: "note": ["list_of_files"]
    notes_mapping = {}
    for filename in valid_files:
        filepath = os.path.join(sensors_dir, filename)
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue
            
            note = data.get("operator_notes", "")
            if note:
                if note not in notes_mapping:
                    notes_mapping[note] = []
                notes_mapping[note].append(filename)

    notes_output_file = os.path.join(base_dir, "notes.json")
    with open(notes_output_file, 'w') as f:
        json.dump(notes_mapping, f, indent=2)

    print(f"Processed {len(files)} files.")
    print(f"Found {len(valid_files)} valid files. Saved to {output_file}")
    print(f"Found {len(invalid_files)} invalid files. Saved to {invalid_output_file}")
    print(f"Found {len(notes_mapping)} unique operator notes. Saved to {notes_output_file}")
    return valid_files, invalid_files, notes_mapping

if __name__ == "__main__":
    process_sensors()
