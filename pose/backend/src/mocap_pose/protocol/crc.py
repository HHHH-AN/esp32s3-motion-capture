def crc16_ccitt_false(data: bytes, initial: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE: poly=0x1021, init=0xffff, xorout=0."""
    crc = initial
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc

