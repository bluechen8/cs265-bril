import json
import sys
import copy
from block_gen import block_gen


# Memoy op alias analysis
def mem_alias(fn):
    blocks, blocks_cfg = block_gen(fn, dummy=False)


if __name__ == "__main__":
    DEBUG = False
    prog = json.load(sys.stdin)

    for fn in prog['functions']:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
            mem_alias(fn)


    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)