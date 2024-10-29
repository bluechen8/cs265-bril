import json
import sys
import copy
from block_gen import block_gen

def merge_ptr_dict(dicts):
    if len(dicts) == 0:
        return dict()
    # extract all keys from list of dicts
    all_keys = set()
    for d in dicts:
        all_keys |= set(d.keys())
    # union w.r.t. each key
    union_dict = dict()
    for key in all_keys:
        union_dict[key] = set()
        for d in dicts:
            if key in d:
                union_dict[key].update(d[key])
    return union_dict

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

# Memoy op alias analysis
def mem_alias(fn):
    blocks, blocks_cfg = block_gen(fn, dummy=False)
    # use "block_id instr_id" as the id for allocation
    # initialize
    for block in blocks_cfg:
        for _ in range(len(block['pred'])):
            block['in'].append(dict())
        block['out'].append(dict())
    # iterate until stable
    worklist = [0]
    # add first block
    # if the funct has pointer args, then assume it points to everywhere
    func_args = fn.get('args')
    if func_args:
        blocks_cfg[0]['in'].append(dict())
        for arg in func_args:
            if isinstance(arg['type'], dict):
                blocks_cfg[0]['in'][-1][arg['name']] = set()
                blocks_cfg[0]['in'][-1][arg['name']].add('all')
    
    while len(worklist) > 0:
        block_id = worklist.pop(0)
        if DEBUG:
            print(f"-----Block {block_id}({blocks_cfg[block_id].get('label')})-----")
        ptr_dict = mem_alias_single(blocks, blocks_cfg, block_id)
        if DEBUG:
            print(f"OUT: {ptr_dict}")
        # check if the out has changed
        out_update_flag = ptr_dict != blocks_cfg[block_id]['out'][0]
        if out_update_flag:
            blocks_cfg[block_id]['out'][0] = copy.deepcopy(ptr_dict)
            if DEBUG:
                print(f"OUT updated")
        for succ_id in blocks_cfg[block_id]['succ']:
            in_idx = blocks_cfg[succ_id]['pred'].index(block_id)
            if out_update_flag or blocks_cfg[succ_id]['touch'] == 0:
                blocks_cfg[succ_id]['touch'] += 1
                blocks_cfg[succ_id]['in'][in_idx] = copy.deepcopy(ptr_dict)
                worklist.append(succ_id)
        if DEBUG:
            print(f"worklist: {worklist}")

    # construct the final map
    ptr_map = dict()
    for block_id in range(len(blocks_cfg)):
        for key in blocks_cfg[block_id]['out'][0]:
            if key in ptr_map:
                # since above analysis merges in fixed point, the value should be the same
                assert ptr_map[key] == blocks_cfg[block_id]['out'][0][key]
            else:
                ptr_map[key] = copy.deepcopy(blocks_cfg[block_id]['out'][0][key])
        # clear cfg
        blocks_cfg[block_id]['in'] = []
        blocks_cfg[block_id]['out'] = []
        blocks_cfg[block_id]['touch'] = 0
    if DEBUG:
        print(f"Final map: {ptr_map}")

    # passes for dead store elimination
    # initialize
    for block_idx in reversed(range(len(blocks_cfg))):
        block = blocks_cfg[block_idx]
        for _ in range(len(block['succ'])):
            block['out'].append(set())
        block['in'].append(set())
        worklist.append(block_idx)
    # iterate until stable
    eliminate_flag = False
    while len(worklist) > 0 or not eliminate_flag:
        if len(worklist) == 0:
            eliminate_flag = True
            # refill worklist
            for block_idx in reversed(range(len(blocks_cfg))):
                worklist.append(block_idx)
            if DEBUG:
                print("*******Eliminate pass*******")
        block_id = worklist.pop(0)
        if DEBUG:
            print(f"-----Block {block_id}({blocks_cfg[block_id].get('label')})-----")
        # pull out the store set
        store_set = intersect_sets(blocks_cfg[block_id]['out'])
        if DEBUG:
            print(f"OUT: {store_set}")

        # iterate through the instructions
        del_list = []
        for instr_idx in reversed(range(len(blocks[block_id]))):
            instr = blocks[block_id][instr_idx]
            op = instr.get('op')
            # check if instr is store
            if op == 'store':
                store_ptr = instr['args'][0]
                # add store ptr to store list
                # check if the store ptr is in the store set
                if store_ptr in store_set:
                    del_list.append(instr_idx)
                    if DEBUG:
                        print(f"Instr removed {instr}")
                else:
                    store_set.add(store_ptr)
            elif op == 'load':
                # check if instr is load
                # load instr should remove ptr
                # may collide with its location
                load_ptr = instr['args'][0]
                load_ptr_loc_set = ptr_map[load_ptr]
                del_store_set = set()
                for store_ptr in store_set:
                    store_ptr_loc_set = ptr_map[store_ptr]
                    # check if the store ptr points to the load ptr
                    if 'all' in store_ptr_loc_set or 'all' in load_ptr_loc_set:
                        del_store_set.add(store_ptr)
                        if DEBUG:
                            print(f"Remove {store_ptr} due to {load_ptr}")
                    elif len(store_ptr_loc_set.intersection(load_ptr_loc_set)) > 0:
                        del_store_set.add(store_ptr)
                        if DEBUG:
                            print(f"Remove {store_ptr} due to {load_ptr}")
                store_set -= del_store_set
        if DEBUG:
            print(f"IN: {store_set}")
        # remove the store instr if eliminate flag is true
        if eliminate_flag:
            if DEBUG:
                print(f"del_list: {del_list}")
            blocks[block_id] = [instr for instr_idx, instr in enumerate(blocks[block_id]) if instr_idx not in del_list]

        # check if the in has changed
        in_update_flag = store_set != blocks_cfg[block_id]['in'][0]
        if in_update_flag:
            blocks_cfg[block_id]['in'][0] = copy.deepcopy(store_set)
            if DEBUG:
                print(f"IN updated")
        for pred_id in blocks_cfg[block_id]['pred']:
            out_idx = blocks_cfg[pred_id]['succ'].index(block_id)
            if in_update_flag:
                blocks_cfg[pred_id]['out'][out_idx] = copy.deepcopy(store_set)
                if pred_id not in worklist:
                    worklist.append(pred_id)
        if DEBUG:
            print(f"worklist: {worklist}")
    
    fn["instrs"] = [inst for block in blocks for inst in block]

def mem_alias_single(blocks, blocks_cfg, block_id):
    # union the in of all preds to get list of pointer
    ptr_dict = merge_ptr_dict(blocks_cfg[block_id]['in'])
    if DEBUG:
        print(f"IN: {ptr_dict}")
    # iterate through the instructions
    for instr_id, instr in enumerate(blocks[block_id]):
        op = instr.get('op')
        dest_var = instr.get('dest')
        update_flag = True
        update_str = ''
        # check if instr is alloc
        if op == 'alloc':
            update_str = "alloc"
            # add the alloc id to the ptr_dict
            # check if ptr_dict has the key
            ptr_dict[dest_var] = set()
            ptr_dict[dest_var].add(f"{block_id} {instr_id}")
        elif op == 'ptradd':
            update_str = "ptradd"
            # the first arg is pointer
            # the dest var should cover locations pointed by this pointer
            ptr_dict[dest_var] = set()
            ptr_dict[dest_var].update(ptr_dict[instr['args'][0]])
        elif op == 'load':
            update_str = "load"
            # if the dest is a pointer, it should point to everywhere
            if isinstance(instr['type'], dict):
                ptr_dict[dest_var] = set()
                ptr_dict[dest_var].add('all')
        elif op == 'id':
            update_str = "id"
            # if the dest is a pointer, it should cover locations pointed by the src
            if isinstance(instr['type'], dict):
                ptr_dict[dest_var] = set()
                ptr_dict[dest_var].update(ptr_dict[instr['args'][0]])
        elif op == 'phi' and isinstance(instr['type'], dict):
            update_str = "phi"
            ptr_dict[dest_var] = set()
            # union all args
            for arg in instr['args']:
                if arg in ptr_dict:
                    ptr_dict[dest_var].update(ptr_dict[arg])
        elif op == 'call' and 'dest' in instr and isinstance(instr['type'], dict):
            update_str = "call"
            # if the dest is a pointer, it should point to everywhere
            ptr_dict[dest_var] = set()
            ptr_dict[dest_var].add('all')
        else:
            update_flag = False

        if DEBUG and update_flag:
            print(f"{instr_id}({update_str}): {ptr_dict}")

    return ptr_dict

if __name__ == "__main__":
    DEBUG = False
    prog = json.load(sys.stdin)

    for fn in prog['functions']:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        mem_alias(fn)


    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)