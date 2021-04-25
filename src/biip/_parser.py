"""The top-level Biip parser."""

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple, Type, Union

from biip import ParseError
from biip.gs1 import DEFAULT_SEPARATOR_CHARS, GS1Message, GS1Symbology
from biip.gtin import Gtin, GtinFormat, RcnRegion
from biip.sscc import Sscc
from biip.symbology import SymbologyIdentifier
from biip.upc import Upc

ParserType = Union[Type[GS1Message], Type[Gtin], Type[Sscc], Type[Upc]]


def parse(
    value: str,
    *,
    rcn_region: Optional[RcnRegion] = None,
    separator_chars: Iterable[str] = DEFAULT_SEPARATOR_CHARS,
) -> "ParseResult":
    """Identify data format and parse data.

    The current strategy is:

    1. If Symbology Identifier prefix indicates a GTIN or GS1 Message,
       attempt to parse and validate as that.
    2. Else, if not Symbology Identifier, attempt to parse with all parsers.

    Args:
        value: The data to classify and parse.
        rcn_region: The geographical region whose rules should be used to
            interpret Restricted Circulation Numbers (RCN).
            Needed to extract e.g. variable weight/price from GTIN.
        separator_chars: Characters used in place of the FNC1 symbol.
            Defaults to `<GS>` (ASCII value 29).
            If variable-length fields in the middle of the message are
            not terminated with a separator character, the parser might
            greedily consume the rest of the message.

    Returns:
        A data class depending upon what type of data is parsed.

    Raises:
        ParseError: If parsing of the data fails.
    """
    value = value.strip()
    config = ParseConfig(
        rcn_region=rcn_region,
        separator_chars=separator_chars,
    )
    result = ParseResult(value=value)

    # Extract Symbology Identifier
    if value.startswith("]"):
        result.symbology_identifier = SymbologyIdentifier.extract(value)
        value = value[len(result.symbology_identifier) :]

    # Select parsers
    queue: List[Tuple[ParserType, str]] = []
    if result.symbology_identifier is not None:
        if result.symbology_identifier.gs1_symbology in GS1Symbology.with_gtin():
            queue.append((Gtin, value))
        if (
            result.symbology_identifier.gs1_symbology
            in GS1Symbology.with_ai_element_strings()
        ):
            queue.append((GS1Message, value))
    if not queue:
        # If we're not able to select a subset based on Symbology Identifiers,
        # run all parsers on the full value.
        queue = [
            (GS1Message, value),
            (Gtin, value),
            (Sscc, value),
            (Upc, value),
        ]

    # Work through queue of parsers and the values to run them on. Any parser may
    # add additional work to the queue. Only the first result for a field is kept.
    while queue:
        (parser, val) = queue.pop(0)
        if parser == GS1Message:
            result._parse_gs1_message(val, config=config, queue=queue)
        if parser == Gtin:
            result._parse_gtin(val, config=config, queue=queue)
        if parser == Sscc:
            result._parse_sscc(val, config=config, queue=queue)
        if parser == Upc:
            result._parse_upc(val, config=config, queue=queue)

    if result._has_result():
        return result
    else:
        raise ParseError(f"Failed to parse {value!r}:\n{result._get_errors_list()}")


@dataclass
class ParseConfig:
    """Configuration options for parsers."""

    rcn_region: Optional[RcnRegion]
    separator_chars: Iterable[str]


@dataclass
class ParseResult:
    """Results from a successful barcode parsing."""

    #: The raw value. Only stripped of surrounding whitespace.
    value: str

    #: The Symbology Identifier, if any.
    symbology_identifier: Optional[SymbologyIdentifier] = None

    #: The extracted GTIN, if any.
    #: Is also set if a GS1 Message containing a GTIN was successfully parsed.
    gtin: Optional[Gtin] = None

    #: The GTIN parse error, if parsing as a GTIN was attempted and failed.
    gtin_error: Optional[str] = None

    #: The extracted UPC, if any.
    upc: Optional[Upc] = None

    #: The UPC parse error, if parsing as an UPC was attempted and failed.
    upc_error: Optional[str] = None

    #: The extracted SSCC, if any.
    #: Is also set if a GS1 Message containing an SSCC was successfully parsed.
    sscc: Optional[Sscc] = None

    #: The SSCC parse error, if parsing as an SSCC was attempted and failed.
    sscc_error: Optional[str] = None

    #: The extracted GS1 Message, if any.
    gs1_message: Optional[GS1Message] = None

    #: The GS1 Message parse error,
    #: if parsing as a GS1 Message was attempted and failed.
    gs1_message_error: Optional[str] = None

    def _parse_gtin(
        self: "ParseResult",
        value: str,
        *,
        config: ParseConfig,
        queue: List[Tuple[ParserType, str]],
    ) -> None:
        if self.gtin is not None:
            return  # pragma: no cover

        try:
            self.gtin = Gtin.parse(value, rcn_region=config.rcn_region)
            self.gtin_error = None
        except ParseError as exc:
            self.gtin = None
            self.gtin_error = str(exc)
        else:
            # If GTIN is a GTIN-12, set UPC on the top-level result.
            if self.gtin.format == GtinFormat.GTIN_12 and self.upc is None:
                queue.append((Upc, self.gtin.as_gtin_12()))

    def _parse_upc(
        self: "ParseResult",
        value: str,
        *,
        config: ParseConfig,
        queue: List[Tuple[ParserType, str]],
    ) -> None:
        if self.upc is not None:
            return  # pragma: no cover

        try:
            self.upc = Upc.parse(value)
            self.upc_error = None
        except ParseError as exc:
            self.upc = None
            self.upc_error = str(exc)
        else:
            # If UPC, expand and set GTIN on the top-level result.
            if self.gtin is None:
                queue.append((Gtin, self.upc.as_upc_a()))

    def _parse_sscc(
        self: "ParseResult",
        value: str,
        *,
        config: ParseConfig,
        queue: List[Tuple[ParserType, str]],
    ) -> None:
        if self.sscc is not None:
            return  # pragma: no cover

        try:
            self.sscc = Sscc.parse(value)
            self.sscc_error = None
        except ParseError as exc:
            self.sscc = None
            self.sscc_error = str(exc)

    def _parse_gs1_message(
        self: "ParseResult",
        value: str,
        *,
        config: ParseConfig,
        queue: List[Tuple[ParserType, str]],
    ) -> None:
        if self.gs1_message is not None:
            return  # pragma: no cover

        try:
            self.gs1_message = GS1Message.parse(
                value,
                rcn_region=config.rcn_region,
                separator_chars=config.separator_chars,
            )
            self.gs1_message_error = None
        except ParseError as exc:
            self.gs1_message = None
            self.gs1_message_error = str(exc)
        else:
            # If the GS1 Message contains an SSCC, set SSCC on the top-level result.
            ai_00 = self.gs1_message.get(ai="00")
            if ai_00 is not None and ai_00.sscc is not None:
                queue.append((Sscc, ai_00.sscc.value))

            # If the GS1 Message contains an GTIN, set GTIN on the top-level result.
            ai_01 = self.gs1_message.get(ai="01")
            if ai_01 is not None and ai_01.gtin is not None:
                queue.append((Gtin, ai_01.gtin.value))

    def _has_result(self: "ParseResult") -> bool:
        return any([self.gtin, self.upc, self.sscc, self.gs1_message])

    def _get_errors_list(self: "ParseResult") -> str:
        return "\n".join(
            f"- {parser_name}: {error}"
            for parser_name, error in [
                ("GTIN", self.gtin_error),
                ("UPC", self.upc_error),
                ("SSCC", self.sscc_error),
                ("GS1", self.gs1_message_error),
            ]
            if error is not None
        )
