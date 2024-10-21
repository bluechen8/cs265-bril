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
            print(f"Back edges: front:{back_edge[0]}",
                    f"({blocks_cfg[back_edge[0]]['label']})",
                    f"back:{back_edge[1]}"
                    f"({blocks_cfg[back_edge[1]]['label']})")
    # backtrace to find loop
    if DEBUG:
        print("############Find Loops############")
    loops = []
    for back_edge in back_edges:
        loop = {}
        # find the pre-header
        # preheader is the only predecessor of the header
        assert len(blocks_cfg[back_edge[0]]['pred']) == 2, "Multiple pre-header detected"
        preheader_idx = (blocks_cfg[back_edge[0]]['pred'].index(back_edge[1]) + 1) % 2
        loop['preheader'] = blocks_cfg[back_edge[0]]['pred'][preheader_idx]
        back = back_edge[1]
        other_nodes = set()
        worklist = [back]
        while len(worklist) > 0:
            node = worklist.pop()
            other_nodes.add(node)
            for pred in blocks_cfg[node]['pred']:
                if pred not in other_nodes and pred != back_edge[0]:
                    worklist.append(pred)
        
        loop['nodes'] = list(other_nodes)
        loop['nodes'].append(back_edge[0])  # add front to nodes
        # determine whether front or back is the header
        header_list = []
        exit_list = []
        for header_can in back_edge:
            # header should have one successor exit outside the loop
            # and the header should dominate the exit
            block = blocks_cfg[header_can]
            for succ_id in block['succ']:
                if succ_id not in loop['nodes']:
                    if header_can in blocks_cfg[succ_id]['out'][0]:
                        if DEBUG:
                            print(f"Header: {header_can}({block.get('label')})")
                            print(f"Exit: {succ_id}({blocks_cfg[succ_id].get('label')})")
                        header_list.append(header_can)
                        exit_list.append(succ_id)
                        break
        assert len(header_list) == 1, "Multiple header detected"
        assert len(exit_list) == 1, "Multiple exit detected"
        loop['header'] = header_list[0]
        loop['exit'] = exit_list[0]
        loops.append(loop)
        if DEBUG:
            print(f"Loop: {loop}")
    return loops, blocks, blocks_cfg

# find loop invariant code
def find_loop_invariant(loop, blocks):
    # first pass: collect all args and dest
    args_set = set()
    dest_set = set()
    for block_id in loop['nodes']:
        block = blocks[block_id]
        for inst in block:
            if 'op' in inst:
                if 'dest' in inst:
                    dest_set.add(inst['dest'])
                if 'args' in inst:
                    args_set.update(inst['args'])
    if DEBUG:
        print(f"args_set: {args_set}")
        print(f"dest_set: {dest_set}")
    # second pass: find loop invariant
    loop_invariant_set = set()
    update_flag = True
    while update_flag:
        update_flag = False
        for block_id in loop['nodes']:
            block = blocks[block_id]
            for inst in block:
                if 'op' in inst:
                    # if arg not in dest_set (defined outside the loop)
                    # if arg is in the loop invariant set
                    invariant_flag = True
                    if 'args' in inst:
                        for arg in inst['args']:
                            if arg in dest_set and arg not in loop_invariant_set:
                                invariant_flag = False
                                break
                        if invariant_flag and 'dest' in inst \
                            and inst['dest'] not in loop_invariant_set:
                            loop_invariant_set.add(inst['dest'])
                            update_flag = True
                            if DEBUG:
                                print(f"Add loop invariant: {inst['dest']}")
    if DEBUG:
        print(f"Loop invariant: {loop_invariant_set}")

    return loop_invariant_set

# loop invariant code motion
def licm(fn):
    loops, blocks, blocks_cfg = find_loops(fn)
    for loop in loops:
        if DEBUG:
            print(f"-----Loop {loop}-----")
        loop_invariant_set = find_loop_invariant(loop, blocks)
        # hoist loop invariant code
        hoisted_inst = []
        for block_id in loop['nodes']:
            # check if this block dominates the exit
            if block_id not in blocks_cfg[loop['exit']]['out'][0]:
                if DEBUG:
                    print(f"Block {block_id}({blocks_cfg[block_id]['label']}) does not dominate the exit")
                continue
            block = blocks[block_id]
            del_list = []
            for inst_idx, inst in enumerate(block):
                if 'op' in inst and inst.get('dest') in loop_invariant_set:
                    hoisted_inst.append(inst)
                    del_list.append(inst_idx)
                    if DEBUG:
                        print(f"Hoist: {inst}")
            blocks[block_id] = [inst for idx, inst in enumerate(block) if idx not in del_list]
        # insert hoisted code to preheader
        blocks[loop['preheader']] += hoisted_inst
    fn["instrs"] = [inst for block in blocks for inst in block]

if __name__ == "__main__":
    DEBUG = False
    prog = json.load(sys.stdin)

    for fn in prog['functions']:
        if DEBUG:
            print(f"-----Function {fn['name']}-----")
        licm(fn)


    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)