import json
import sys
import copy
from block_gen import block_gen


def t_ssa_to(fn):
    # remove all phi functions
    # remove variable names after '.'
    # func args
    if 'args' in fn:
        for arg in fn['args']:
            arg['name'] = arg['name'].split('.')[0]
    # instrs
    del_list = []
    for instr_idx, instr in enumerate(fn['instrs']):
        # check if instr is phi
        if 'op' in instr and instr['op'] == 'phi':
            del_list.append(instr_idx)
            continue
        # dest
        if 'dest' in instr:
            instr['dest'] = instr['dest'].split('.')[0]
        # args
        if 'args' in instr:
            for arg_idx in range(len(instr['args'])):
                instr['args'][arg_idx] = instr['args'][arg_idx].split('.')[0]

    fn['instrs'] = [instr for idx, instr in enumerate(fn['instrs']) if idx not in del_list]



if __name__ == "__main__":
    DEBUG = False
    prog = json.load(sys.stdin)

    # Analyze the program p
    for fn in prog["functions"]:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        t_ssa_to(fn)

    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)