import json
import sys

TERMINATORS = 'br', 'jmp', 'ret'

# generate basic blocks
def block_gen(fn):
    blocks = []
    # iterate inst
    cur_block = []
    for instr in fn["instrs"]:
        if 'op' in instr:
            # terminator, add to current block and start a new
            if instr['op'] in TERMINATORS:
                cur_block.append(instr)
                blocks.append(cur_block)
                cur_block = []
            else:
                cur_block.append(instr)
        else:
            # label
            # add it if it is the first, or end before it
            if len(cur_block) > 0:
                blocks.append(cur_block)
                cur_block = [instr]
            else:
                cur_block.append(instr)

    # if cur_lock has something, add it
    if len(cur_block) > 0:
        blocks.append(cur_block)
    
    return blocks

if __name__ == "__main__":
    import briltxt
    prog = json.load(sys.stdin)
    for fidx, fn in enumerate(prog["functions"]):
        print(f"-----Function {fidx}-----")
        blocks = block_gen(fn)
        for bidx, block in enumerate(blocks):
            print(f"-----Block {bidx}-----")
            for instr in block:
                if 'op' in instr:
                    print(briltxt.instr_to_string(instr))
                else:
                    print(f".{instr['label']}:")
