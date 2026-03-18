#!/usr/bin/env python3

import argparse
import re
import shlex
import sys
from collections import defaultdict


CAPS_RE = re.compile(r"^[A-Za-z0-9.+_-]+/[A-Za-z0-9.+_-]+(?:[,(].*)?$")
PAD_REF_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*\.[A-Za-z0-9_.-]+$")
NAME_PROP_RE = re.compile(r"^name=(.+)$")


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def split_blocks(text):
    """
    Split the pipeline file into blocks while preserving the original text.

    A block is:
    - one pipeline segment line plus its property continuation lines
    - one standalone separator line containing only '\'
    - one empty line
    - one prefix line such as the gst-launch command

    This parser is designed for the multiline shell style shown in the example.
    """
    lines = text.splitlines(True)
    blocks = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == "" or stripped == "\\":
            blocks.append({"kind": "raw", "text": line})
            i += 1
            continue

        block_lines = [line]
        i += 1

        while i < len(lines):
            next_line = lines[i]
            next_stripped = next_line.strip()

            if next_stripped == "" or next_stripped == "\\":
                break

            if next_stripped.startswith("!"):
                break

            if looks_like_new_top_level_line(next_line):
                break

            block_lines.append(next_line)
            i += 1

        blocks.append({"kind": "segment", "text": "".join(block_lines)})

    return blocks


def looks_like_new_top_level_line(line):
    """
    Heuristic:
    A new top-level chain line usually does not start with '!' and has a small indentation.
    Property continuation lines usually have a deeper indentation.

    This matches the formatting style used in the provided pipeline.
    """
    stripped = line.lstrip(" ")
    if stripped.startswith("!"):
        return False

    indent = len(line) - len(stripped)

    if indent <= 2:
        return True

    return False


def block_tokens(block_text):
    """
    Convert one block to shell tokens.

    Leading '!' is ignored for classification purposes.
    Trailing '\' used for shell continuation is ignored.
    """
    joined = " ".join(
        line.strip().rstrip("\\").strip()
        for line in block_text.splitlines()
    ).strip()

    if joined.startswith("!"):
        joined = joined[1:].strip()

    if not joined:
        return []

    try:
        return shlex.split(joined)
    except ValueError:
        return []


def classify_block(block_text):
    """
    Return one of:
    - element
    - caps
    - padref
    - other
    """
    tokens = block_tokens(block_text)
    if not tokens:
        return "other", None, None

    first = tokens[0]

    if is_caps(first):
        return "caps", first, tokens

    if is_pad_reference(first):
        return "padref", first, tokens

    if looks_like_element(first):
        return "element", first, tokens

    return "other", first, tokens


def is_caps(token):
    return bool(CAPS_RE.match(token))


def is_pad_reference(token):
    return bool(PAD_REF_RE.match(token))


def looks_like_element(token):
    if "=" in token:
        return False
    if is_caps(token):
        return False
    if is_pad_reference(token):
        return False
    return True


def extract_element_base_name(factory, tokens, inferred_counters):
    """
    If the element has name=..., use it.
    Otherwise infer <factory>_<index>.
    """
    for token in tokens[1:]:
        match = NAME_PROP_RE.match(token)
        if match:
            return sanitize_name(match.group(1))

    inferred_index = inferred_counters[factory]
    inferred_counters[factory] += 1
    return "{}_{}".format(sanitize_name(factory), inferred_index)


def sanitize_name(value):
    """
    Keep the name safe for GStreamer element naming.
    """
    return re.sub(r"[^A-Za-z0-9_]+", "_", value)


def identity_line_for(blocks, current_index, identity_name):
    """
    Reuse the indentation style from the next linked block when possible.
    """
    default_indent = "    "

    next_indent = default_indent
    if current_index + 1 < len(blocks):
        next_text = blocks[current_index + 1]["text"]
        first_line = next_text.splitlines()[0] if next_text.splitlines() else ""
        match = re.match(r"^(\s*)!", first_line)
        if match:
            next_indent = match.group(1)

    return "{}! identity name={} \\\n".format(next_indent, identity_name)


def should_insert_after(blocks, index):
    """
    Insert identity only if this block is followed by a linked segment.
    That means the next non-raw block must start with '!'.

    This avoids inserting after terminal sinks and also avoids touching
    independent chains.
    """
    if index + 1 >= len(blocks):
        return False

    next_text = blocks[index + 1]["text"]
    return next_text.lstrip().startswith("!")


def instrument_pipeline(text):
    blocks = split_blocks(text)
    inferred_counters = defaultdict(int)
    output_parts = []

    for index, block in enumerate(blocks):
        output_parts.append(block["text"])

        if block["kind"] != "segment":
            continue

        block_type, first, tokens = classify_block(block["text"])

        if block_type != "element":
            continue

        if not should_insert_after(blocks, index):
            continue

        base_name = extract_element_base_name(first, tokens, inferred_counters)
        identity_name = "{}_id".format(base_name)
        output_parts.append(identity_line_for(blocks, index, identity_name))

    return "".join(output_parts)


def build_default_output_path(input_path):
    if "." in input_path:
        base, ext = input_path.rsplit(".", 1)
        return "{}_with_identities.{}".format(base, ext)
    return input_path + "_with_identities"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Insert GStreamer identity elements after each eligible element in a pipeline file."
    )
    parser.add_argument(
        "input_file",
        help="Path to the input pipeline file.",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        help="Path to the output pipeline file. Defaults to <input>_with_identities.<ext>.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    input_path = args.input_file
    output_path = args.output_file or build_default_output_path(input_path)

    original_text = read_text(input_path)
    instrumented_text = instrument_pipeline(original_text)
    write_text(output_path, instrumented_text)

    print("Input : {}".format(input_path))
    print("Output: {}".format(output_path))


if __name__ == "__main__":
    sys.exit(main())
