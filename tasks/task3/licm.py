import json
import sys
import copy
from block_gen import block_gen

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

# compute dominance
def comp_dom(blocks_cfg):
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

# find all natural loops
def find_loops(fn):
    blocks, blocks_cfg = block_gen(fn, dummy=False)

    # compute dominance (result is kept in blocks_cfg)
    if DEBUG:
        print("############Compute Dominance############")
    comp_dom(blocks_cfg)

    # search for back edges
    if DEBUG:
        print("############Search Back edges############")
    back_edges = []
    for block_id in range(len(blocks_cfg)):
        block = blocks_cfg[block_id]
        if DEBUG:
            print(f"-----Block {block_id} ({block.get('label')})-----")
            print(f"succ: {block['succ']}")
            print(f"out: {block['out']}")
            print("-------------------------")
        # search for succesor that dominates the block
        count = 0
        for succ_id in block['succ']:
            if succ_id in block['out'][0]:
                back_edges.append((succ_id, block_id))
                count += 1
        assert count <= 1, "Multiple back edges detected"
    if DEBUG:
        for back_edge in back_edges:
            print(f"Back edges: header:{back_edge[0]}",
                    f"({blocks_cfg[back_edge[0]]['label']})",
                    f"back:{back_edge[1]}"
                    f"({blocks_cfg[back_edge[1]]['label']})")
    # backtrace to find loop
    if DEBUG:
        print("############Find Loops############")
    loops = []
    for back_edge in back_edges:
        loop = {'header': back_edge[0]}
        root = back_edge[1]
        other_nodes = set()
        worklist = [root]
        while len(worklist) > 0:
            node = worklist.pop()
            other_nodes.add(node)
            for pred in blocks_cfg[node]['pred']:
                if pred not in other_nodes and pred != back_edge[0]:
                    worklist.append(pred)
        loop['nodes'] = list(other_nodes)
        loops.append(loop)
        if DEBUG:
            print(f"Loop: {loop}")

if __name__ == "__main__":
    DEBUG = True
    prog = json.load(sys.stdin)

    for fn in prog['functions']:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        find_loops(fn)


    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)