ONTOLOGY = {
    "Equipment": {
        "Pump": {
            "CentrifugalPump": ["P-101", "P-102", "P-103", "PUMP", "CENTRIFUGAL"],
            "PositiveDisplacementPump": ["P-201"]
        },
        "Compressor": {
            "RotaryScrew": ["C-17"],
            "Reciprocating": ["COMPRESSOR"]
        },
        "Vessel": {
            "PressureVessel": ["V-301"],
            "StorageTank": ["TANK"]
        },
        "HeatExchanger": {
            "ShellAndTube": ["HX-34", "EXCHANGER"]
        },
        "Valve": {
            "ControlValve": ["VALVE", "CV"],
            "ReliefValve": ["RV", "PSV"]
        }
    },
    "Incident": {
        "Mechanical": {
            "BearingFailure": ["BEARING", "SEIZE", "VIBRATION"],
            "SealLeak": ["LEAK", "SEAL"]
        },
        "Electrical": {
            "MotorFailure": ["MOTOR", "TRIP", "SHORT"]
        },
        "Process": {
            "Overpressure": ["OVERPRESSURE", "HIGH PRESSURE"],
            "FlowDeviation": ["NO FLOW", "LOW FLOW"]
        }
    },
    "Procedure": {
        "Maintenance": {
            "PreventiveMaintenance": ["PM", "PREVENTIVE", "SCHEDULED"],
            "PredictiveMaintenance": ["PREDICTIVE", "VIBRATION ANALYSIS"]
        },
        "Inspection": {
            "VisualInspection": ["VISUAL", "WALKDOWN"],
            "NDT": ["NON-DESTRUCTIVE", "ULTRASONIC", "RADIOGRAPHY"]
        }
    }
}

def classify_entity_subtype(entity_type: str, entity_name: str) -> dict:
    """
    Given a top-level entity type and its name, attempts to find its subtype
    and subclass in the ontology using simple keyword matching.
    Returns {"subtype": str, "subclass": str} if found.
    """
    if entity_type not in ONTOLOGY:
        return {}

    name_upper = entity_name.upper()
    for subtype, subclasses in ONTOLOGY[entity_type].items():
        for subclass, keywords in subclasses.items():
            for kw in keywords:
                if kw in name_upper:
                    return {"subtype": subtype, "subclass": subclass}
    
    return {}
