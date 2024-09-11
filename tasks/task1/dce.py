import json
import sys
from block_gen import block_gen

# do a single pass for global dead code elimination
def g_dce_single(fn):
    # Arg set and dest set
    arg_set = set()
    dest_set = set()
    # Skim the function for args and dests
    for instr in fn["instrs"]:
        if "args" in instr:
            arg_set.update(instr["args"])
        if "dest" in instr:
            dest_set.add(instr["dest"])
    # Variable not used
    unused_set = dest_set - arg_set
    # Remove unused variables
    fn["instrs"] = [instr for instr in fn["instrs"] if instr.get("dest") not in unused_set]
    # return the size of unused_set
    return len(unused_set)

# passes for global dead code elimination
def g_dce(fn):
    # call g_dce_single until no more unused variables
    count = 0
    while g_dce_single(fn):
        count += 1
    return count

# do a single pass for local dead code elimination
def l_dce_single(block):
    # unused dict {variable: index}
    unused = {}
    # delete inst list
    del_list = []
    # interate inst in one local block
    for idx, inst in enumerate(block):
        # ignore labels
        if 'op' in inst:
            # process args first
            # pop args from unused
            if 'args' in inst:
                for arg in inst["args"]:
                    unused.pop(arg, None)
            # process dest
            # if dest is in unused, 
            # add the inst (pointed by unused) to del_list
            if 'dest' in inst:
                if inst['dest'] in unused:
                    del_list.append(unused[inst['dest']])
                else:
                    unused[inst['dest']] = idx
    # del_list += list(unused.values())
    block = [inst for idx, inst in enumerate(block) if idx not in del_list]
    return block, len(del_list)

# passes for local dead code elimination
def l_dce(fn):
    # interate blocks
    blocks = block_gen(fn)
    count = 0
    for block_id in range(len(blocks)):
        # call l_dce_single until no more unused variables
        while True:
            blocks[block_id], num_del = l_dce_single(blocks[block_id])
            if num_del == 0:
                break
            count += 1

    fn["instrs"] = [inst for block in blocks for inst in block]
    return count


if __name__ == "__main__":
    prog = json.load(sys.stdin)
    # Analyze the program per-func
    for fn in prog["functions"]:
        while g_dce(fn) or l_dce(fn):
            pass

    # Output the program
    json.dump(prog, sys.stdout, indent=2)
