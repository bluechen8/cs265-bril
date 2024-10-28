import json
import sys
import copy
from block_gen import block_gen

COMMUTATIVE_OPS = ['add', 'mul', 'eq']
BAD_CONST_OPS = ['call', 'ret', 'print', "store", "load", "alloc", "phi"]

def str2bool(arg):
    if arg.lower() == 'true':
        return True
    elif arg.lower() == 'false':
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

# pos: if true, ignore empty set
# loose: if true, include (union) unique keys
def merge_dicts(dicts, pos=False, loose=False):
    if len(dicts) == 0:
        return {}
    # print(dicts)
    # pick a non-empty dict
    common_items = set()
    common_keys = set()
    for d in dicts:
        if len(d) > 0:
            common_items = set(d.items())
            common_keys = set(d.keys())
            break
    all_keys = copy.deepcopy(common_keys)
    # print(common_items)
    for d in dicts:
        if pos and len(d) == 0:
            continue
        common_items &= set(d.items())
        common_keys &= set(d.keys())
        all_keys |= set(d.keys())
    # print(common_items)
    # collect unique keys
    unique_keys = all_keys - common_keys
    for key in unique_keys:
        for d in dicts:
            if key in d:
                common_items.add((key, d[key]))
                break
    return dict(common_items)

def intersect_sets(sets, pos=False):
    if len(sets) == 0:
        return set()
    # pick a non-empty set
    intersect_items = set()
    for s in sets:
        if len(s) > 0:
            intersect_items = copy.deepcopy(s)
            break
    for s in sets:
        if pos and len(s) == 0:
            continue
        intersect_items.intersection_update(s)
    return intersect_items

def union_sets(sets):
    if len(sets) == 0:
        return set()
    union_items = set()
    for s in sets:
        union_items.update(s)
    return union_items

# trivial dominator frontier for blocks
def t_dom_frontier(blocks_cfg):
    # initialize dom frontier
    worklist = [0]
    for block_id in range(len(blocks_cfg)):
        block = blocks_cfg[block_id]
        block['out'].append(set())
        len_pred = len(block['pred'])
        for _ in range(len_pred):
            block['in'].append(set())
    
    while len(worklist) > 0:
        block_id = worklist.pop(0)
        if DEBUG:
            print(f"-----Block {block_id} ({blocks_cfg[block_id].get('label')})-----")
            print(f"init_in: {blocks_cfg[block_id]['in']}")
            print(f"init_out: {blocks_cfg[block_id]['out']}")
        # compute out
        out_set = intersect_sets(blocks_cfg[block_id]['in'], pos=False)
        # all blocks are dominated by itself
        out_set.add(block_id)
        if DEBUG:
            print(f"result_out: {out_set}")
        # if out changed, update succ
        if out_set != blocks_cfg[block_id]['out'][0]:
            blocks_cfg[block_id]['out'][0] = out_set
            for succ_id in blocks_cfg[block_id]['succ']:
                blocks_cfg[succ_id]['in'][blocks_cfg[succ_id]['pred'].index(block_id)] = out_set
                if succ_id not in worklist:
                    worklist.append(succ_id)
        if DEBUG:
            print(f"worklist: {worklist}")
            print('-------------------------')

    # generate dom frontier
    dom_frontier = {}
    for block_id in range(len(blocks_cfg)):
        block = blocks_cfg[block_id]
        for in_set in block['in']:
            for in_elem in in_set:
                if in_elem not in block['out'][0]:
                    if in_elem not in dom_frontier:
                        dom_frontier[in_elem] = []
                    dom_frontier[in_elem].append(block_id)
    if DEBUG:
        print(f"dom_frontier: {dom_frontier}")
    return dom_frontier

# trivial variable -> defined block map
def t_var2block(blocks):
    var2block = {}
    for block_id in range(len(blocks)):
        block = blocks[block_id]
        for instr in block:
            dest = instr.get('dest')
            if dest is not None:
                if dest not in var2block:
                    var2block[dest] = set()
                # treat ptr type
                if isinstance(instr['type'], dict):
                    instr_type = 'ptr ' + instr['type']['ptr']
                else:
                    instr_type = instr['type']
                var2block[dest].add((block_id, instr_type))
    if DEBUG:
        print(f"var2block: {var2block}")
    return var2block

# check if a block contains phi func for one var
def has_phi(block, var):
    for instr_id, instr in enumerate(block):
        if 'op' in instr and instr['op'] == 'phi':
            dest_raw = ''.join(instr['dest'].split('.')[:-1])
            if dest_raw == var:
                return instr_id
    return None

# trivial conversion to ssa for one function
def t_to_ssa(fn):
    # iterate blocks
    blocks, blocks_cfg = block_gen(fn, dummy=True)

    # compute dominator frontier
    dom_frontier = t_dom_frontier(copy.deepcopy(blocks_cfg))

    # generate variable -> defined block map
    var2block = t_var2block(blocks)

    # insert phi functions
    var2count = {}
    for var in var2block:
        var2count[var] = 0
        # create a worklist
        worklist = []
        # initialize the worklist
        for def_block, type in var2block[var]:
            worklist.append((def_block, type))
        while len(worklist) > 0:
            def_block, type = worklist.pop(0)
            # assign a new name to each def
            for instr in blocks[def_block]:
                if instr.get('dest') == var:
                    var2count[var] += 1
                    instr['dest'] = f"{var}.{var2count[var]}"
            # insert phi functions
            if dom_frontier.get(def_block) is None: continue
            for join_block in dom_frontier[def_block]:
                if DEBUG:
                    print(f"-----Insert phi for {var} in block {join_block}-----")
                # check second instr of join block (phi or not)
                instr_idx = has_phi(blocks[join_block], var)
                if instr_idx is None:
                    var2count[var] += 1
                    instr_type = {'ptr': type.split(' ')[1]} if 'ptr' in type else type
                    blocks[join_block].insert(1, {'args': [],
                                                'dest': f"{var}.{var2count[var]}",
                                                'labels': [],
                                                'op': 'phi',
                                                'type': instr_type})
                    worklist.append((join_block, type))
    
                if DEBUG:
                    print(blocks[join_block])
    
    # iterate blocks to rename uses and complete phi functions
    phi_remove_mode = False
    worklist = [0]
    blocks_cfg[0]['in'].append({})
    while len(worklist) > 0 and not phi_remove_mode:
        # start phi remove after worklist is empty
        if len(worklist) == 0:
            if DEBUG:
                print("########Start phi remove########")
            phi_remove_mode = True
            # add all nodes
            for block_idx in range(len(blocks_cfg)):
                worklist.append(block_idx)

        block_id = worklist.pop(0)
        block = blocks[block_id]
        blocks_cfg[block_id]['touch'] += 1
        start_dic = merge_dicts(blocks_cfg[block_id]['in'], pos=True, loose=True)
        if phi_remove_mode:
            del_list = []
        if DEBUG:
            print(f"-----Block {block_id} ({blocks_cfg[block_id].get('label')})-----")
            print(f"in: {blocks_cfg[block_id]['in']}")
            print(f"start_dic: {start_dic}")
        for instr_idx, instr in enumerate(block):
            # check args first
            if 'args' in instr:
                if instr['op'] == 'phi':
                    # get dest var
                    dest_raw = ''.join(instr['dest'].split('.')[:-1])
                    if phi_remove_mode:
                        # check if args change
                        for label_idx, label in enumerate(instr['labels']):
                            pred_idx = 0
                            for pred_block_id in blocks_cfg[block_id]['pred']:
                                if label == blocks_cfg[pred_block_id]['label']:
                                    break
                                pred_idx += 1
                            new_arg = blocks_cfg[block_id]['in'][pred_idx].get(dest_raw)
                            if new_arg is None:
                                instr['args'].pop(label_idx)
                                instr['labels'].pop(label_idx)
                            elif new_arg != instr['args'][label_idx]:
                                instr['args'][label_idx] = new_arg
                                    
                        # check pred to see if we could remove phi
                        if len(instr['args']) == 2:
                            # check if one of args is the same as dest
                            if instr['dest'] in instr['args']:
                                pick_dest = (instr['args'].index(instr['dest']) + 1) % 2
                                if DEBUG:
                                    print(f"Remove {instr['dest']} and keep {instr['args'][pick_dest]}")
                                # replace dest with the other arg
                                instr['dest'] = instr['args'][pick_dest]
                                del_list.append(instr_idx)
                        elif len(instr['args']) == 1:
                            if DEBUG:
                                print(f"Remove {instr['dest']} and keep {instr['args'][0]}")
                            # replace dest with the only arg
                            instr['dest'] = instr['args'][0]
                            del_list.append(instr_idx)
                    else:
                        # check pred
                        for pred_idx, pred_block_id in enumerate(blocks_cfg[block_id]['pred']):
                            # check if already inserted
                            pred_label = blocks_cfg[pred_block_id].get('label')
                            if pred_label is None:
                                print(f"Error: block {pred_block_id} has no label")
                                exit(1)
                            if pred_label in instr['labels']:
                                continue
                            # get ssa var name
                            ssa_var = blocks_cfg[block_id]['in'][pred_idx].get(dest_raw)
                            # pred is not ready
                            if ssa_var is None:
                                continue
                            instr['args'].append(ssa_var)
                            instr['labels'].append(pred_label)
                else:
                    for arg_idx, arg in enumerate(instr['args']):
                        if phi_remove_mode:
                            arg_raw = ''.join(arg.split('.')[:-1])
                            arg = arg_raw
                        if arg in start_dic:
                            instr['args'][arg_idx] = start_dic[arg]
                            if DEBUG:
                                print(f"Replace {arg} with {start_dic[arg]}")
                        else:
                            if DEBUG:
                                print(f"Error: {arg} not defined")
            # check dest
            if 'dest' in instr:
                dest_raw = ''.join(instr['dest'].split('.')[:-1])
                start_dic[dest_raw] = instr['dest']
        
        if DEBUG:
            print(f"out start_dic: {start_dic}")

        # insert succ to worklist
        for succ_id in blocks_cfg[block_id]['succ']:
            if len(blocks_cfg[succ_id]['in']) == 0:
                # initialize in
                for _ in range(len(blocks_cfg[succ_id]['pred'])):
                    blocks_cfg[succ_id]['in'].append({})
            if blocks_cfg[succ_id]['in'][blocks_cfg[succ_id]['pred'].index(block_id)] != start_dic:
                blocks_cfg[succ_id]['in'][blocks_cfg[succ_id]['pred'].index(block_id)] = start_dic
                if succ_id not in worklist:
                    worklist.append(succ_id)
        
        # remove phi instr
        if phi_remove_mode:
            blocks[block_id] = [instr for idx, instr in enumerate(block) if idx not in del_list]

    # strip out dummy blocks
    if 'dummy_entry' in blocks_cfg[0]['label']:
        new_map = {}
        for instr in blocks[0]:
            if 'op' not in instr:
                continue
            assert instr['op'] == 'id'
            new_map[instr['args'][0]] = instr['dest']
        for arg in fn['args']:
            arg['name'] = new_map[arg['name']]
        # preserve the label, remove dummy instr
        blocks[0] = [instr for instr in blocks[0] if 'op' not in instr and 'label' in instr]
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
    return block, used_set

# trivial live variable analysis
def t_lva(fn):
    # interate blocks
    blocks, blocks_cfg = block_gen(fn, dummy=False)
    # initialize in and out table
    for block in blocks_cfg:
        for _ in range(len(block['succ'])):
            block['out'].append(set())
        block['in'].append(set())
    # initialize worklist
    worklist = []
    for block_idx in range(len(blocks_cfg)):
        block = blocks_cfg[block_idx]
        if len(block['succ']) == 0:
            worklist.append(block_idx)

    # big while loop containing both lva and dce
    dce_mode = False
    while len(worklist) > 0 or not dce_mode:
        # check worklist length
        if len(worklist) == 0:
            # liveness analysis done, start dce
            dce_mode = True
            # add all nodes
            for block_idx in range(len(blocks_cfg)):
                worklist.append(block_idx)

        block_id = worklist.pop()

        if DEBUG:
            print(f"-----Block {block_id}-----")
            print(f"out: {blocks_cfg[block_id]['out']}")

        # liveness or dce analysis
        if not dce_mode:
            used_set = t_lva_single(blocks[block_id], union_sets(blocks_cfg[block_id]['out']))
        else:
            blocks[block_id], used_set = l_dce_single(blocks[block_id], union_sets(blocks_cfg[block_id]['out']))
        if DEBUG:
            print(f"used_set: {used_set}")
        blocks_cfg[block_id]['touch'] += 1
        # if in changed, update pred
        if used_set != blocks_cfg[block_id]['in'][0]:
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

    fn["instrs"] = [inst for block in blocks for inst in block]

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
        all_const_flag = True
        # ignore labels
        if 'op' in inst:
            if DEBUG:
                print(inst)
            # ignore float
            if 'type' in inst and inst['type'] == 'float':
                continue
            if inst['op'] in BAD_CONST_OPS:
                continue
            if dest is None:
                continue
            # check if has args
            if 'args' in inst or 'value' in inst:
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

                # construct value
                # if all const, then compute it
                if all_const_flag:
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
                    inst['op'] = 'const'
                    inst.pop('args', None)
                    inst['value'] = value
                    value = 'const ' + str(value)
                else:
                    if inst['op'] in COMMUTATIVE_OPS:
                        args.sort()
                    if inst['op'] == 'id':
                        value = args[0]
                    else:
                        value = inst['op'] + ' ' + ' '.join(args)
                if DEBUG:
                    print(f"Compute the value {value}")

                # search for common value
                if inst['op'] == 'id' and value.isdecimal():
                    num = int(value)
                else:
                    num = val2num.get(value)
                if DEBUG:
                    print(f"Matched num: {num}")
                if num is None:
                    # add new num
                    val2num[value] = global_num
                    dest2num[dest] = global_num
                    num2dest[global_num] = [dest]
                    num2val[global_num] = value
                    global_num += 1
                else:
                    if DEBUG:
                        print(f"Replace {dest} with {num}")
                    inst['args'] = [num2dest[num][0]]
                    inst['op'] = 'id'
                    dest2num[dest] = num
                    num2dest[num].append(dest)
            if DEBUG:
                print_table(dest2num, val2num, num2dest, num2val)
                print('-------------------------')
    return block

# trivial local value numbering
def t_lvn(fn):
    # interate blocks
    blocks, _ = block_gen(fn, dummy=False)
    for block_id in range(len(blocks)):
        if DEBUG:
            print(f"-----Block {block_id}-----")
        blocks[block_id] = t_lvn_single(blocks[block_id])
    fn["instrs"] = [inst for block in blocks for inst in block]


if __name__ == "__main__":
    DEBUG = False
    prog = json.load(sys.stdin)

    # Analyze th program p
    for fn in prog["functions"]:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        t_to_ssa(fn)

    # local load value numbering
    for fn in prog["functions"]:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        t_lvn(fn)

    # liveness and dce
    for fn in prog["functions"]:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        t_lva(fn)

    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)