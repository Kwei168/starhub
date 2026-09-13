import re

with open('insight_engine.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix all lines that have ASCII " used as Chinese quotes inside Python strings
# Pattern: lines containing 禁止说"..."、"..."、"..." etc.
for i, line in enumerate(lines):
    if '\u7981\u6b62\u8bf4"' in line:  # "禁止说"
        # Replace "X" with 'X' for Chinese text between quotes
        # But preserve the outer Python string delimiters
        # The line format is: '        "- ...\n"\n'
        # We need to replace inner " with '
        new_line = line.replace('"\u68c0\u7d22\u4e0a\u4e0b\u6587\u672a\u5305\u542b"', "'\u68c0\u7d22\u4e0a\u4e0b\u6587\u672a\u5305\u542b'")
        new_line = new_line.replace('"\u65e0\u6cd5\u751f\u6210"', "'\u65e0\u6cd5\u751f\u6210'")
        new_line = new_line.replace('"\u5efa\u8bae\u63d0\u4f9b"', "'\u5efa\u8bae\u63d0\u4f9b'")
        lines[i] = new_line
        print(f'fixed line {i+1}')

with open('insight_engine.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('done')
