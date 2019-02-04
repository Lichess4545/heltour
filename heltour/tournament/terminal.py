"""Simple terminal output
"""

HEADER = '\033[95m'
OKBLUE = '\033[94m'
OKGREEN = '\033[92m'
WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
def bold(txt):
    return BOLD + txt + ENDC
def green(txt):
    return OKGREEN + txt + ENDC
def blue(txt):
    return OKBLUE + txt + ENDC
def header(txt):
    return HEADER + txt + ENDC
def underline(txt):
    return UNDERLINE + txt + ENDC
def smallheader(txt, wrap=None):
    if wrap:
        wrap = lambda x: underline(wrap(x))
    else:
        wrap = underline
    smallcol(txt, wrap)
def largeheader(txt, wrap=None):
    if wrap:
        wrap = lambda x: underline(wrap(x))
    else:
        wrap = underline
    largecol(txt, wrap)
def smallcol(txt, wrap=None):
    if not wrap:
        wrap = lambda x: x
    print(wrap(" {0: <6} |".format(txt)), end='')
def largecol(txt, wrap=None):
    if not wrap:
        wrap = lambda x: x
    print(wrap(" {0: <27} |".format(txt)), end='')
def separator():
    print("-{0:-<6}--".format(""), end='')
    for x in range(6):
        print("-{0: <27}--".format("-"*27), end='')
    print()
