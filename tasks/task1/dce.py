import json
import sys

# do a single pass for global dead code elimination
def g_dce_single(prog):
    # Arg set and dest set
    arg_set = set()
    dest_set = set()
    # Skim the program for args and dests
    for fn in prog["functions"]:
        for instr in fn["instrs"]:
            if "args" in instr:
                arg_set.update(instr["args"])
            if "dest" in instr:
                dest_set.add(instr["dest"])
    # Variable not used
    unused_set = dest_set - arg_set
    # Remove unused variables
    for fn in prog["functions"]:
        fn["instrs"] = [instr for instr in fn["instrs"] if instr.get("dest") not in unused_set]
    # return the size of unused_set
    return len(unused_set)

# passes for global dead code elimination
def g_dce(prog):
    # call g_dce_single until no more unused variables
    while g_dce_single(prog):
        pass

if __name__ == "__main__":
    prog = json.load(sys.stdin)
    g_dce(prog)
    # Output the program
    json.dump(prog, sys.stdout, indent=2)
