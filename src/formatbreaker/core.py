"""This module contains the basic Parser, Block (Parser container), and Context (Parser
data storage) code"""

# pyright: reportUnnecessaryComparison=false
# pyright: reportUnnecessaryIsInstance=false

from __future__ import annotations
from typing import ClassVar, Any, override, Callable
from abc import ABC, abstractmethod
import copy
import io
import collections
from formatbreaker.util import validate_address_or_length
from formatbreaker.datasource import DataManager, AddrType


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


type Contexts = tuple[Context, ...]


def get_from_contexts(contexts: Contexts, key: str):
    for context in contexts:
        if key in context:
            return context[key]
    raise KeyError


class ParseResult:
    """Returned by Parser.read() when there is no data to return"""


class Reverted(ParseResult):
    """Returned by an Optional.read() that fails"""


class Success(ParseResult):
    """Returned after a successful Parser.read() with no return data"""


class Parser(ABC):
    """This is the basic parser implementation that most parsers inherit from"""

    __slots__ = ("__label", "__addr_type", "__address", "_backup_label")

    _default_backup_label: ClassVar[str | None] = None
    _default_addr_type: ClassVar[AddrType] = AddrType.UNDEFINED
    __label: str | None
    __address: int | None
    __addr_type: AddrType

    @property
    def _label(self) -> str | None:
        return self.__label

    @_label.setter
    def _label(self, label: str) -> None:
        if label is not None and not isinstance(label, str):
            raise TypeError("Parser labels must be strings")
        self.__label = label

    @property
    def _addr_type(self) -> AddrType:
        return self.__addr_type

    @_addr_type.setter
    def _addr_type(self, addr_type: AddrType | str) -> None:
        if isinstance(addr_type, str):
            self.__addr_type = AddrType[addr_type]
        elif isinstance(addr_type, AddrType):
            self.__addr_type = addr_type
        else:
            raise TypeError("Address type must be ")

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

    @abstractmethod
    def read(self, data: DataManager, contexts: Contexts) -> Any:
        """Parses data

        Should be overridden by any subclass that reads data. Does
        nothing and returns None by default.

        Args:
            data: Data being parsed
            context: Where results old results are stored
        """

    def goto_addr_and_read(
        self, data: DataManager, contexts: Contexts
    ) -> type[ParseResult]:
        """Reads to the target location and then parses normally

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the same
                containing Block
        """
        if self._address is not None:
            _spacer(data, contexts[0], self._address)
        addr = data.address
        result = self.read_and_translate(data, contexts)
        if result is Reverted:
            return Reverted
        if isinstance(result, Context):
            result.update_ext()
        elif result is None:
            raise ValueError
        elif result is not Success:
            self._store(contexts[0], result, addr)
        return Success

    def read_and_translate(
        self,
        data: DataManager,
        contexts: Contexts,
    ) -> Any:

        result = self.read(data, contexts)
        if result is Reverted:
            return Reverted
        return self.translate(result)

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
            self.goto_addr_and_read(manager, (context,))
            return dict(context)
        return {}

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

    def translate(self, data: Any) -> Any:
        """Converts parsed data to another format

        Defaults to passing through the data unchanged.
        This should be overridden as needed by subclasses.

        Args:
            data: Input data from parsing and previous decoding steps

        Returns:
            Translated output data
        """
        return data

    def __getitem__(self, qty: int):
        return Array(self, qty)

    def __mul__(self, qty: int):
        return Repeat(self, qty)

    def __matmul__(self, addr: int):
        b = copy.copy(self)
        b._address = addr
        return b

    def __rshift__(self, label: str):
        if not isinstance(label, str):
            raise TypeError
        b = copy.copy(self)
        b._label = label
        return b


class Block(Parser):
    """A container that holds ordered data fields and provides a mechanism for
    parsing them in order"""

    __slots__ = ("_relative", "_elements", "_optional")

    _relative: bool
    _elements: tuple[Parser, ...]
    _optional: bool
    _default_backup_label: ClassVar[str | None] = "Block"

    def __init__(
        self,
        *elements: Parser,
        relative: bool = True,
        addr_type: AddrType | str = AddrType.PARENT,
        optional: bool = False,
    ) -> None:
        """
        Args:
            *args: Parsers this Block should hold, in order.
            relative: If True, addresses for `self.elements` are relative to this Block.
            bitwise: If True, `self.elements` is addressed and parsed bitwise
            **kwargs: Arguments to be passed to the superclass constructor
        """
        super().__init__()
        if not isinstance(relative, bool):
            raise TypeError
        if not all(isinstance(item, Parser) for item in elements):
            raise TypeError

        self._addr_type = addr_type
        self._elements = elements
        self._relative = relative
        self._optional = optional

    @override
    def read(
        self,
        data: DataManager,
        contexts: Contexts,
    ) -> dict[str, Any] | type[ParseResult]:
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
            out_context = Context()
            for element in self._elements:
                element.goto_addr_and_read(new_data, (out_context, *contexts))
            return dict(out_context)
        return Reverted


class Section(Block):
    _default_backup_label: ClassVar[str | None] = "Section"

    @override
    def read(
        self,
        data: DataManager,
        contexts: Contexts,
    ) -> Context | type[ParseResult]:
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
            out_context = contexts[0].new_child()
            for element in self._elements:
                element.goto_addr_and_read(new_data, (out_context, *contexts[1:]))

            print(out_context)
            return out_context
        return Reverted


def Optional(*args: Any, **kwargs: Any) -> Section:  # pylint: disable=invalid-name
    """Shorthand for generating an optional `Block`.

    Takes the same arguments as a `Block`.

    Returns:
        An optional `Block`
    """
    return Section(*args, optional=True, **kwargs)


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


class Modifier(Parser):
    __slots__ = ["_parser"]
    _parser: Parser

    def __init__(self, parser: Parser, backup_label: str | None = None) -> None:
        super().__init__()
        self._parser = parser
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
        contexts: Contexts,
    ) -> Any:
        """Parses data

        Args:
            data: Data being parsed
            context: Where results old results are stored
        """
        return self._parser.read_and_translate(data, contexts)


class Translator(Modifier):

    __slots__ = ["_translate_func"]

    def __init__(
        self,
        parser: Parser,
        translate_func: Callable[[Any], Any],
        backup_label: str | None = None,
    ) -> None:
        super().__init__(parser, backup_label)
        self._translate_func: Callable[[Any], Any] = staticmethod(translate_func)

    def translate(self, data: Any) -> Any:
        return self._translate_func(data)


class Repeat(Modifier):
    __slots__ = ["_repeat_qty"]

    def __init__(self, parser: Parser, repeat_qty: int | str) -> None:
        super().__init__(parser)
        validate_address_or_length(repeat_qty, 1)
        self._repeat_qty = repeat_qty

    @override
    def read(
        self,
        data: DataManager,
        contexts: Contexts,
    ) -> Context:
        """Parse the data using each Parser sequentially.

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the same
                containing Block
            addr: The bit or byte address in `data` where the Data being parsed lies.
        """

        if isinstance(self._repeat_qty, str):
            reps = get_from_contexts(contexts, self._repeat_qty)
        if isinstance(self._repeat_qty, int):
            reps = self._repeat_qty
        else:
            raise ValueError

        results = contexts[0].new_child()

        for _ in range(reps):
            with data.make_child(
                relative=True,
                addr_type=AddrType.PARENT,
                revertible=False,
            ) as new_data:
                addr = new_data.address
                out_context = results.new_child()
                result = self._parser.read_and_translate(new_data, contexts)
                if result is Reverted:
                    continue
                elif isinstance(result, Context):
                    result.update_ext()
                elif result is not None:
                    self._store(out_context, result, addr)
                out_context.update_ext()
        return results


class Array(Modifier):
    __slots__ = ["_repeat_qty"]

    def __init__(self, parser: Parser, repeat_qty: int | str) -> None:
        super().__init__(parser)
        validate_address_or_length(repeat_qty)
        self._repeat_qty = repeat_qty

    @override
    def read(
        self,
        data: DataManager,
        contexts: Contexts,
    ) -> list[Any] | type[ParseResult]:
        """Parse the data using each Parser sequentially.

        Args:
            data: Data being parsed
            context: Where results are stored including prior results in the same
                containing Block
            addr: The bit or byte address in `data` where the Data being parsed lies.
        """

        if isinstance(self._repeat_qty, str):
            reps = get_from_contexts(contexts, self._repeat_qty)
        if isinstance(self._repeat_qty, int):
            reps = self._repeat_qty
        else:
            raise ValueError

        results: list[Any] = []
        for _ in range(reps):
            with data.make_child(
                relative=True,
                addr_type=AddrType.PARENT,
                revertible=False,
            ) as new_data:
                out_context = Context()
                result = self._parser.read_and_translate(
                    new_data, (out_context, *contexts[1:])
                )
                if result is Reverted:
                    results.append([])
                elif isinstance(result, Context):
                    results.append(dict(result))  # Well, I guess that's okay
                elif result is not None:
                    results.append(result)
        return results
