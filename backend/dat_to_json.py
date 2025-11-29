import json
import os


def parse_file1(dat_path):
    with open(dat_path, "r") as f:
        lines = f.readlines()

    day_of_period = 0
    period = 0
    num_drom = 0
    trips = []
    num_type_group = []
    list_type_group = []
    min_delay = []
    dian_dial_size = 0
    dian_dial_start_idx = 0
    dian_dial = []
    num_driver_bus = 0
    list_driver_bus = []
    num_proh_bus = 0
    proh_bus = []
    num_proh_drivers = 0
    proh_drivers = []

    in_trips = False
    in_type_group = False
    in_dian_dial = False
    in_driver_bus = False
    in_proh_bus = False
    in_proh_drivers = False

    for i, line in enumerate(lines):
        line = line.strip()
        if line == "[DayOfPeriod]":
            day_of_period = int(lines[i + 1].strip())
        elif line == "[Period]":
            period = int(lines[i + 1].strip())
        elif line == "[NumOfDrom]":
            num_drom = int(lines[i + 1].strip())
        elif line == "[ListOfDrom]":
            in_trips = True
        elif line == "[NumOfTypeGroup]":
            num_type_group = lines[i + 1].strip().split()
        elif line == "[ListOfTypeGroup]":
            in_type_group = True
            in_trips = False
        elif line == "[MinDelay]":
            min_delay = [lines[i + 1].strip()] + lines[i + 2].strip().split()
            in_type_group = False
        elif line == "[DianDial]":
            in_dian_dial = True
            dian_dial_size = int(lines[i + 1].strip())
            dian_dial_start_idx = i + 2
        elif line == "[NumOfDriverBus]":
            num_driver_bus = int(lines[i + 1].strip())
            in_dian_dial = False
        elif line == "[ListOfDriverBus]":
            in_driver_bus = True
        elif line == "[NumOfProhBus]":
            num_proh_bus = int(lines[i + 1].strip())
            in_driver_bus = False
        elif line == "[ListProhBus]":
            in_proh_bus = True
        elif line == "[NumOfProhDrivers]":
            num_proh_drivers = int(lines[i + 1].strip())
            in_proh_bus = False
        elif line == "[ListProhDrivers]":
            in_proh_drivers = True
            in_proh_bus = False
        elif in_trips and line and not line.startswith("["):
            parts = line.split()
            if len(parts) >= 27:
                start_time = parts[8]
                end_time = parts[9]
                raw_start_hour = int(start_time[:2])
                start_min = int(start_time[2:])
                raw_end_hour = int(end_time[:2])
                end_min = int(end_time[2:])

                start_day = raw_start_hour // 24
                end_day = raw_end_hour // 24
                start_hour = raw_start_hour % 24
                end_hour = raw_end_hour % 24

                raw_start_time = int(start_time)

                duration = (end_hour * 60 + end_min) - (start_hour * 60 + start_min)
                if duration < 0:
                    duration += 24 * 60

                road_type_map = {0: "NORMAL", 1: "DIRT", 2: "INTERCITY"}
                road_type = road_type_map.get(int(parts[23]), "NORMAL")

                shift_position_map = {
                    0: "ANY",
                    1: "MUST_BE_FIRST",
                    2: "WHOLE_SHIFT",
                    3: "MUST_BE_LAST",
                }
                shift_position = shift_position_map.get(int(parts[24]), "ANY")

                rest_rule_map = {
                    0: "NONE",
                    1: "NO_REST_TOMORROW",
                    2: "MUST_REST_TOMORROW",
                    3: "NO_REST_YESTERDAY",
                    4: "MUST_REST_YESTERDAY",
                }
                rest_rule = rest_rule_map.get(int(parts[25]), "NONE")

                allowed_bus_types = [
                    parts[i] for i in range(11, 21) if parts[i] != "00"
                ]

                start_minutes = (start_day * 1440) + (start_hour * 60) + start_min
                end_minutes = (end_day * 1440) + (end_hour * 60) + end_min

                if end_minutes <= start_minutes:
                    end_minutes += 1440

                trip = {
                    "id": parts[0], 
                    "startStation": parts[1],
                    "endStation": parts[2],
                    "start_time": f"{start_hour:02d}:{start_min:02d}",
                    "end_time": f"{end_hour:02d}:{end_min:02d}",
                    "start_minutes": start_minutes,
                    "end_minutes": end_minutes,
                    "rawStartTime": raw_start_time,  
                    "dayOffset": start_day,  
                    "alternativeStationCodes": [
                        parts[i] for i in range(3, 8) if parts[i] != "000"
                    ],
                    "distance": int(parts[10]),
                    "allowedBusTypes": allowed_bus_types,
                    "specificBusOverrides": (
                        [parts[22], parts[23]]
                        if parts[22] != "000" or parts[23] != "000"
                        else []
                    ),
                    "group": parts[21],
                    "roadType": road_type,
                    "shiftPosition": shift_position,
                    "nextDayRestRule": rest_rule,
                    "daysToRestRule": int(parts[26]),
                }
                trips.append(trip)
        elif in_type_group and line and not line.startswith("["):
            if line.strip():
                list_type_group.append(line)
        elif (
            in_dian_dial
            and i >= dian_dial_start_idx
            and line
            and not line.startswith("[")
            and len(dian_dial) < dian_dial_size
        ):
            if line.strip():
                row = [int(x) for x in line.split()]
                if row:
                    dian_dial.append(row)
        elif in_driver_bus and line and not line.startswith("["):
            if line.strip():
                list_driver_bus.append(line.split())
        elif in_proh_bus and line and not line.startswith("["):
            if line.strip():
                proh_bus.append(line)
        elif in_proh_drivers and line and not line.startswith("["):
            if line.strip():
                proh_drivers.append(line)

    return {
        "dayOfPeriod": day_of_period,
        "period": period,
        "numberOfTrips": num_drom,
        "trips": trips,
        "numberOfTypeGroup": num_type_group,
        "listOfTypeGroup": list_type_group,
        "minDelay": min_delay,
        "dianDial": dian_dial,
        "numberOfDriverBus": num_driver_bus,
        "listOfDriverBus": list_driver_bus,
        "numberOfProhibitedBuses": num_proh_bus,
        "prohibitedBuses": proh_bus,
        "numberOfProhibitedDrivers": num_proh_drivers,
        "prohibitedDrivers": proh_drivers,
    }


def parse_file2(dat_path):
    with open(dat_path, "r") as f:
        lines = f.readlines()

    num_wishes = 0
    wishes = []
    num_second_shifts = 0
    second_shifts = []
    bus_to_home = ""

    in_wishes = False
    in_second_shifts = False

    for i, line in enumerate(lines):
        line = line.strip()
        if line == "[NumOfWishes]":
            num_wishes = int(lines[i + 1].strip())
        elif line == "[ListWishes]":
            in_wishes = True
        elif line == "[NumOfSecondShifts]":
            num_second_shifts = int(lines[i + 1].strip())
            in_wishes = False
        elif line == "[ListOfSecondShifts]":
            in_second_shifts = True
        elif line == "[BusToHome]":
            bus_to_home = lines[i + 1].strip()
            in_second_shifts = False
        elif in_wishes and line and not line.startswith("["):
            if line.strip():
                wishes.append(line.split())
        elif in_second_shifts and line and not line.startswith("["):
            if line.strip():
                second_shifts.append(line.split())

    return {
        "numberOfWishes": num_wishes,
        "wishes": wishes,
        "numberOfSecondShifts": num_second_shifts,
        "secondShifts": second_shifts,
        "busToHome": bus_to_home,
    }


def parse_file3(dat_path):
    with open(dat_path, "r") as f:
        lines = f.readlines()

    num_pairs = 0
    pairs = []
    num_joints = 0
    joints = []

    in_pairs = False
    in_joints = False

    for line in lines:
        line = line.strip()
        if line.startswith("//"):
            continue
        if line == "[Pairs]":
            in_pairs = True
        elif line == "[Joints]":
            in_joints = True
            in_pairs = False
        elif in_pairs and line.isdigit() and not in_joints:
            num_pairs = int(line)
        elif in_joints and line.isdigit() and num_joints == 0:
            num_joints = int(line)
        elif in_joints and line and not line.startswith("["):
            parts = line.split()
            if len(parts) == 3:
                joints.append([parts[0], parts[1], int(parts[2])])
        elif in_pairs and line and not line.startswith("[") and not line.isdigit():
            if line.strip():
                pairs.append(line.split())

    return {
        "numberOfPairs": num_pairs,
        "pairs": pairs,
        "numberOfJoints": num_joints,
        "joints": joints,
    }


def transform_to_structured_format(file1_data, file2_data, file3_data, file4_data):
    connection_map = {1: "NONE", 2: "BREAK", 3: "OVERNIGHT"}

    station_matrix = []
    dian_dial_data = file1_data.get("dianDial", [])
    for row in dian_dial_data:
        descriptive_row = [connection_map.get(val, "UNKNOWN") for val in row]
        station_matrix.append(descriptive_row)

    structured_trips = []
    trip_by_raw_time = {}

    for trip in file1_data.get("trips", []):
        duration = trip["end_minutes"] - trip["start_minutes"]
        if duration < 0:
            duration += 24 * 60

        structured_trip = {
            "id": trip["id"],
            "startStation": trip["startStation"],
            "endStation": trip["endStation"],
            "start_time": trip["start_time"],
            "end_time": trip["end_time"],
            "start_minutes": trip["start_minutes"],
            "end_minutes": trip["end_minutes"],
            "dayOffset": trip.get("dayOffset", 0),
            "time": {
                "start": trip["start_time"],
                "end": trip["end_time"],
                "durationMinutes": duration,
            },
            "classification": {
                "group": trip.get("group", "000"),
                "roadType": trip.get("roadType", "NORMAL"),
                "allowedBusTypes": trip.get("allowedBusTypes", ["07"]),
                "specificBusOverrides": trip.get("specificBusOverrides", []),
            },
            "properties": {
                "distance": trip.get("distance", 0),
                "alternativeStationCodes": trip.get("alternativeStationCodes", []),
                "constraints": {
                    "shiftPosition": trip.get("shiftPosition", "ANY"),
                    "nextDayRestRule": trip.get("nextDayRestRule", "NONE"),
                    "daysToRestRule": trip.get("daysToRestRule", 0),
                },
            },
        }
        structured_trips.append(structured_trip)

        raw_time = trip.get("rawStartTime", 0)
        trip_by_raw_time[(trip["id"], raw_time)] = structured_trip

    resources = []
    for driver_bus in file1_data.get("listOfDriverBus", []):
        if len(driver_bus) >= 20:
            preassigned_breaks = []
            for i in range(4):
                duration_col = 6 + i  
                day_col = 10 + i  
                duration = (
                    int(driver_bus[duration_col])
                    if duration_col < len(driver_bus)
                    else 0
                )
                day_index = int(driver_bus[day_col]) if day_col < len(driver_bus) else 0
                preassigned_breaks.append(
                    {"durationMinutes": duration, "dayIndex": day_index}
                )
            cost = int(driver_bus[-1]) if len(driver_bus) > 0 else 0  # 125
            distance_adjustment = (
                int(driver_bus[-2]) if len(driver_bus) >= 2 else 0
            )  # 1
            exclude_from_eq = int(driver_bus[-3]) if len(driver_bus) >= 3 else 0  # 1
            bus_type = driver_bus[-4] if len(driver_bus) >= 4 else "01"  # 01
            compatibility = (
                driver_bus[-5] if len(driver_bus) >= 5 else "+000000"
            )  # +000000
            bus_id = driver_bus[-6] if len(driver_bus) >= 6 else "000"  # 075
            is_ktel = int(driver_bus[17]) if len(driver_bus) > 17 else 0

            resource = {
                "driverId": driver_bus[0],
                "busId": bus_id,
                "homeStation": driver_bus[2],  # Home station
                "currentStation": driver_bus[1],  # Current/bus station
                "shiftStartTime": driver_bus[3],
                "busAttributes": {
                    "type": bus_type,
                    "isKtel": is_ktel,
                    "excludeFromEq": exclude_from_eq,
                    "distanceAdjustment": distance_adjustment,
                },
                "preassignedBreaks": preassigned_breaks,
                "parameters": {
                    "cost": cost,
                    "compatibility": compatibility,
                },
            }
            resources.append(resource)

    prohibited_buses = []
    for bus_id in file1_data.get("prohibitedBuses", []):
        prohibited_buses.append(bus_id)

    prohibited_drivers = []
    for driver_id in file1_data.get("prohibitedDrivers", []):
        prohibited_drivers.append(driver_id)

    driver_wishes = []
    for wish in file2_data.get("wishes", []):
        if len(wish) >= 2:
            driver_wishes.append(
                {"driverId": wish[0], "tripId": wish[1], "preferenceLevel": 1}
            )

    mandatory_sequences = []
    for pair in file3_data.get("pairs", []):
        if len(pair) >= 2:
            mandatory_sequences.append(
                {
                    "description": "List of trips that must be done in order.",
                    "tripIds": [pair[0], pair[1]],
                }
            )

    mandatory_connections = []
    for joint in file3_data.get("joints", []):
        if len(joint) >= 3:
            mandatory_connections.append(
                {
                    "description": "Specific connection times required between trips.",
                    "incomingTripId": joint[0],
                    "outgoingTripId": joint[1],
                    "time": joint[2],  # Extended HHMM of outgoing trip start
                }
            )

    structured_data = {
        "metaData": {
            "dayOfPeriod": file1_data.get("dayOfPeriod", 0),
            "periodLength": file1_data.get("period", 0),
            "description": "Bus scheduling data parsed from DAT files",
        },
        "configuration": {
            "minDelays": {
                "description": "Delay required between different vehicle types (in minutes)",
                "values": file1_data.get("minDelay", [5, 0, 0, 0, 0, 0]),
            },
            "parameters": {
                "maxDutyMinutes": 900,
                "normalDutyMinutes": 600,
                "maxWorkMinutes": 720,
                "driveTimeToBreakMinutes": 270,
                "minBreakMinutes": 30,
                "transitMinutes": 30,
            },
        },
        "stationTransferMatrix": {
            "description": "Matrix defining requirements to move between stations.",
            "legend": {
                "NONE": "No constraint (1)",
                "BREAK": "Requires Break (2)",
                "OVERNIGHT": "Requires Overnight Stay (3)",
            },
            "matrix": station_matrix,
        },
        "resources": resources,
        "trips": structured_trips,
        "constraints": {
            "prohibited": {"buses": prohibited_buses, "drivers": prohibited_drivers},
            "driverWishes": driver_wishes,
            "mandatorySequences": mandatory_sequences,
            "mandatoryConnections": mandatory_connections,
        },
    }

    return structured_data


def parse_file4(dat_path):
    with open(dat_path, "r") as f:
        content = f.read().strip()
    return {"numberOfProhibitedBuses": int(content) if content.isdigit() else 0}


dat_dir = "docs/Information"
file1_data = parse_file1(os.path.join(dat_dir, "FILE1.DAT"))
file2_data = parse_file2(os.path.join(dat_dir, "FILE2.DAT"))
file3_data = parse_file3(os.path.join(dat_dir, "FILE3.DAT"))
file4_data = parse_file4(os.path.join(dat_dir, "FILE4.DAT"))


data = transform_to_structured_format(file1_data, file2_data, file3_data, file4_data)

with open("data.json", "w") as f:
    json.dump(data, f, indent=2)

print("data.json updated with structured DAT information")
