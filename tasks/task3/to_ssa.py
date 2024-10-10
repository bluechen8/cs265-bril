import json
import sys
import copy
from block_gen import block_gen

def intersect_sets(sets):
    if len(sets) == 0:
        return set()
    intersect_items = copy.deepcopy(sets[0])
    for s in sets:
        intersect_items.intersection_update(s)
    return intersect_items


# trivial dominator frontier for blocks
def t_dom_frontier(blocks_cfg):
    # initialize dom frontier
    # add single pred block to worklist
    worklist = []
    for block_id in range(len(blocks_cfg)):
        block = blocks_cfg[block_id]
        block['out'].append(set())
        len_pred = len(block['pred'])
        for _ in range(len_pred):
            block['in'].append(set())
        if len_pred <= 1:
            worklist.append(block_id)
    
    while len(worklist) > 0:
        block_id = worklist.pop(0)
        if DEBUG:
            print(f"-----Block {block_id}-----")
            print(f"init_in: {blocks_cfg[block_id]['in']}")
            print(f"init_out: {blocks_cfg[block_id]['out']}")
        # compute out
        out_set = intersect_sets(blocks_cfg[block_id]['in'])
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
                print(f"in_elem: {in_elem}")
                if in_elem not in block['out'][0]:
                    if in_elem not in dom_frontier:
                        dom_frontier[in_elem] = []
                    dom_frontier[in_elem].append(block_id)
    if DEBUG:
        print(f"dom_frontier: {dom_frontier}")
    return dom_frontier


# trivial conversion to ssa for one function
def t_to_ssa(fn):
    # iterate blocks
    blocks, blocks_cfg = block_gen(fn)

    # compute dominator frontier
    dom_frontier = t_dom_frontier(blocks_cfg)


if __name__ == "__main__":
    DEBUG = True
    prog = json.load(sys.stdin)

    # Analyze th program p
    for fn in prog["functions"]:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        t_to_ssa(fn)

    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)