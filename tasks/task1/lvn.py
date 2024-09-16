import json
import sys
from block_gen import block_gen

COMMUTATIVE_OPS = ['add', 'mul', 'sub', 'eq']

def str2bool(arg):
    if arg == 'true':
        return True
    elif arg == 'false':
        return False
    else:
        exit(f"Unknown boolean value {arg}")

# print current table
def print_table(dest2num, val2num, num2dest, num2val):
    for num in num2val.keys():
        print(f"{num}: {num2val[num]} | {num2dest[num]}")
        # test dest2num
        for dest in num2dest[num]:
            assert dest2num[dest] == num
        # test val2num
        assert val2num[num2val[num]] == num

# trivial local value numbering for one block
def t_lvn_single(block):
    # declare table
    dest2num = {}
    val2num = {}
    num2dest = {}
    num2val = {}
    global_num = 0

    # iterate inst in one local block
    for inst_idx in range(len(block)):
        inst = block[inst_idx]
        dest = inst.get('dest')
        # flags
        clobber_flag = False
        all_const_flag = True
        # ignore labels
        if 'op' in inst:
            # check if has dest
            if 'dest' in inst:
                # if dest in table, set clobber flag
                if dest2num.get(dest) is not None:
                    old_num = dest2num[dest]
                    old_val = num2val[old_num]
                    clobber_flag = True
            # check if has args
            if 'args' in inst or 'value' in inst:
                # print(inst)
                if 'value' in inst:
                    args = [str(inst['value'])]
                    all_const_flag = False
                else:  # 'args' in inst
                    args = [str(dest2num[arg]) if dest2num.get(arg) is not None \
                        else arg for arg in inst['args']]
                    args = []
                    for arg in inst['args']:
                        argnum = dest2num.get(arg)
                        if argnum is not None:
                            if 'const' in num2val[argnum]:
                                args.append(num2val[argnum].split(' ')[1])
                                continue
                            else:
                                args.append(str(argnum))
                        else:
                            args.append(arg)
                        all_const_flag = False
                # print(args)

                # construct value
                # if all const, then compute it
                if all_const_flag:
                    match inst['op']:
                        case 'add':
                            value = int(args[0]) + int(args[1])
                        case 'sub':
                            value = int(args[0]) - int(args[1])
                        case 'mul':
                            value = int(args[0]) * int(args[1])
                        case 'div':
                            value = int(args[0]) // int(args[1])
                        case 'id':
                            value = int(args[0])
                        case 'print':
                            value = args[0]
                        case _:
                            exit(f"Unknown operator {inst['op']}")
                    if inst['op'] != 'print':
                        inst['op'] = 'const'
                        inst.pop('args', None)
                        inst['value'] = value
                    value = 'const ' + str(value)
                else:
                    if inst['op'] in COMMUTATIVE_OPS:
                        args.sort()
                    value = inst['op'] + ' ' + ' '.join(args)
                # print(value)

                # search for common value
                num = val2num.get(value)
                if num is None:
                    # add new num
                    val2num[value] = global_num
                    dest2num[dest] = global_num
                    num2dest[global_num] = [dest]
                    num2val[global_num] = value
                    global_num += 1
                else:
                    inst['args'] = [num2dest[num][0]]
                    if inst['op'] != 'print':
                        inst['op'] = 'id'
                        dest2num[dest] = num
                        num2dest[num].append(dest)

            # Check clobber flag
            if clobber_flag:
                num2dest[old_num].remove(dest)
                if len(num2dest[old_num]) == 0:
                    num2val.pop(old_num, None)
                    val2num.pop(old_val, None)
        # print(inst)
        # print_table(dest2num, val2num, num2dest, num2val)
    return block

# trivial local value numbering
def t_lvn(fn):
    # interate blocks
    blocks = block_gen(fn)
    count = 0
    for block_id in range(len(blocks)):
        # print(f"-----Block {block_id}-----")
        blocks[block_id] = t_lvn_single(blocks[block_id])
    fn["instrs"] = [inst for block in blocks for inst in block]

if __name__ == "__main__":
    prog = json.load(sys.stdin)
    # Analyze the program p    
    for fn in prog["functions"]:
        t_lvn(fn)

    # Output the program
    json.dump(prog, sys.stdout, indent=2)