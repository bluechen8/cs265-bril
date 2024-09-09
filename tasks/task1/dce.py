import json
import sys

if __name__ == "__main__":
    prog = json.load(sys.stdin)
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
    # Output the program
    json.dump(prog, sys.stdout, indent=2)
