"""Shared experiment limits extracted from the existing orchestrator."""

def normalise_parameters(failure_type: str, parameters: dict) -> dict:
    """Accept old UI keys, store one validated form, and reject unknown inputs."""
    fields = {
        "cpu": (("cpu_percent", "cpuPercent", 50, 1, 65),
                ("duration_seconds", "duration", 30, 1, 300)),
        "latency": (("latency_ms", "delayMs", 100, 0, 500),),
        "packet_loss": (("packet_loss_percent", "lossPercent", 10, 0, 50),),
        "memory": (("memory_mb", "memoryMb", 512, 64, 4096),
                   ("duration_seconds", "duration", 30, 1, 300)),
    }[failure_type]
    allowed = {key for canonical, legacy, *_ in fields for key in (canonical, legacy)}
    unknown = set(parameters) - allowed
    if unknown:
        raise ValueError(f"Unknown parameters: {', '.join(sorted(unknown))}")
    result = {}
    for canonical, legacy, default, low, high in fields:
        if canonical in parameters and legacy in parameters and parameters[canonical] != parameters[legacy]:
            raise ValueError(f"Conflicting values for {canonical}")
        raw = parameters.get(canonical, parameters.get(legacy, default))
        if isinstance(raw, bool) or not isinstance(raw, int) or not low <= raw <= high:
            raise ValueError(f"{canonical} must be an integer from {low} to {high}")
        result[canonical] = raw
    return result
 