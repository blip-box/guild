---
name: escape-check
description: How to write a non-ASCII character in this project's Python source or tests, and how to check the file afterwards. Use it whenever an edit needs a code point above U+007F, such as a look-alike, a control, a mark or a Tag character.
---

# Escape and check

Python source in this project is ASCII. Every other character is written as
an escape inside an ordinary string: `\u0430` for a code point up to
U+FFFF, `\U0001f3f4` above it. Never paste the character itself, and never
put an escape in a raw string, where it stays two characters.

A brief writes code points as `U+XXXX`; the string for `U+0061 U+202E` is
`"a\u202e"`, and for `U+1F3F4 U+E0075` it is `"\U0001f3f4\U000e0075"`.

After writing the file, check its bytes:

    python3 -c "import sys; d=open(sys.argv[1],'rb').read(); print('ascii' if d.isascii() else 'NON-ASCII')" path/to/file.py

If it prints NON-ASCII, replace the character with its escape. The test
suite and ruff refuse a file that is not ASCII, so the check saves a round.
