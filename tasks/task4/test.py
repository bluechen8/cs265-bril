import copy

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
    print(f"all_keys: {all_keys}")
    print(f"common_keys: {common_keys}")
    # print(common_items)
    # collect unique keys
    unique_keys = all_keys - common_keys
    print(f"unique_keys: {unique_keys}")
    print(f"common_items: {common_items}")
    for key in unique_keys:
        for d in dicts:
            if key in d:
                common_items.add((key, d[key]))
                break
    return dict(common_items)

in_dict_list = [{'edge_loc': 'edge_loc.2', 'node_loc': 'node_loc.1', 'csr_edges': 'csr_edges.1', 'num_nodes': 'num_nodes.1', 'num_edges': 'num_edges.3', 'csr_offset': 'csr_offset.1', 'node_idx': 'node_idx.1', 'one': 'one.1', 'offset_loc': 'offset_loc.1', 'row_cond': 'row_cond.1', 'row_tmp': 'row_tmp.1', 'node_val': 'node_val.1', 'adjmat': 'adjmat.1', 'col': 'col.1', 'col_cond': 'col_cond.1', 'cond': 'cond.1', 'row': 'row.2'}, {'node_loc': 'node_loc.1', 'row': 'row.2', 'node_idx': 'node_idx.1', 'row_cond': 'row_cond.1', 'num_edges': 'num_edges.1', 'node_val': 'node_val.1', 'row_tmp': 'row_tmp.1', 'col': 'col.3', 'col_cond': 'col_cond.1', 'cond': 'cond.1', 'edge_loc': 'edge_loc.1'}]
print(f"length of in_dict_list: {len(in_dict_list)}")
print(merge_dicts(in_dict_list, pos=True, loose=True))