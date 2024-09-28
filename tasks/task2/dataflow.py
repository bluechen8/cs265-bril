import json
import sys
from block_gen import block_gen

def str2bool(arg):
    if arg.lower() == 'true':
        return True
    elif arg.lower() == 'false':
        return False
    else:
        exit(f"Unknown boolean value {arg}")

# trivial constant propagation/folding for one block
def t_cpf_single(block, dest2val):
    # iterate inst in one local block
    for inst_idx in range(len(block)):
        inst = block[inst_idx]
        dest = inst.get('dest')

        # flags
        all_const_flag = True
        const_value_flag = False

        # ignore labels
        if 'op' in inst:
            # print(inst['op'])
            # check if has args
            if 'args' in inst or 'value' in inst:
                if 'value' in inst:
                    args = [str(inst['value'])]
                else:
                    args = []
                    for arg in inst['args']:
                        if arg in dest2val:
                            # print(dest2val[arg])
                            args.append(str(dest2val[arg]))
                        else:
                            all_const_flag = False
                            args.append(arg)
            # print(args)
            # construct value
            value = 0
            if all_const_flag:
                const_value_flag = True
                match inst['op']:
                    case 'const':
                        value = int(args[0]) if inst['type'] == 'int' else str2bool(args[0])
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
                    case 'and':
                        value = str2bool(args[0]) and str2bool(args[1])
                    case 'or':
                        value = str2bool(args[0]) or str2bool(args[1])
                    case 'not':
                        value = not str2bool(args[0])
                    case 'eq':
                        value = int(args[0]) == int(args[1])
                    case 'le':
                        value = int(args[0]) <= int(args[1])
                    case 'lt':
                        value = int(args[0]) < int(args[1])
                    case 'ge':
                        value = int(args[0]) >= int(args[1])
                    case 'gt':
                        value = int(args[0]) > int(args[1])
                    case 'ne':
                        value = int(args[0]) != int(args[1])
                    case _:
                        exit(f"Unknown operator {inst['op']}")
            else:
                if len(args) == 2 and args[0] == args[1]:
                    match inst['op']:
                        case 'eq':
                            value = True
                            const_value_flag = True
                        case 'le':
                            value = True
                            const_value_flag = True
                        case 'lt':
                            value = False
                            const_value_flag = True
                        case 'ge':
                            value = True
                            const_value_flag = True
                        case 'gt':
                            value = False
                            const_value_flag = True
                        case 'ne':
                            value = False
                            const_value_flag = True
                        case _:
                            all_const_flag = False

            # check dest
            if dest is not None and const_value_flag:
                inst['op'] = 'const'
                inst.pop('args', None)
                inst['value'] = value
                dest2val[dest] = value

    return block                

# trivial constant propagation/folding
def t_cpf(fn):
    # interate blocks
    blocks, blocks_cfg = block_gen(fn)
    for block_id in range(len(blocks)):
        # print(f"-----Block {block_id}-----")
        dest2val = {}
        blocks[block_id] = t_cpf_single(blocks[block_id], dest2val)
    fn["instrs"] = [inst for block in blocks for inst in block]

if __name__ == "__main__":
    prog = json.load(sys.stdin)
    # Analyze the program p    
    for fn in prog["functions"]:
        t_cpf(fn)

    # Output the program
    json.dump(prog, sys.stdout, indent=2)