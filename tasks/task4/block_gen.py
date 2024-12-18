import json
import sys

TERMINATORS = 'br', 'jmp', 'ret'

# generate basic blocks
def block_gen(fn, dummy=False):
    blocks = []
    block_idx = 0
    label2pred = {}
    label2succ = {}
    blocks_cfg = []
    cur_block = []
    cur_block_cfg = {'pred': [], 'succ': [], 'touch': 0, 'in': [], 'out': []}
    # insert a label if the first instr is not a label
    if 'op' in fn['instrs'][0]:
        fn['instrs'].insert(0, {'label': 'entry'})

    # add args to the first block
    if dummy and 'args' in fn:
        fn['instrs'].insert(0, {'label': 'dummy_entry'})
        if 'args' in fn:
            for arg in fn['args']:
                fn['instrs'].insert(1,
                                    {'args': [arg['name']],
                                    'dest': arg['name'],
                                    'op': 'id',
                                    'type': arg['type']})
    # iterate inst
    for instr in fn["instrs"]:
        if 'op' in instr:
            # check if op is the first in the block
            # then drop it
            # every block starts with a label
            if len(cur_block) == 0:
                continue
            # terminator, add to current block and start a new
            if instr['op'] in TERMINATORS:
                # check terminator
                if instr['op'] in ['br', 'jmp']:
                    # iter labels
                    for label in instr['labels']:
                        # add to label2pred
                        if label not in label2pred:
                            label2pred[label] = []
                        label2pred[label].append(block_idx)
                        # check and link succ
                        if label in label2succ:
                            for succ_idx in label2succ[label]:
                                cur_block_cfg['succ'].append(succ_idx)
                                # check if the succ is itself
                                if succ_idx == block_idx:
                                    cur_block_cfg['pred'].append(block_idx)
                                else:  
                                    blocks_cfg[succ_idx]['pred'].append(block_idx)
                # add to blocks
                cur_block.append(instr)
                blocks.append(cur_block)
                blocks_cfg.append(cur_block_cfg)
                cur_block_cfg = {'pred': [], 'succ': [], 'touch': 0, 'in': [], 'out': []}
                cur_block = []
                block_idx += 1
            else:
                cur_block.append(instr)
        else:
            # label
            # add it if it is the first, or end before it
            if len(cur_block) > 0:
                # next block is the succ
                cur_block_cfg['succ'].append(block_idx+1)
                blocks_cfg.append(cur_block_cfg)
                blocks.append(cur_block)

                cur_block_cfg = {'pred': [block_idx], 'succ': [], 'touch': 0, 'in': [], 'out': []}
                cur_block = [instr]
                block_idx += 1
            else:
                cur_block.append(instr)

            cur_label = instr['label']
            cur_block_cfg['label'] = cur_label
            # add to label2succ
            if cur_label not in label2succ:
                label2succ[cur_label] = []
            label2succ[cur_label].append(block_idx)
            # check and link pred
            if cur_label in label2pred:
                for pred_idx in label2pred[cur_label]:
                    cur_block_cfg['pred'].append(pred_idx)
                    blocks_cfg[pred_idx]['succ'].append(block_idx)

    # if cur_lock has something, add it
    if len(cur_block) > 0:
        blocks.append(cur_block)
        blocks_cfg.append(cur_block_cfg)
    
    return blocks, blocks_cfg

if __name__ == "__main__":
    import briltxt
    prog = json.load(sys.stdin)
    for fidx, fn in enumerate(prog["functions"]):
        print(f"-----Function {fn['name']}-----")
        blocks, blocks_cfg = block_gen(fn)
        for bidx, block in enumerate(blocks):
            print(f"-----Block {bidx}-----")
            print(blocks_cfg[bidx])
            for instr in block:
                if 'op' in instr:
                    print(briltxt.instr_to_string(instr))
                else:
                    print(f".{instr['label']}:")
