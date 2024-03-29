"""This module contains formatbreaker.Parser subclasses that operate directly
on the bits and bytes of the data being parsed

If a Parser can be implemented as a subclass of an existing Parser
by only implementing __init__ and _decode, it should not go here.
"""

from __future__ import annotations
from typing import override, ClassVar, Any
from formatbreaker.core import Parser, Contexts, Success, ParseResult, get_from_contexts
from formatbreaker.datasource import DataManager, AddrType
from formatbreaker.exceptions import FBError
from formatbreaker.util import validate_address_or_length
from formatbreaker.bitwisebytes import BitwiseBytes


class FailureParser(Parser):
    """Always raises an FBError when parsing"""

    def read(self, data: DataManager, contexts: Contexts) -> BitwiseBytes:
        raise FBError


Failure = FailureParser()


class ByteParser(Parser):
    """Reads a single byte from the data"""

    _default_backup_label: ClassVar[str] = "Byte"
    _default_addr_type: ClassVar[AddrType] = AddrType.BYTE

    @override
    def read(self, data: DataManager, contexts: Contexts) -> bytes:
        """Reads a single byte from `addr` in `data` and stores the byte in an
        entry in `context`

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the
                same containing Block
            addr: The bit or byte address in `data` where the byte to be parsed lies.
        """
        return data.read_bytes(1)


Byte = ByteParser()


class Bytes(Parser):
    """Reads a number of bytes from the data"""

    _default_backup_label: ClassVar[str] = "Bytes"

    @override
    def __init__(self, byte_length: int | str | tuple) -> None:
        """
        Args:
            byte_length:The length to read in bytes, when parsing.
            **kwargs: Arguments to be passed to the superclass constructor
        """
        if isinstance(byte_length, int):
            validate_address_or_length(byte_length, 1)
        self._byte_length = byte_length
        super().__init__()

    @override
    def read(self, data: DataManager, contexts: Contexts) -> bytes:
        """Reads `self._byte_length` many bytes from `addr` in `data` and
        stores the bytes in an entry in `context`

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the
                same containing Block
            addr: The bit or byte address in `data` where the bytes to be parsed lie.
        """
        if isinstance(self._byte_length, int):
            length = self._byte_length
        else:
            length = get_from_contexts(contexts, self._byte_length)
            if not isinstance(length, int):
                raise TypeError
        if length < 1:
            raise ValueError

        return data.read_bytes(length)


class VarBytes(Parser):
    """Reads a number of bytes from the data with length dynamically
    defined by another field in the data"""

    _default_backup_label: ClassVar[str] = "VarBytes"

    @override
    def __init__(
        self, *, source: str
    ) -> None:  # source is keyword-only to avoid ambiguity with label
        """
        Args:
            length_key: The key to read from the context to get the number of
                bytes to read while parsing
            **kwargs: Arguments to be passed to the superclass constructor
        """
        if not isinstance(source, str):  # type: ignore
            raise TypeError
        self._length_key = source
        super().__init__()

    @override
    def read(self, data: DataManager, contexts: Contexts) -> bytes:
        """Reads `context[self.length_key]` many bytes from `addr` in `data`
        and stores the bytes in an entry in `context`

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the
                same containing Block
            addr: The bit or byte address in `data` where the bytes to be parsed lie.

        Returns:
            The next bit or byte address after the parsed bytes
        """
        length: int = contexts[0][self._length_key]
        if not isinstance(length, int):  # type: ignore
            raise ValueError()
        return data.read_bytes(length)


class PadToAddress(Parser):
    """Generates a spacer during parsing to a specific address"""

    def __call__(self, name: str | None = None, *, addr: int | None = None) -> Parser:
        raise NotImplementedError

    @override
    def __init__(self, addr: int) -> None:
        """
        Args:
            addr: The address up to which to read
        """
        super().__init__()
        self._address = addr

    def read(self, *args: Any, **kwargs: Any) -> type[ParseResult]:
        # pylint: disable=unused-argument
        return Success


class EndParser(Parser):
    """Raises an error if there is more data"""
    @override
    def read(self, data: DataManager, contexts: Contexts) -> type[ParseResult]:
        """Reads all data from `addr` to the end of `data` and stores the
        data in an entry in `context`

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the
                same containing Block
            addr: The bit or byte address in `data` where the bytes to be parsed lie.

        Returns:
            The length of `data`
        """
        test = None
        with data.make_child(relative=True, addr_type=AddrType.PARENT, revertible=True):
            test = data.read_bytes(1)
        if test is not None:
            raise FBError
        return Success


End = EndParser()


class RemnantParser(Parser):
    """Reads all remainging bytes in the data"""

    _default_backup_label: ClassVar[str] = "Remnant"

    @override
    def read(self, data: DataManager, contexts: Contexts) -> bytes:
        """Reads all data from `addr` to the end of `data` and stores the
        data in an entry in `context`

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the
                same containing Block
            addr: The bit or byte address in `data` where the bytes to be parsed lie.

        Returns:
            The length of `data`
        """
        result = data.read_bytes()
        print(result)
        return result


Remnant = RemnantParser()


class BitParser(Parser):
    """Reads a single byte from the data"""

    _default_backup_label: ClassVar[str] = "Bit"
    _default_addr_type: ClassVar[AddrType] = AddrType.BIT

    @override
    def read(self, data: DataManager, contexts: Contexts) -> bool:
        """Reads a single bit from `addr` in `data` and stores the bit in an
        entry in `context`

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the
                same containing Block
            addr: The bit address in `data` where the byte to be parsed lies.

        Returns:
            The next bit address after the parsed byte
        """
        return data.read_bits(1)[0]


Bit = BitParser()


class BitWord(Parser):
    """Reads a number of bits from the data"""

    _bit_length: int
    _default_backup_label: ClassVar[str] = "BitWord"
    _default_addr_type: ClassVar[AddrType] = AddrType.BIT

    @override
    def __init__(self, bit_length: int) -> None:
        """
        Args:
            bit_length: The length to read in bits, when parsing.
            **kwargs: Arguments to be passed to the superclass constructor
        """
        validate_address_or_length(bit_length, 1)
        self._bit_length = bit_length
        super().__init__()

    @override
    def read(self, data: DataManager, contexts: Contexts) -> BitwiseBytes:
        """Reads `self._bit_length` many bits from `addr` in `data` and
        stores the bits as BitwiseBytes in an entry in `context`

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the
                same containing Block
            addr: The bit address in `data` where the bytes to be parsed lie.

        Returns:
            The next bit address after the parsed bits
        """
        return data.read_bits(self._bit_length)
