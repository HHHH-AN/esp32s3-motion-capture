class ProtocolError(ValueError):
    """Base error for malformed wire data."""


class CobsDecodeError(ProtocolError):
    pass


class FrameDecodeError(ProtocolError):
    pass


class CrcMismatchError(FrameDecodeError):
    pass

