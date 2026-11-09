"""Matemática pura del MetaSound de motor sintetizado. No necesita Unreal."""

SPEED_OF_SOUND = 343.0  # m/s


def semitone_ratio(semitones: float) -> float:
    """Multiplicador de frecuencia para un cambio de tono en semitonos: 2^(st/12)."""
    return 2.0 ** (semitones / 12.0)


def engine_hz(base_hz: float, span_st: float, size_st: float, rpm: float, size: float,
              doppler: float = 1.0) -> float:
    """Frecuencia final del oscilador. rpm y size en 0..1."""
    rpm = min(max(rpm, 0.0), 1.0)
    size = min(max(size, 0.0), 1.0)
    return base_hz * semitone_ratio(span_st * rpm - size_st * size) * doppler


def doppler_pitch(v_source_toward: float, v_listener_toward: float,
                  lo: float = 0.8, hi: float = 1.2) -> float:
    """Multiplicador Doppler, velocidades en m/s sobre la línea de visión (+ = acercándose).

    (c + vl) / (c - vs), limitado a [lo, hi]. El denominador nunca baja de 1 m/s.
    """
    raw = (SPEED_OF_SOUND + v_listener_toward) / max(SPEED_OF_SOUND - v_source_toward, 1.0)
    return min(max(raw, lo), hi)


def pulse_rate(rpm_real: float, stroke: int = 2, blades: int = 1, pole_pairs: int = 1,
               kind: str = "combustion") -> float:
    """Pulsos por segundo. combustion: 2T = rpm/60, 4T = rpm/120. prop: rpm/60*blades.
    electric: rpm/60*pole_pairs."""
    if kind == "combustion":
        if stroke not in (2, 4):
            raise ValueError("stroke must be 2 or 4")
        return rpm_real / (60.0 if stroke == 2 else 120.0)
    if kind == "prop":
        return rpm_real / 60.0 * blades
    if kind == "electric":
        return rpm_real / 60.0 * pole_pairs
    raise ValueError("unknown kind: " + kind)
