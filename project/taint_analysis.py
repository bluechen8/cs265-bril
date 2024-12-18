import json
import sys
import copy
from block_gen import block_gen

NO_ARGS_INST = ['nop', 'ret', 'jmp', 'br', 'const']
BAD_CONST_OPS = ['call']
func_call_stack = []

def values_equality_check(values):
    if len(values) <= 1:
        return True
    else:
        for i in range(1, len(values)):
            if values[i] != values[0]:
                return False
        return True

def union_dicts(dicts):
    if len(dicts) == 0:
        return {}
    common_items = set(dicts[0].items())
    for d in dicts[1:]:
        common_items |= set(d.items())
    return dict(common_items)

# return func_id, func_v, dest_taint
def check_func_args_taint(func_dict, func_name, args_taint):
    if DEBUG:
        print(f"----- Checking Function {func_name} input taints-----")
    if len(args_taint) == 0:
        if len(func_dict[func_name][1]) == 1:
            assert 'args' not in func_dict[func_name][1][0][0]
            return 0, func_dict[func_name][1][0][0], func_dict[func_name][1][0][1]
        return None, None, None
    else:
        for func_id, (func_v, dest_taint) in enumerate(func_dict[func_name][1]):
            # check if the input args taints match
            if DEBUG:
                print(f"Checking {args_taint} <-> {[arg['type']['taint'] for arg in func_v['args']]}")
            if args_taint == [arg['type']['taint'] for arg in func_v['args']]:
                if DEBUG:
                    print(f"Existing version matches, return dest taint: {dest_taint}")
                return func_id, func_v, dest_taint
        return None, None, None

def write_func_args_taint(func_dict, func_name, args_taint, correct_func_v, correct_taint):
    if DEBUG:
        print(f"----- Checking Function {func_name} input taints for update it-----")
    if len(args_taint) == 0:
        if len(func_dict[func_name][1]) == 1:
            assert 'args' not in func_dict[func_name][1][0][0]
            func_dict[func_name][2][0][1] = True
            return True
        return False
    else:
        for func_id, (func_v, _) in enumerate(func_dict[func_name][1]):
            # check if the input args taints match
            if DEBUG:
                print(f"Checking {args_taint} <-> {[arg['type']['taint'] for arg in func_v['args']]}")
            if args_taint == [arg['type']['taint'] for arg in func_v['args']]:
                func_dict[func_name][1][func_id][0] = correct_func_v
                func_dict[func_name][1][func_id][1] = correct_taint
                func_dict[func_name][2][func_id][1] = True
                return True
        return False
    
# trivial constant analysis for one block
def t_cpf_single(block, dest2val):
    if DEBUG:
        print(f"Block start: {dest2val}")
    # iterate inst in one local block
    for instr_idx in range(len(block)):
        instr = block[instr_idx]
        dest = instr.get('dest')

        # flags
        all_const_flag = True
        const_value_flag = False

        # extract constant depending on the operator
        if 'op' in instr and instr['op'] not in BAD_CONST_OPS:
            # check if has args
            if 'args' in instr or 'value' in instr:
                if 'value' in instr:
                    assert instr['op'] == 'const'
                    values = [instr['value']]
                else:
                    values = []
                    for arg in instr['args']:
                        if arg in dest2val:
                            values.append(dest2val[arg])
                        else:
                            if arg == instr.get('dest'):
                                # since the input program is SSA, only phi func could have dest as arg
                                assert instr['op'] == 'phi'
                                continue 
                            all_const_flag = False
                            break
            else:
                # pass if no args
                continue
            # compute dest value
            value = 0
            if all_const_flag and dest is not None:
                const_value_flag = True
                match instr['op']:
                    case 'const':
                        value = values[0]
                    case 'add' | 'fadd' | 'fadd_ct':
                        value = values[0] + values[1]
                    case 'sub' | 'fsub' | 'fsub_ct':
                        value = values[0] - values[1]
                    case 'mul' | 'mul_ct' | 'fmul' | 'fmul_ct':
                        value = values[0] * values[1]
                    case 'div' | 'div_ct' | 'fdiv' | 'fdiv_ct':
                        value = values[0] // values[1]
                    case 'id':
                        value = values[0]
                    case 'and':
                        value = values[0] and values[1]
                    case 'or':
                        value = values[0] or values[1]
                    case 'not':
                        value = not values[0]
                    case 'eq' | 'feq' | 'feq_ct' | 'ceq':
                        value = values[0] == values[1]
                    case 'le' | 'fle' | 'fle_ct' | 'cle':
                        value = values[0] <= values[1]
                    case 'lt' | 'flt' | 'flt_ct' | 'clt':
                        value = values[0] < values[1]
                    case 'ge' | 'fge' | 'fge_ct' | 'cge':
                        value = values[0] >= values[1]
                    case 'gt' | 'fgt' | 'fgt_ct' | 'cgt':
                        value = values[0] > values[1]
                    case 'phi':
                        if values_equality_check(values):
                            value = values[0]
                        else:
                            const_value_flag = False
                    case _:
                        # exit(f"Unknown operator {instr['op']}")
                        pass
            else:
                if len(values) == 2 and 'args' in instr and instr['args'][0] == instr['args'][1]:
                    match instr['op']:
                        case 'eq' | 'feq' | 'feq_ct' | 'ceq':
                            value = True
                            const_value_flag = True
                        case 'le' | 'fle' | 'fle_ct' | 'cle':
                            value = True
                            const_value_flag = True
                        case 'lt' | 'flt' | 'flt_ct' | 'clt':
                            value = False
                            const_value_flag = True
                        case 'ge' | 'fge' | 'fge_ct' | 'cge':
                            value = True
                            const_value_flag = True
                        case 'gt' | 'fgt' | 'fgt_ct' | 'cgt':
                            value = False
                            const_value_flag = True
                        case _:
                            pass

            # check and dest value
            if dest is not None and const_value_flag:
                dest2val[dest] = value
    if DEBUG:
        print(f"Block end: {dest2val}")
    return dest2val

def t_cpf(fn):
    # interate blocks
    blocks, blocks_cfg = block_gen(fn)
    # initialize in and out table
    for block in blocks_cfg:
        for _ in range(len(block['pred'])):
            block['in'].append({})
        block['out'].append({})
    # initialize worklist
    worklist = [0]
    while len(worklist) > 0:
        block_id = worklist.pop()
        dest2val = t_cpf_single(blocks[block_id], union_dicts(blocks_cfg[block_id]['in']))
        blocks_cfg[block_id]['touch'] += 1
        # if out changed, update succ
        if dest2val != blocks_cfg[block_id]['out'][0]:
            for succ_id in blocks_cfg[block_id]['succ']:
                if succ_id not in worklist:
                    worklist.append(succ_id)
                blocks_cfg[succ_id]['in'][blocks_cfg[succ_id]['pred'].index(block_id)] = dest2val
            blocks_cfg[block_id]['out'][0] = dest2val
        else:
            # if succ has not been touched, add to worklist
            for succ_id in blocks_cfg[block_id]['succ']:
                if succ_id not in worklist and blocks_cfg[succ_id]['touch'] == 0:
                    worklist.append(succ_id)

    # get union of the taint_dict
    const_dict_list = []
    # interate blocks without successors
    for block_id in range(len(blocks_cfg)):
        if len(blocks_cfg[block_id]['succ']) == 0:
            const_dict_list.append(blocks_cfg[block_id]['out'][0])
    const_dict = union_dicts(const_dict_list)
    return const_dict

def taint_analysis(prog):
    return_prog = {"functions": []}
    # dict to track different version of func
    # each version has args with distinct taints
    # func1: (func1, [(func1_v1,ret_taint), (func1_v2,ret_taint), ...], [bit if func is added, bit if func is tainted])
    func_dict = {}
    for fn in prog['functions']:
        # pull out the main func
        if fn['name'] == 'main':
            return_prog['functions'].append(copy.deepcopy(fn))
        else:
            # add other func to func dict
            func_dict[fn['name']] = (fn, [], [])
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
    func_call_stack.append('main')
    taint_func(main_func, func_dict, return_prog)
    func_call_stack.pop()
    assert len(func_call_stack) == 0
    return return_prog


def taint_func(fn, func_dict, return_prog):
    if DEBUG:
        print(f"-----Function {fn['name']}-----")
    # constant analysis
    const_dict = {}
    if CONSTANT_ANALYSIS:
        if DEBUG:
            print(f"-----Constant Analysis-----")
        const_dict = t_cpf(fn)
        if DEBUG:
            print(f"-----Constant Analysis Result: {const_dict}-----")
    # start taint analysis
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
                    elif 'dest' in instr and instr['dest'] in const_dict:
                        # if dest can be determined by constant analysis, then it should be public
                        taint_dict[instr['dest']] = 'public'
                    else:
                        # TODO: consider mul, mul_ct, and, or for more constant analysis opt
                        # check if the op is call
                        if instr['op'] == 'call':
                            # apply taint analysis to this func
                            # check input args' taints
                            input_args_taint = []
                            # could be function without args
                            if 'args' in instr:
                                for arg in instr['args']:
                                    if arg in taint_dict:
                                        input_args_taint.append(taint_dict[arg])
                                    else:
                                        # if arg is not in taint dict,
                                        # we assume it is private
                                        input_args_taint.append('private')
                            # get the func version
                            _, _, dest_taint = check_func_args_taint(func_dict, instr['funcs'][0], input_args_taint)
                            if dest_taint is None:
                                if DEBUG:
                                    print(f"No existing version matches, create new version for {input_args_taint}")
                                # evaluate the func with new input args taints
                                func_v = copy.deepcopy(func_dict[instr['funcs'][0]][0])
                                if 'args' in func_v:
                                    for arg_id in range(len(func_v['args'])):
                                        arg = func_v['args'][arg_id]
                                        # check if type is dict
                                        if isinstance(arg['type'], dict):
                                            arg['type']['taint'] = input_args_taint[arg_id]
                                        else:
                                            arg['type'] = {'prim': arg['type'],'taint': input_args_taint[arg_id]}
                                # check if this func is already in call stack
                                if instr['funcs'][0] in func_call_stack:
                                    if DEBUG:
                                        print(f"-----Recursion Function {instr['funcs'][0]}-----")
                                    # if so, we assume it is private
                                    dest_taint = 'private'
                                    func_dict[instr['funcs'][0]][1].append([func_v, dest_taint])
                                    func_dict[instr['funcs'][0]][2].append([False, False])  # not taint ready
                                    dest_taint = taint_func(func_v, func_dict, return_prog)
                                    assert write_func_args_taint(func_dict, instr['funcs'][0], input_args_taint, func_v, dest_taint)
                                else:
                                    func_call_stack.append(instr['funcs'][0])
                                    dest_taint = taint_func(func_v, func_dict, return_prog)
                                    func_call_stack.pop()
                                    # check if this func is already added by its child
                                    # if yes, overwrite the return taint
                                    if not write_func_args_taint(func_dict, instr['funcs'][0], input_args_taint, func_v, dest_taint):
                                        if DEBUG:
                                            print(f"Input taint of {instr['funcs'][0]} does not match its child, add new version for {input_args_taint}")
                                        func_dict[instr['funcs'][0]][1].append([func_v, dest_taint])
                                        func_dict[instr['funcs'][0]][2].append([False, True]) # taint ready
                            if 'dest' in instr:
                                taint_dict[instr['dest']] = dest_taint
                            if DEBUG:
                                print(f"-----Back Function {fn['name']}-----")
                        elif instr['op'] == 'load':
                            # conservative approach: if load, we assume it is private
                            taint_dict[instr['dest']] = 'private'
                        else:
                            # other instructions
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
    # get union of the taint_dict
    taint_dict_list = []
    # interate blocks without successors
    for block_id in range(len(blocks_cfg)):
        if len(blocks_cfg[block_id]['succ']) == 0:
            taint_dict_list.append(blocks_cfg[block_id]['out'][0])
    taint_dict = union_dicts(taint_dict_list)
    if DEBUG:
        print(f"-----Start Updating Dest Taints-----")
    for block_id in range(len(blocks_cfg)):
        block = blocks[block_id]
        for instr in block:
            if 'op' in instr:
                if instr['op'] == 'ret':
                    # check if exist ret valuable
                    if 'args' in instr and blocks_cfg[block_id]['out'][0][instr['args'][0]] == 'private':
                        ret_taint = 'private'
                    continue
                if instr['op'] == 'call':
                    # check input args' taints
                    input_args_taint = []
                    if 'args' in instr:
                        for arg in instr['args']:
                            if arg in taint_dict:
                                input_args_taint.append(taint_dict[arg])
                            else:
                                # if arg is not in taint dict,
                                # we assume it is private
                                input_args_taint.append('private')
                    # get the func version
                    func_id, func_v, dest_taint = check_func_args_taint(func_dict, instr['funcs'][0], input_args_taint)
                    assert dest_taint is not None
                    # add matched func to return prog if it is not added yet and its taint is ready
                    add_flag = func_dict[instr['funcs'][0]][2][func_id][0]
                    taint_ready_flag = func_dict[instr['funcs'][0]][2][func_id][1]
                    if DEBUG:
                        print(f"{func_v['name']} added: {add_flag}, taint ready: {taint_ready_flag}")
                    if not add_flag and taint_ready_flag:
                        func_dict[instr['funcs'][0]][2][func_id][0] = True
                        func_v_copy = copy.deepcopy(func_v)
                        func_v_copy['name'] = f"{func_v['name']}_{func_id}"
                        return_prog['functions'].append(func_v_copy)
                        if DEBUG:
                            print(f"Add {func_v_copy['name']} to return_prog")
                    if DEBUG:
                        print(f"Replace {instr['funcs'][0]} with {instr['funcs'][0]}_{func_id}")
                    instr['funcs'][0] = f"{instr['funcs'][0]}_{func_id}"
                    if 'dest' in instr:
                        if isinstance(instr.get('type'), dict):
                            instr['type']['taint'] = dest_taint
                        else:
                            instr['type'] = {'prim': instr['type'], 'taint': dest_taint}
                    continue

                if 'dest' in instr:
                    if isinstance(instr.get('type'), dict):
                        instr['type']['taint'] = blocks_cfg[block_id]['out'][0][instr['dest']]
                    else:
                        instr['type'] = {'prim': instr['type'], 'taint': blocks_cfg[block_id]['out'][0][instr['dest']]}

    return ret_taint


if __name__ == '__main__':
    DEBUG = False
    CONSTANT_ANALYSIS = True
    MEMORY_ALIAS = False
    CODE_TRANSFORM = False

    prog = json.load(sys.stdin)

    prog = taint_analysis(prog)

    # Output the program
    if not DEBUG:
        json.dump(prog, sys.stdout, indent=2)
        