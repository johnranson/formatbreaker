# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=protected-access
# pyright: reportPrivateUsage=false

from typing import Any
import io
import pytest
from formatbreaker.basictypes import Failure
from formatbreaker.core import (
    Parser,
    Block,
    Section,
    Context,
    Contexts,
    Success,
    _spacer,
    Optional,
    ParseResult,
)
from formatbreaker.bitwisebytes import BitwiseBytes
from formatbreaker.datasource import DataManager
from formatbreaker.exceptions import FBNoDataError


class TestContext:
    def test_renaming(self):
        context = Context()
        context["name"] = 1
        context["name"] = 2
        context["name"] = 3
        assert context["name"] == 1
        assert context["name 1"] == 2
        assert context["name 2"] == 3

    def test_update_ext_works(self):
        context = Context()
        context["name"] = 1
        child = context.new_child()
        child["name"] = 2
        child["new_name"] = 3
        child.update_ext()
        assert context["name"] == 1
        assert context["name 1"] == 2
        assert context["new_name"] == 3

    def test_update_ext_with_no_parent_raises_error(self):
        context = Context()
        with pytest.raises(RuntimeError):
            context.update_ext()


class ConcreteParser(Parser):
    def read(self, *args: Any, **kwargs: Any) -> type[ParseResult]:
        # pylint: disable=unused-argument
        return Success


class TestParser:

    @pytest.fixture
    def default_dt(self):
        return ConcreteParser()

    @pytest.fixture
    def context(self):
        return Context()

    def test_constructor_defaults_to_no_label_and_address(
        self, default_dt: Parser
    ):

        assert default_dt._label is None
        assert default_dt._address is None

    def test_bad_constructor_types_raise_exceptions(self):
        with pytest.raises(TypeError):
            _ = ConcreteParser() @ "1" >> "label"  # type: ignore

        with pytest.raises(TypeError):
            _ = ConcreteParser() @ 3 >> 3  # type: ignore

    def test_negative_address_raises_exception(self):
        with pytest.raises(IndexError):
            _ = ConcreteParser() @ -1 >> "label"

    @pytest.fixture
    def labeled_dt(self) -> Parser:
        return ConcreteParser() @ 3 >> "label"

    def test_constructor_with_arguments_saves_label_and_address(
        self, labeled_dt: Parser
    ):
        assert labeled_dt._label == "label"
        assert labeled_dt._address == 3
        assert labeled_dt.translate("123") == "123"

    def test_default_parser_performs_no_op(self, labeled_dt: Parser, context: Context):
        with DataManager(b"123567") as data:
            labeled_dt.read(data, (context,))

        assert context == {}

    def test_goto_addr_and_read_raises_error_past_required_address(
        self, labeled_dt: Parser, context: Context
    ):
        with DataManager(b"123567") as data:
            data.read(5)
            with pytest.raises(IndexError):
                labeled_dt.goto_addr_and_read(data, (context,))

    def test_goto_addr_and_read_does_not_create_spacer_if_at_address(
        self, labeled_dt: Parser, context: Context
    ):
        with DataManager(b"123567") as data:
            data.read(3)
            labeled_dt.goto_addr_and_read(data, (context,))
            assert not bool(context)

    def test_goto_addr_and_read_creates_spacer_if_before_required_address(
        self, labeled_dt: Parser, context: Context
    ):
        with DataManager(b"123567") as data:
            data.read(1)
            labeled_dt.goto_addr_and_read(data, (context,))

            assert context["spacer_0x1-0x2"] == b"23"


class TestSection:
    class MockType(Parser):
        _default_backup_label = "mock"

        def __init__(self, length: int | None = None, value: Any = None) -> None:
            self.value = value
            self.length = length
            super().__init__()

        def read(self, data: DataManager, contexts: Contexts):
            data.read(self.length)
            return self.value

    @pytest.fixture
    def empty_section(self) -> Section:
        return Section()

    def test_empty_block_returns_empty_dict_on_parsing(self, empty_section: Section):
        assert empty_section.parse(b"abc") == {}

    def test_section_constructor_fails_with_bad_data(self):
        with pytest.raises(TypeError):
            Section("test")  # type: ignore
        with pytest.raises(TypeError):
            Section(relative="true")  # type: ignore
        with pytest.raises(TypeError):
            Section(addr_type={})  # type: ignore

    @pytest.fixture
    def sequential_section(self) -> Section:
        return Section(
            TestSection.MockType(3, "foo"),
            TestSection.MockType(5, "bar"),
            TestSection.MockType(1, "baz"),
        )

    def test_block_returns_parsing_results_from_all_elements(
        self, sequential_section: Section
    ):
        result = sequential_section.parse(b"12354234562")
        assert result == {
            "mock_0x0": "foo",
            "mock_0x3": "bar",
            "mock_0x8": "baz",
        }

    def test_bytewise_block_raises_error_with_bits(self, sequential_section: Section):
        with pytest.raises(NotImplementedError):
            sequential_section.parse(BitwiseBytes(b"12354234562"))  # type: ignore

    def test_block_returns_error_if_parsing_elements_parse_past_end_of_input(
        self, sequential_section: Section
    ):

        with pytest.raises(FBNoDataError):
            sequential_section.parse(b"12")

    @pytest.fixture
    def bitwise_sequential_section(self) -> Section:
        return Section(
            TestSection.MockType(3, "foo"),
            TestSection.MockType(4, "bar"),
            TestSection.MockType(1, "baz"),
            addr_type="BIT",
        )

    def test_bitwise_block_works_on_bytewise_data(
        self, bitwise_sequential_section: Section
    ):
        result = bitwise_sequential_section.parse(b"12354234562")
        assert result == {
            "mock_0x0": "foo",
            "mock_0x3": "bar",
            "mock_0x7": "baz",
        }

    @pytest.fixture
    def bitwise_sequential_section_length_9(self) -> Section:

        return Section(
            Section(
                TestSection.MockType(3, "foo"),
                TestSection.MockType(5, "bar"),
                TestSection.MockType(1, "baz"),
                addr_type="BIT",
            )
        )

    def test_bitwise_block_parsing_bytewise_data_ending_off_byte_boundary_raises_error(
        self, bitwise_sequential_section_length_9: Section
    ):
        with pytest.raises(RuntimeError):
            bitwise_sequential_section_length_9.parse(b"12354234562")

    @pytest.fixture
    def addressed_section(self) -> Section:
        return Section(
            TestSection.MockType(3, "foo"),
            TestSection.MockType(5, "bar"),
            TestSection.MockType(1, "baz"),
            TestSection.MockType(2, "qux") @ 10,
        )

    @pytest.fixture
    def addressed_block(self) -> Block:
        return Block(
            TestSection.MockType(3, "foo"),
            TestSection.MockType(5, "bar"),
            TestSection.MockType(1, "baz"),
            TestSection.MockType(2, "qux") @ 10,
        )

    def test_section_gets_spacer_with_addressed_elements(
        self, addressed_section: Section
    ):

        result = addressed_section.parse(b"\0" * 100)

        assert result == {
            "mock_0x0": "foo",
            "mock_0x3": "bar",
            "mock_0x8": "baz",
            "spacer_0x9": b"\x00",
            "mock_0xa": "qux",
        }

    def test_nested_blocks_produce_expected_results(
        self, addressed_section: Section, addressed_block: Block
    ):
        cnk = Section(
            addressed_section,
            addressed_block >> "label",
            addressed_block @ 40 >> "label",
            addressed_section @ 60,
        )

        result = cnk.parse(bytes(range(256)))
        print(result)

        assert result == {
            "mock_0x0": "foo",
            "mock_0x3": "bar",
            "mock_0x8": "baz",
            "spacer_0x9": b"\t",
            "mock_0xa": "qux",
            "label": {
                "mock_0x0": "foo",
                "mock_0x3": "bar",
                "mock_0x8": "baz",
                "spacer_0x9": b"\x15",
                "mock_0xa": "qux",
            },
            "spacer_0x18-0x27": b"\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f !\"#$%&'",
            "label 1": {
                "mock_0x0": "foo",
                "mock_0x3": "bar",
                "mock_0x8": "baz",
                "spacer_0x9": b"1",
                "mock_0xa": "qux",
            },
            "spacer_0x34-0x3b": b"456789:;",
            "mock_0x0 1": "foo",
            "mock_0x3 1": "bar",
            "mock_0x8 1": "baz",
            "spacer_0x9 1": b"E",
            "mock_0xa 1": "qux",
        }

    def test_optional_blocks_work(
        self, addressed_section: Section, addressed_block: Block
    ):
        cnk = Section(
            addressed_section,
            Optional(
                addressed_block >> "opt",
                addressed_block @ 40 >> "opt",
                Block(
                    addressed_section @ 60,
                    Failure,
                    relative=False,
                ),
                relative=False,
            ),
            addressed_block >> "label",
            addressed_block @ 40 >> "label",
            addressed_section @ 60,
        )
        result = cnk.parse(bytes(range(256)))

        assert result == {
            "mock_0x0": "foo",
            "mock_0x3": "bar",
            "mock_0x8": "baz",
            "spacer_0x9": b"\t",
            "mock_0xa": "qux",
            "label": {
                "mock_0x0": "foo",
                "mock_0x3": "bar",
                "mock_0x8": "baz",
                "spacer_0x9": b"\x15",
                "mock_0xa": "qux",
            },
            "spacer_0x18-0x27": b"\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f !\"#$%&'",
            "label 1": {
                "mock_0x0": "foo",
                "mock_0x3": "bar",
                "mock_0x8": "baz",
                "spacer_0x9": b"1",
                "mock_0xa": "qux",
            },
            "spacer_0x34-0x3b": b"456789:;",
            "mock_0x0 1": "foo",
            "mock_0x3 1": "bar",
            "mock_0x8 1": "baz",
            "spacer_0x9 1": b"E",
            "mock_0xa 1": "qux",
        }


@pytest.fixture
def spacer_stream_data():
    dat = bytes(range(128))
    return DataManager(io.BytesIO(dat))


@pytest.fixture
def spacer_bytes_data():
    dat = bytes(range(256)) * 16
    return DataManager(dat)


spacer_data = bytes(range(128))


class TestSpacer:

    @pytest.fixture
    def context(self):
        return Context()

    def test_spacer_generates_expected_dictionary_and_return_value(
        self, context: Context
    ):
        with DataManager(spacer_data) as data:
            data.read(1)
            _spacer(data, context, 6)
            assert context["spacer_0x1-0x5"] == bytes(spacer_data[1:6])

    def test_duplicate_spacer_generates_expected_dictionary_and_return_value(
        self, context: Context
    ):
        with DataManager(spacer_data) as data:
            context["spacer_0x1-0x5"] = bytes(spacer_data[1:6])
            data.read(1)
            _spacer(data, context, 6)
            assert context["spacer_0x1-0x5 1"] == bytes(spacer_data[1:6])

    def test_spacer_works_with_entire_input(self, context: Context):
        with DataManager(spacer_data) as data:
            _spacer(data, context, 128)
            assert context["spacer_0x0-0x7f"] == bytes(spacer_data)

    def test_length_one_beyond_input_size_raises_error(self, context: Context):
        with DataManager(spacer_data) as data:
            with pytest.raises(FBNoDataError):
                _spacer(data, context, 129)

    def test_negative_address_raises_error(self, context: Context):
        with DataManager(spacer_data) as data:
            with pytest.raises(IndexError):
                _spacer(data, context, -1)

    def test_zero_length_spacer_is_no_op(self, context: Context):
        with DataManager(spacer_data) as data:
            _spacer(data, context, 0)
            assert context == {}
