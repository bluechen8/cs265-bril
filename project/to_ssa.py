import json
import sys
import copy
from block_gen import block_gen

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
                    if 'taint' in instr['type']:
                        instr_type = instr['type']['taint'] + ' '
                    else:
                        instr_type = ''
                    if 'ptr' in instr['type']:
                        instr_type = 'ptr ' + instr['type']['ptr']
                    else:
                        instr_type = instr['type']['prim']
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
                    instr_type = {}
                    if 'private' in type or 'public' in type:
                        instr_type['taint'] = type.split(' ')[0]
                        if 'ptr' in type:
                            instr_type['ptr'] = type.split(' ')[2]
                        else:
                            instr_type['prim'] = type.split(' ')[1]
                    elif 'ptr' in type:
                        instr_type['ptr'] = type.split(' ')[1]
                    else:
                        instr_type = type
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
                if DEBUG:
                    print(f"{succ_id} in changed: {blocks_cfg[succ_id]['in'][blocks_cfg[succ_id]['pred'].index(block_id)]}")
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

if __name__ == "__main__":
    DEBUG = False
    prog = json.load(sys.stdin)

    # Analyze th program p
    for fn in prog["functions"]:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        t_to_ssa(fn)

    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)