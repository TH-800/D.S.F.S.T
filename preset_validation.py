# AI-assisted SCRUM-16 implementation; review and attribute in code reflections.
import math

RULES = {
    "cpu": {"cpu_percent": (1, 65, True), "duration_seconds": (1, 300, True)},
    "latency": {"latency_ms": (0, 500, False)},
    "packet_loss": {"packet_loss_percent": (0, 50, False)},
    "memory": {"memory_mb": (64, 4096, True), "duration_seconds": (1, 300, True)},
}

def validate_preset(name, failure_type, parameters):
    if not isinstance(name, str):
        raise ValueError("Preset name must be text")
    name = name.strip()
    if not 1 <= len(name) <= 80 or any(ord(c) < 32 for c in name):
        raise ValueError("Use a preset name of 1-80 characters without control characters")
    if not isinstance(failure_type, str) or failure_type not in RULES:
        raise ValueError("Unsupported injection type")
    rules = RULES[failure_type]
    if not isinstance(parameters, dict) or set(parameters) != set(rules):
        raise ValueError("Parameters must match the selected injection type")
    clean = {}
    for key, (low, high, integer) in rules.items():
        value = parameters[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
        if integer and int(value) != value:
            raise ValueError(f"{key} must be a whole number")
        clean[key] = int(value) if integer else value
    return {"name": name, "failure_type": failure_type, "parameters": clean}
