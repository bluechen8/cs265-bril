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
        else:
            update_flag = False

        if DEBUG and update_flag:
            print(f"{instr_id}({update_str}): {ptr_dict}")

    return ptr_dict

if __name__ == "__main__":
    DEBUG = True
    prog = json.load(sys.stdin)

    for fn in prog['functions']:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
            mem_alias(fn)


    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)