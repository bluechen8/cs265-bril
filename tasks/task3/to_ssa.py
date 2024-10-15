import json
import sys
import copy
from block_gen import block_gen

def merge_dicts(dicts, pos=False):
    if len(dicts) == 0:
        return {}
    # print(dicts)
    # pick a non-empty dict
    common_items = set()
    for d in dicts:
        if len(d) > 0:
            common_items = set(d.items())
            break
    # print(common_items)
    for d in dicts:
        if pos and len(d) == 0:
            continue
        common_items &= set(d.items())
    # print(common_items)
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
        # if len_pred <= 1:
        #     worklist.append(block_id)
    
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
                var2block[dest].add((block_id, instr['type']))
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

    # insert phi functionsz
    var2count = {}
    for var in var2block:
        var2count[var] = 0
        for def_block, type in var2block[var]:
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
                    blocks[join_block].insert(1, {'args': [],
                                                'dest': f"{var}.{var2count[var]}",
                                                'labels': [],
                                                'op': 'phi',
                                                'type': type})
    
                if DEBUG:
                    print(blocks[join_block])
    
    # iterate blocks to rename uses and complete phi functions
    worklist = [0]
    blocks_cfg[0]['in'].append({})
    while len(worklist) > 0:
        block_id = worklist.pop(0)
        block = blocks[block_id]
        blocks_cfg[block_id]['touch'] += 1
        start_dic = merge_dicts(blocks_cfg[block_id]['in'], pos=True)
        if DEBUG:
            print(f"-----Block {block_id} ({blocks_cfg[block_id].get('label')})-----")
            print(f"in: {blocks_cfg[block_id]['in']}")
            print(f"start_dic: {start_dic}")
        for instr in block:
            # check args first
            if 'args' in instr:
                if instr['op'] == 'phi':
                    # get dest var
                    dest_raw = ''.join(instr['dest'].split('.')[:-1])
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
                    for arg in instr['args']:
                        if arg in start_dic:
                            instr['args'][instr['args'].index(arg)] = start_dic[arg]
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
        blocks.pop(0)
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