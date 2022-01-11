import json
import iec61850


DEFAULT_VALUES = {
    'options': 0,
    'control_options': 0,
    'wp_options': 0,
    'max_pts': 0,
    'has_old_status': False,
    'has_transient_indicator': False,
    'has_cm_tm': False,
    'has_cm_ct': False,
    'has_his_rs': False,
    'has_cha_man_rs': False,
    'is_integer_not_float': False,
}
EXTRA_OPTIONS = {
    'ALM': ['control_options', 'wp_options', 'has_old_status'],
    'APC': ['control_options', 'is_integer_not_float'],
    'ASG': ['is_integer_not_float'],
    'BAC': ['control_options', 'is_integer_not_float'],
    'BSC': ['control_options', 'has_transient_indicator'],
    'CMD': ['control_options', 'wp_options', 'has_old_status', 'has_cm_tm', 'has_cm_ct'],
    'CTE': ['control_options', 'wp_options', 'has_his_rs'],
    'DPC': ['control_options'],
    'ENC': ['control_options'],
    'HST': ['max_pts'],
    'INC': ['control_options'],
    'ISC': ['control_options', 'has_transient_indicator'],
    'MV': ['is_integer_not_float'],
    'SAV': ['is_integer_not_float'],
    'SPC': ['control_options'],
    'SPV': ['control_options', 'wp_options', 'has_cha_man_rs'],
    'STV': ['control_options', 'wp_options', 'has_old_status'],
    'TMS': ['control_options', 'wp_options', 'has_his_rs']
}
CDC_CREATORS = dict(map(
    lambda cdc: (cdc, {
        'fn': getattr(iec61850, 'CDC_{}_create'.format(cdc)),
        'extra_args': [
            {'name': arg, 'default': DEFAULT_VALUES[arg]}
            for arg in (['options'] + EXTRA_OPTIONS.get(cdc, []))
        ]
    }),
    ['ACD', 'ACT', 'ALM', 'APC', 'ASG', 'BAC', 'BCR', 'BSC', 'CMD', 'CMV',
     'CTE', 'DEL', 'DPC', 'DPL', 'DPS', 'ENC', 'ENG', 'ENS', 'HST', 'INC',
     'ING', 'INS', 'ISC', 'LPL', 'MV', 'SAV', 'SEC', 'SPC', 'SPG', 'SPS',
     'SPV', 'STV', 'TMS', 'VSG', 'VSS', 'WYE']
))


def load_extra_do_args(config, args):
    return list(map(lambda arg: config.get(arg['name'], arg['default']), args))


def load_data_object(ln, config):
    creator = CDC_CREATORS[config['cdc']]
    do = {
        'inst': creator['fn'](
            config['name'],
            iec61850.toModelNode(ln['inst']),
            *load_extra_do_args(config, creator['extra_args']))
    }
    for da_config in config.get('data_attributes', []):
        do[da_config['name']] = iec61850.toDataAttribute(iec61850.ModelNode_getChild(
            iec61850.toModelNode(do['inst']), da_config['name']))
    ln[config['name']] = do


def load_data_set(ln, config):
    data_set = iec61850.DataSet_create(config['name'], ln['inst'])
    for entry in config.get('entries', []):
        iec61850.DataSetEntry_create(data_set, entry['variable'], -1, None)


def load_logical_node(ld, config):
    ln = {'inst': iec61850.LogicalNode_create(config['name'], ld['inst'])}
    for do_config in config.get('data_objects', []):
        load_data_object(ln, do_config)
    for ds_config in config.get('data_sets', []):
        load_data_set(ln, ds_config)
    ld[config['name']] = ln


def load_logical_device(model, config):
    ld = {'inst': iec61850.LogicalDevice_create(config['name'], model['inst'])}
    for ln_config in config.get('logical_nodes', []):
        load_logical_node(ld, ln_config)
    model[config['name']] = ld


def load_model(config_path):
    with open(config_path) as f:
        model_config = json.load(f)

    model = {'inst': iec61850.IedModel_create(model_config['name'])}
    for ld_config in model_config.get('logical_devices', []):
        load_logical_device(model, ld_config)

    return model
