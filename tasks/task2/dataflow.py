import json
import sys
from block_gen import block_gen

DEBUG = False

BAD_CONST_OPS = ['call']

def str2bool(arg):
    if arg.lower() == 'true':
        return True
    elif arg.lower() == 'false':
        return False
    else:
        exit(f"Unknown boolean value {arg}")

def merge_dicts(dicts):
    if len(dicts) == 0:
        return {}
    # print(dicts)
    common_items = set(dicts[0].items())
    # print(common_items)
    for d in dicts[1:]:
        common_items &= set(d.items())
    # print(common_items)
    return dict(common_items)

def union_sets(sets):
    if len(sets) == 0:
        return set()
    union_items = set()
    for s in sets:
        union_items.update(s)
    return union_items

# trivial constant propagation/folding for one block
def t_cpf_single(block, dest2val):
    # iterate inst in one local block
    for inst_idx in range(len(block)):
        inst = block[inst_idx]
        dest = inst.get('dest')

        # flags
        all_const_flag = True
        const_value_flag = False

        # ignore float
        if 'type' in inst and inst['type'] == 'float':
            continue

        # ignore labels
        if 'op' in inst and inst['op'] not in BAD_CONST_OPS:
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
            else:
                # pass if no args
                continue
            # print(args)
            # construct value
            value = 0
            if all_const_flag and dest is not None:
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
                        value = int(args[0]) if inst['type'] == 'int' else str2bool(args[0])
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

    return block, dest2val

# trivial constant propagation/folding
def t_cpf(fn):
    # interate blocks
    blocks, blocks_cfg = block_gen(fn)
    # initialize in and out table
    for block in blocks_cfg:
        for _ in range(len(block['pred'])):
            block['in'].append({})
        block['out'].append({})
    # initialize worklist
    worklist = [0]
    while len(worklist) > 0:
        block_id = worklist.pop()
        # print(f"-----Block {block_id}-----")
        blocks[block_id], dest2val = t_cpf_single(blocks[block_id], merge_dicts(blocks_cfg[block_id]['in']))
        blocks_cfg[block_id]['touch'] += 1
        # if out changed, update succ
        if dest2val != blocks_cfg[block_id]['out'][0]:
            # print(f"not equal {dest2val} {blocks_cfg[block_id]['out'][0]}")
            for succ_id in blocks_cfg[block_id]['succ']:
                if succ_id not in worklist:
                    worklist.append(succ_id)
                blocks_cfg[succ_id]['in'][blocks_cfg[succ_id]['pred'].index(block_id)] = dest2val
            blocks_cfg[block_id]['out'][0] = dest2val
        else:
            # if succ has not been touched, add to worklist
            for succ_id in blocks_cfg[block_id]['succ']:
                if succ_id not in worklist and blocks_cfg[succ_id]['touch'] == 0:
                    worklist.append(succ_id)
        # print(block_id)
        # print(dest2val)
        # print(worklist)
        # print('-------------------------')
    fn["instrs"] = [inst for block in blocks for inst in block]

# trivial live variable analysis for one block
def t_lva_single(block, used_set):
    if DEBUG:
        print(f"initial used_set: {used_set}")
    # iterate inst in one local block (reverse order)
    for inst_idx in reversed(range(len(block))):
        inst = block[inst_idx]
        if DEBUG:
            print(f"[+] inst dut: {inst}")
        # check dest variable
        # new definition -> clear used_set
        dest = inst.get('dest')
        if dest is not None:
            used_set.discard(dest)
            if DEBUG:
                print(f"[++] discard {dest}")
        # check args variables
        # args -> used -> add to used_set
        if 'args' in inst:
            for arg in inst['args']:
                used_set.add(arg)
                if DEBUG:
                    print(f"[++] add {arg}")
    return used_set

# trivial local dead code elimination for one block
def l_dce_single(block, used_set):
    # delete inst list
    del_list = []
    # interate inst in one local block
    for inst_idx in reversed(range(len(block))):
        inst = block[inst_idx]
        # ignore labels
        if 'op' in inst:
            # process dest
            dest = inst.get('dest')
            if dest is not None:
                if dest not in used_set:
                    del_list.append(inst_idx)
                else:
                    used_set.remove(dest)
            # process args
            if inst_idx in del_list:
                continue
            if 'args' in inst:
                for arg in inst["args"]:
                    used_set.add(arg)

    block = [inst for idx, inst in enumerate(block) if idx not in del_list]
    return block, len(del_list)

# trivial live variable analysis
def t_lva(block):
    # interate blocks
    blocks, blocks_cfg = block_gen(fn)
    # initialize in and out table
    for block in blocks_cfg:
        for _ in range(len(block['succ'])):
            block['out'].append(set())
        block['in'].append(set())
    # initialize worklist
    worklist = []
    # print(blocks_cfg)
    for block_idx in range(len(blocks_cfg)):
        block = blocks_cfg[block_idx]
        if len(block['succ']) == 0:
            worklist.append(block_idx)
    # print(worklist)
    while len(worklist) > 0:
        block_id = worklist.pop()
        if DEBUG:
            print(f"-----Block {block_id}-----")
            print(f"out: {blocks_cfg[block_id]['out']}")
        used_set = t_lva_single(blocks[block_id], union_sets(blocks_cfg[block_id]['out']))
        if DEBUG:
            print(f"used_set: {used_set}")
        blocks_cfg[block_id]['touch'] += 1
        # if in changed, update pred
        if used_set != blocks_cfg[block_id]['in'][0]:
            # print(f"not equal {used_set} {blocks_cfg[block_id]['in'][0]}")
            for pred_id in blocks_cfg[block_id]['pred']:
                if pred_id not in worklist:
                    worklist.append(pred_id)
                blocks_cfg[pred_id]['out'][blocks_cfg[pred_id]['succ'].index(block_id)] = used_set
            blocks_cfg[block_id]['in'][0] = used_set
        else:
            # if pred has not been touched, add to worklist
            for pred_id in blocks_cfg[block_id]['pred']:
                if pred_id not in worklist and blocks_cfg[pred_id]['touch'] == 0:
                    worklist.append(pred_id)
        if DEBUG:
            print(f"worklist: {worklist}")
            print('-------------------------')

    # local dead code elimination
    if DEBUG:
        print(f"-----Local Dead Code Elimination-----")
    for block_id in range(len(blocks)):
        # call l_dce_single until no more unused variables
        while True:
            used_set = set() if len(blocks_cfg[block_id]['out']) == 0 else union_sets(blocks_cfg[block_id]['out'])
            if DEBUG:
                print(f"-----Block {block_id}-----")
                print('out:')
                for cur_set in blocks_cfg[block_id]['out']:
                    print(cur_set)
                print('in:')
                for cur_set in blocks_cfg[block_id]['in']:
                    print(cur_set)

            blocks[block_id], num_del = l_dce_single(blocks[block_id], used_set)
            if num_del == 0:
                break

    fn["instrs"] = [inst for block in blocks for inst in block]


if __name__ == "__main__":
    prog = json.load(sys.stdin)
    # Analyze the program p    
    for fn in prog["functions"]:
        t_cpf(fn)

    for fn in prog["functions"]:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        t_lva(fn)

    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)

    # test merge
    # d1 = {'a': 1, 'b': 2, 'c': 3}
    # d2 = {'a': 12, 'b': 2, 'c': 3}
    # d3 = {'a': 1, 'b': 2, 'c': 33}
    # d1 = {}
    # d2 = {}
    # d3 = {}
    # print(merge_dicts([d1, d2, d3]))