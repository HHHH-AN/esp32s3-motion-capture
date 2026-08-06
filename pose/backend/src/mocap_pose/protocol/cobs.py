from .errors import CobsDecodeError


def cobs_encode(data: bytes) -> bytes:
    output = bytearray([0])
    code_index = 0
    code = 1
    for byte in data:
        if byte == 0:
            output[code_index] = code
            code_index = len(output)
            output.append(0)
            code = 1
        else:
            output.append(byte)
            code += 1
            if code == 0xFF:
                output[code_index] = code
                code_index = len(output)
                output.append(0)
                code = 1
    output[code_index] = code
    return bytes(output)


def cobs_decode(data: bytes) -> bytes:
    if not data:
        raise CobsDecodeError("empty COBS frame")
    output = bytearray()
    index = 0
    while index < len(data):
        code = data[index]
        if code == 0:
            raise CobsDecodeError("zero byte inside COBS frame")
        index += 1
        end = index + code - 1
        if end > len(data):
            raise CobsDecodeError("COBS block exceeds frame boundary")
        output.extend(data[index:end])
        index = end
        if code != 0xFF and index < len(data):
            output.append(0)
    return bytes(output)

