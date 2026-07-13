"""L'entry point accetta gli argomenti che i client editor passano davvero."""
import pytest

from glls.__main__ import build_parser


def test_stdio_flag_accepted():
    # vscode-languageclient con TransportKind.stdio aggiunge --stdio
    args = build_parser().parse_args(["--stdio"])
    assert args.stdio is True and args.tcp is False


def test_no_args_defaults_to_stdio():
    args = build_parser().parse_args([])
    assert args.tcp is False


def test_unknown_arg_still_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--bogus"])
