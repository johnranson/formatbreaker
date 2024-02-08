from formatbreaker.core import DataType, FBError
from formatbreaker import util


class Byte(DataType):
    """Reads a single byte from the data"""

    backupname = "Byte"

    def _parse(self, data, context, addr):
        bitwise = isinstance(data, util.BitwiseBytes)
        if bitwise:
            length = 8
        else:
            length = 1
        end_addr = addr + length

        if len(data) < end_addr:
            raise FBError("No byte available to parse Byte")

        result = bytes(data[addr:end_addr])

        self._store(context, result, addr=addr)

        return end_addr


class Bytes(DataType):
    """Reads a number of bytes from the data"""

    backupname = "Bytes"

    def __init__(self, length, **kwargs) -> None:
        util.validate_address_or_length(length, 1)
        self.length = length
        super().__init__(**kwargs)

    def _parse(self, data, context, addr):
        bitwise = isinstance(data, util.BitwiseBytes)

        length = self.length
        if bitwise:
            length = length * 8

        end_addr = addr + self.length

        if len(data) < end_addr:
            raise FBError("Insufficient bytes available to parse Bytes")

        result = bytes(data[addr:end_addr])

        self._store(context, result, addr=addr)

        return end_addr


class VarBytes(DataType):
    """Reads a number of bytes from the data with length defined by another field"""

    backupname = "VarBytes"

    def __init__(self, length_key, **kwargs) -> None:
        if not isinstance(length_key, str):
            raise TypeError
        self.length_key = length_key
        super().__init__(**kwargs)

    def _parse(self, data, context, addr):
        bitwise = isinstance(data, util.BitwiseBytes)

        length = context[self.length_key]
        if bitwise:
            length = length * 8
        end_addr = addr + length

        if len(data) < end_addr:
            raise FBError("Insufficient bytes available to parse VarBytes")

        result = bytes(data[addr:end_addr])

        self._store(context, result, addr=addr)

        return end_addr


class PadToAddress(DataType):
    """Brings the data stream to a specific address. Generates a spacer in the
    output. Does not have a name and
    """

    __call__ = None

    def __init__(self, address) -> None:
        super().__init__(address=address)


class Remnant(DataType):
    """Reads all remainging bytes in the data"""

    backupname = "Remnant"

    def _parse(self, data, context, addr):
        end_addr = len(data)

        result = bytes(data[addr:end_addr])

        self._store(context, result, addr=addr)

        return end_addr


class Bit(DataType):
    """Reads a single byte from the data"""

    backupname = "Bit"

    def _parse(self, data, context, addr):
        bitwise = isinstance(data, util.BitwiseBytes)
        if not bitwise:
            raise RuntimeError

        end_addr = addr + 1

        if len(data) < end_addr:
            raise FBError("No bit available to parse Bit")

        result = data[addr]

        self._store(context, result, addr=addr)

        return end_addr


class BitFlags(DataType):
    """Reads a number of bits from the data"""

    backupname = "BitFlags"

    def __init__(self, length, **kwargs) -> None:

        util.validate_address_or_length(length, 1)
        self.length = length
        super().__init__(**kwargs)

    def _parse(self, data, context, addr):
        bitwise = isinstance(data, util.BitwiseBytes)
        if not bitwise:
            raise RuntimeError

        end_addr = addr + self.length

        if len(data) < end_addr:
            raise FBError("Insufficient bytes available to parse Bytes")

        result = data[addr:end_addr].to_bools()

        self._store(context, result, addr=addr)

        return end_addr


class BitWord(DataType):
    """Reads a number of bits from the data"""

    backupname = "BitWord"

    def __init__(self, length=None, **kwargs) -> None:
        util.validate_address_or_length(length, 1)
        self.length = length
        super().__init__(**kwargs)

    def _parse(self, data, context, addr):
        bitwise = isinstance(data, util.BitwiseBytes)
        if not bitwise:
            raise RuntimeError

        end_addr = addr + self.length

        if len(data) < end_addr:
            raise FBError("Insufficient bytes available to parse Bytes")

        result = int(data[addr:end_addr])

        self._store(context, result, addr=addr)

        return end_addr
