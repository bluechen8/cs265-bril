import json
import sys
import copy
from block_gen import block_gen

NO_ARGS_INST = ['nop', 'ret', 'jmp', 'br', 'const']

def union_dicts(dicts):
    if len(dicts) == 0:
        return {}
    common_items = set(dicts[0].items())
    for d in dicts[1:]:
        common_items |= set(d.items())
    return dict(common_items)


def taint_analysis(prog):
    return_prog = {"functions": []}
    # dict to track different version of func
    # each version has args with distinct taints
    # func1: (func1, [(func1_v1,ret_taint), (func1_v2,ret_taint), ...])
    func_dict = {}
    for fn in prog['functions']:
        # pull out the main func
        if fn['name'] == 'main':
            return_prog['functions'].append(copy.deepcopy(fn))
        else:
            # add other func to func dict
            func_dict[fn['name']] = (fn, [])
    # start parse main
    main_func = return_prog['functions'][0]
    # args to main are always private
    if 'args' in main_func:
        for arg in main_func['args']:
            # check if type is dict
            if isinstance(arg['type'], dict):
                # check if it has a taint
                if 'taint' not in arg['type']:
                    arg['type']['taint'] = 'private'
            else:
                arg['type'] = {'prim': arg['type'],'taint': 'private'}
    # start taint analysis
    taint_func(main_func, func_dict, return_prog)
    return return_prog


def taint_func(fn, func_dict, return_prog):
    if DEBUG:
        print(f"-----Function {fn['name']}-----")
    ret_taint = 'public'  # return taint
    blocks, blocks_cfg = block_gen(fn, dummy=False)
    # initialize
    for block in blocks_cfg:
        for _ in range(len(block['pred'])):
            block['in'].append(dict())
        block['out'].append(dict())
    # add first block and start iterate to a fixed point
    worklist = [0]
    while len(worklist) > 0:
        block_id = worklist.pop(0)
        if DEBUG:
            print(f"-----Block {block_id}({blocks_cfg[block_id].get('label')})-----")
        # fill first block with taints from args
        taint_dict = {}
        if block_id == 0 and 'args' in fn:
            assert blocks[block_id][0]['label'] == 'dummy_entry'
            for arg in fn['args']:
                taint_dict[arg['name']] = arg['type']['taint']
            if DEBUG:
                print(f"Initial: {taint_dict}")
        else:
            # for other blocks, get taints by union pred taints
            taint_dict = union_dicts(blocks_cfg[block_id]['in'])
            if DEBUG:
                print(f"IN: {taint_dict}")
            # iterate instructions
            for instr_idx in range(len(blocks[block_id])):
                instr = blocks[block_id][instr_idx]
                if DEBUG:
                    print(f"-----Instruction {instr}-----")
                # pass label
                if 'op' in instr:
                    # check if the taint of dest is already specify
                    if isinstance(instr.get('type'), dict) and 'taint' in instr['type']:
                        taint_dict[instr['dest']] = instr['type']['taint']
                    else:
                        # check if the op is call
                        if instr['op'] == 'call':
                            # apply taint analysis to this func
                            # check input args' taints
                            input_args_taint = []
                            for arg in instr['args']:
                                if arg in taint_dict:
                                    input_args_taint.append(taint_dict[arg])
                                else:
                                    # if arg is not in taint dict,
                                    # we assume it is private
                                    input_args_taint.append('private')
                            # get the func version
                            func_match_flag = False
                            for func_v, dest_taint in func_dict[instr['funcs'][0]][1]:
                                # check if the input args taints match
                                if input_args_taint == [arg['type']['taint'] for arg in func_v['args']]:
                                    func_match_flag = True
                                    if 'dest' in instr:
                                        taint_dict[instr['dest']] = dest_taint
                                    break
                            if not func_match_flag:
                                new_func_id = len(func_dict[instr['funcs'][0]][1])
                                # evaluate the func with new input args taints
                                func_v = copy.deepcopy(func_dict[instr['funcs'][0]][0])
                                func_v['name'] = f"{instr['funcs'][0]}_{new_func_id}"
                                for arg_id in range(len(func_v['args'])):
                                    arg = func_v['args'][arg_id]
                                    # check if type is dict
                                    if isinstance(arg['type'], dict):
                                        arg['type']['taint'] = input_args_taint[arg_id]
                                    else:
                                        arg['type'] = {'prim': arg['type'],'taint': input_args_taint[arg_id]}
                                dest_taint = taint_func(func_v, func_dict, return_prog)
                                func_dict[instr['funcs'][0]][1].append((func_v, dest_taint))
                                if DEBUG:
                                    print(f"-----Back Function {fn['name']}-----")

                        # check args taint
                        private_flag = False
                        if 'args' in instr:
                            for arg in instr['args']:
                                if arg in taint_dict:
                                    if taint_dict[arg] == 'private':
                                        private_flag = True
                                        break
                                else:
                                    # if arg is not in taint dict,
                                    # we assume it is private
                                    private_flag = True
                                    break
                        else:
                            # if no args, it should be const or nop
                            # for const, we assume it is public
                            assert instr['op'] in NO_ARGS_INST
                        
                        # check dest
                        if 'dest' in instr:
                            if private_flag:
                                taint_dict[instr['dest']] = 'private'
                            else:
                                taint_dict[instr['dest']] = 'public'
        # if taint_dict changed, then update successor in and add to worklist
        if DEBUG:
            print(f"OUT: {taint_dict}")
        out_update_flag = taint_dict != blocks_cfg[block_id]['out'][0]
        if out_update_flag or blocks_cfg[block_id]['touch'] == 0:
            blocks_cfg[block_id]['touch'] += 1
            blocks_cfg[block_id]['out'][0] = copy.deepcopy(taint_dict)
            for succ_id in blocks_cfg[block_id]['succ']:
                blocks_cfg[succ_id]['in'][blocks_cfg[succ_id]['pred'].index(block_id)] = copy.deepcopy(taint_dict)
                if succ_id not in worklist:
                    worklist.append(succ_id)

    # reach fixed point, start updating dest taints
    for block_id in range(len(blocks_cfg)):
        block = blocks[block_id]
        for instr in block:
            if 'op' in instr:
                if instr['op'] == 'ret':
                    if blocks_cfg[block_id]['out'][0][instr['args'][0]] == 'private':
                        ret_taint = 'private'
                    continue
                if instr['op'] == 'call':
                    # check input args' taints
                    input_args_taint = []
                    for arg in instr['args']:
                        if arg in taint_dict:
                            input_args_taint.append(taint_dict[arg])
                        else:
                            # if arg is not in taint dict,
                            # we assume it is private
                            input_args_taint.append('private')
                    # get the func version
                    func_match_flag = False
                    for func_id, (func_v, dest_taint) in enumerate(func_dict[instr['funcs'][0]][1]):
                        # check if the input args taints match
                        if input_args_taint == [arg['type']['taint'] for arg in func_v['args']]:
                            func_match_flag = True
                            instr['funcs'][0] = f"{instr['funcs'][0]}_{func_id}"
                            return_prog['functions'].append(copy.deepcopy(func_v))
                            if 'dest' in instr:
                                if isinstance(instr.get('type'), dict):
                                    instr['type']['taint'] = dest_taint
                                else:
                                    instr['type'] = {'prim': instr['type'], 'taint': dest_taint}
                            break
                    assert func_match_flag  # should have matched
                    continue

                if 'dest' in instr:
                    if isinstance(instr.get('type'), dict):
                        instr['type']['taint'] = blocks_cfg[block_id]['out'][0][instr['dest']]
                    else:
                        instr['type'] = {'prim': instr['type'], 'taint': blocks_cfg[block_id]['out'][0][instr['dest']]}

    return ret_taint


if __name__ == '__main__':
    DEBUG = False
    prog = json.load(sys.stdin)

    prog = taint_analysis(prog)

    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)
        