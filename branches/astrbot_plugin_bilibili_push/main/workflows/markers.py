from __future__ import annotations

ZERO = "\u200b"
ONE = "\u200c"
SEP = "\u2063"
PREFIX = f"{SEP}{ZERO}{ONE}{ZERO}{ONE}{SEP}"
SUFFIX = f"{SEP}{ONE}{ZERO}{ONE}{ZERO}{SEP}"


def encode_task_marker(task_id: str) -> str:
    value = str(task_id or "")
    if not value:
        return ""
    bits = "".join(f"{byte:08b}" for byte in value.encode("utf-8"))
    payload = "".join(ONE if bit == "1" else ZERO for bit in bits)
    return f"{PREFIX}{payload}{SUFFIX}"


def decode_task_marker(text: str) -> str:
    value = str(text or "")
    start = value.find(PREFIX)
    if start < 0:
        return ""
    start += len(PREFIX)
    end = value.find(SUFFIX, start)
    if end < 0:
        return ""
    payload = value[start:end]
    bits = "".join("1" if char == ONE else "0" for char in payload if char in {ZERO, ONE})
    if len(bits) % 8:
        return ""
    try:
        raw = bytes(int(bits[index:index + 8], 2) for index in range(0, len(bits), 8))
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
