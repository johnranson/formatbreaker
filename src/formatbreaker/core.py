"""This module contains the basic Parser, Block (Parser container), and Context (Parser
data storage) code"""

from __future__ import annotations
from typing import ClassVar, Any, override
import copy
import io
import collections
from formatbreaker.util import validate_address_or_length
from formatbreaker.datasource import DataManager, AddrType


class Parser:
    """This is the basic parser implementation that most parsers inherit from"""

    __slots__ = ("__label", "__address", "_addr_type", "_backup_label")

    __label: str | None
    __address: int | None
    _default_backup_label: ClassVar[str | None] = None
    _default_addr_type: ClassVar[AddrType] = AddrType.UNDEFINED
    _addr_type: AddrType

    @property
    def _label(self) -> str | None:
        return self.__label

    @_label.setter
    def _label(self, label: str) -> None:
        if label is not None and not isinstance(label, str):  # type: ignore
            raise TypeError("Parser labels must be strings")
        self.__label = label

    @property
    def _address(self) -> int | None:
        return self.__address

    @_address.setter
    def _address(self, address: int) -> None:
        if address is not None:
            validate_address_or_length(address)
        self.__address = address

    def __init__(self) -> None:
        self.__address = None
        self.__label = None
        self._addr_type = self._default_addr_type

        self._backup_label = self._default_backup_label

    def read(
        self,
        data: DataManager,
        context: Context,
    ) -> Any:
        """Parses data

        Should be overridden by any subclass that reads data. Does
        nothing and returns None by default.

        Args:
            data: Data being parsed
            context: Where results old results are stored
        """
        # pylint: disable=unused-argument
        return None

    def goto_addr_and_read(self, data: DataManager, context: Context) -> None:
        """Reads to the target location and then parses normally

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the same
                containing Block
        """
        if self._address is not None:
            _spacer(data, context, self._address)
        addr = data.address
        result = self.read(data, context)
        if result is None:
            return
        result = self.decode(result)
        self._store(context, result, addr)

    def parse(
        self,
        data: bytes | io.BufferedIOBase,
    ) -> dict[str, Any]:
        """Parse the provided data from the beginning

        Args:
            data: Data being parsed
        """
        context = Context()
        with DataManager(src=data, addr_type=self._addr_type) as manager:
            self.goto_addr_and_read(manager, context)
            return dict(context)

    def _store(
        self,
        context: Context,
        data: Any,
        addr: int | None = None,
        label: str | None = None,
    ) -> None:
        """Store the value with a unique key

        If `label` is not provided, the code will use `self._label`. If
        `self._label` is None, it will default to the class `_backup_label`
        attribute.

        Args:
            context: Where results are stored including prior results in the same
                containing Block
            data: The data to be decoded and stored
            addr: The location the data came from, used for unlabeled fields
            label: The label to store the data under.
        """

        if label:
            pass
        elif self._label:
            label = self._label
        elif self._backup_label:
            if addr is not None:
                validate_address_or_length(addr)
                label = self._backup_label + "_" + hex(addr)
            else:
                label = self._backup_label
        else:
            raise RuntimeError("Attempted to store unlabeled data")
        context[label] = data

    def _update(self, context: Context, data: Context):
        """Decode a dictionary and update into another dictionary

        Args:
            context: Where to store the results
            data: The data to be decoded and stored
        """
        for key in data:
            self._store(context, data[key], label=key)

    def decode(self, data: Any) -> Any:
        """Converts parsed data to another format

        Defaults to passing through the data unchanged.
        This should be overridden as needed by subclasses.

        Args:
            data: Input data from parsing and previous decoding steps

        Returns:
            Decoded output data
        """
        return data

    def __getitem__(self, qty: int):
        validate_address_or_length(qty)
        return Repeat(qty)(self)

    def __matmul__(self, addr: int):
        b = copy.copy(self)
        validate_address_or_length(addr)
        b._address = addr
        return b

    def __rshift__(self, label: str):
        if not isinstance(label, str):  # type: ignore
            raise TypeError
        b = copy.copy(self)
        b._label = label
        return b


class Block(Parser):
    """A container that holds ordered data fields and provides a mechanism for
    parsing them in order"""

    __slots__ = ("_relative", "_elements", "_optional", "_repeat")

    _relative: bool
    _elements: tuple[Parser, ...]
    _optional: bool
    _repeat: int | str

    def __init__(
        self,
        *args: Parser,
        relative: bool = True,
        addr_type: AddrType | str = AddrType.PARENT,
        optional: bool = False,
        repeat_qty: int | str = 1,
    ) -> None:
        """
        Args:
            *args: Parsers this Block should hold, in order. Lists will be unpacked
            relative: If True, addresses for `self.elements` are relative to this Block.
            bitwise: If True, `self.elements` is addressed and parsed bitwise
            **kwargs: Arguments to be passed to the superclass constructor
        """
        super().__init__()
        if not isinstance(relative, bool):  # type: ignore
            raise TypeError
        if not all(isinstance(item, Parser) for item in args):  # type: ignore
            raise TypeError
        if isinstance(addr_type, AddrType):
            self._addr_type = addr_type
        else:
            self._addr_type = AddrType[addr_type]

        if isinstance(repeat_qty, int) | isinstance(repeat_qty, str):
            self._repeat = repeat_qty
        else:
            raise TypeError

        self._elements = args

        self._relative = relative
        self._optional = optional

    def goto_addr_and_read(
        self,
        data: DataManager,
        context: Context,
    ) -> None:
        """Reads to the target location and then parses normally

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the same
                containing Block
        """
        if self._address is not None:
            _spacer(data, context, self._address)
        if isinstance(self._repeat, str):
            reps = context[self._repeat]
            if not isinstance(reps, int):
                raise ValueError
        else:
            reps = self._repeat
        for _ in range(reps):
            result = self.read(data, context)
            if result is None:
                return
            result = self.decode(result)
            if self._label:
                self._store(context, dict(result))
            else:
                result.update_ext()

    @override
    def read(
        self,
        data: DataManager,
        context: Context,
    ) -> Context:
        """Parse the data using each Parser sequentially.

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the same
                containing Block
            addr: The bit or byte address in `data` where the Data being parsed lies.
        """

        with data.make_child(
            relative=self._relative,
            addr_type=self._addr_type,
            revertible=self._optional,
        ) as new_data:
            if self._label:
                out_context = Context()
            else:
                out_context = context.new_child()
            for element in self._elements:
                element.goto_addr_and_read(  # pylint: disable=protected-access
                    new_data, out_context
                )
            return out_context
        return None


def Optional(*args: Any, **kwargs: Any) -> Block:  # pylint: disable=invalid-name
    """Shorthand for generating an optional `Block`.

    Takes the same arguments as a `Block`.

    Returns:
        An optional `Block`
    """
    return Block(*args, optional=True, **kwargs)


def Repeat(repeat_qty: int | str):  # pylint: disable=invalid-name
    """Shorthand for generating a repeated `Block`.

    Takes the same arguments as a `Block`.

    Returns:
        An optional `Block`
    """
    return lambda *args, **kwargs: Block(*args, repeat_qty=repeat_qty, **kwargs)


def _spacer(
    data: DataManager,
    context: Context,
    stop_addr: int,
):
    """Reads a spacer into a context dictionary

    Args:
        data: Data being parsed
        context: Where results are stored
        stop_addr: The address of the first bit or byte in `data_source` to be excluded

    """
    start_addr = data.address
    length = stop_addr - start_addr

    if length == 0:
        return
    if length > 1:
        spacer_label = "spacer_" + hex(start_addr) + "-" + hex(stop_addr - 1)
    else:
        spacer_label = "spacer_" + hex(start_addr)

    context[spacer_label] = data.read(length)


class Context(collections.ChainMap[str, Any]):
    """Contains the results from parsing in a nested manner, allowing reverting failed
    optional data reads"""

    def __setitem__(self, key: str, value: Any) -> None:
        """Sets the underlying ChainMap value but updates duplicate keys

        Args:
            key: _description_
            value: _description_
        """
        parts = key.split(" ")
        if parts[-1].isnumeric():
            base = " ".join(parts[0:-1])
            i = int(parts[-1])
            new_key = base + " " + str(i)
        else:
            base = key
            i = 1
            new_key = key

        while new_key in self:
            new_key = base + " " + str(i)
            i = i + 1
        super().__setitem__(new_key, value)

    def update_ext(self) -> None:
        """Loads all of the current Context values into the parent Context"""
        if len(self.maps) == 1:
            raise RuntimeError
        self.maps[1].update(self.maps[0])
        self.maps[0].clear()


class Translator(Parser):
    __slots__ = ["_parsable"]
    _parsable: Parser

    def __init__(self, parser: Parser, backup_label: str | None = None) -> None:
        super().__init__()
        self._parsable = parser
        if backup_label:
            self._backup_label = backup_label
        else:
            self._backup_label = parser._backup_label
        self._addr_type = parser._addr_type
        if parser._label:
            self._label = parser._label
        if parser._address:
            self._address = parser._address

    def read(
        self,
        data: DataManager,
        context: Context,
    ) -> Any:
        """Parses data

        Args:
            data: Data being parsed
            context: Where results old results are stored
        """
        return self._parsable.read(data, context)

    def decode(self, data: Any) -> Any:
        return self._translate(data)

    def _translate(self, data: Any) -> Any:
        return self._parsable.decode(data)


class StaticTranslator(Translator):

    __slots__ = ["_translate_func"]

    def __init__(
        self, parser: Parser, translate_func, backup_label: str | None = None
    ) -> None:
        super().__init__(parser, backup_label)
        self._translate_func = staticmethod(translate_func)

    def _translate(self, data: Any) -> Any:
        return self._translate_func(data)
