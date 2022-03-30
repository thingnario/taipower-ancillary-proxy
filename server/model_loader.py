import json
import iec61850
from functools import reduce


DEFAULT_VALUES = {
    'options': [],
    'controlOptions': [],
    'wpOptions': [],
    'maxPts': 0,
    'hasOldStatus': False,
    'hasTransientIndicator': False,
    'hasCmTm': False,
    'hasCmCt': False,
    'hasHisRs': False,
    'hasChaManRs': False,
    'isIntegerNotFloat': False,
}

EXTRA_OPTIONS = {
    'ALM': ['controlOptions', 'wpOptions', 'hasOldStatus'],
    'APC': ['controlOptions', 'isIntegerNotFloat'],
    'ASG': ['isIntegerNotFloat'],
    'BAC': ['controlOptions', 'isIntegerNotFloat'],
    'BSC': ['controlOptions', 'hasTransientIndicator'],
    'CMD': ['controlOptions', 'wpOptions', 'hasOldStatus', 'hasCmTm', 'hasCmCt'],
    'CTE': ['controlOptions', 'wpOptions', 'hasHisRs'],
    'DPC': ['controlOptions'],
    'ENC': ['controlOptions'],
    'HST': ['maxPts'],
    'INC': ['controlOptions'],
    'ISC': ['controlOptions', 'hasTransientIndicator'],
    'MV': ['isIntegerNotFloat'],
    'CMV': ['isIntegerNotFloat'],
    'WYE': ['isIntegerNotFloat'],
    'DEL': ['isIntegerNotFloat'],
    'SAV': ['isIntegerNotFloat'],
    'SPC': ['controlOptions'],
    'SPV': ['controlOptions', 'wpOptions', 'hasChaManRs'],
    'STV': ['controlOptions', 'wpOptions', 'hasOldStatus'],
    'TMS': ['controlOptions', 'wpOptions', 'hasHisRs']
}

OPTION_MAP = {
    'options': {
        'INST_MAG': iec61850.CDC_OPTION_INST_MAG,
    },
    'controlOptions': {
        'MODEL_DIRECT_NORMAL': iec61850.CDC_CTL_MODEL_DIRECT_NORMAL,
    }
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

CONTROLLABLE_CDC = ['SPC', 'DPC', 'INC', 'ENC', 'BSC', 'ISC', 'APC', 'BAC']

UPDATERS = {
    'int32': iec61850.IedServer_updateInt32AttributeValue,
    'int64': iec61850.IedServer_updateInt64AttributeValue,
    'float': iec61850.IedServer_updateFloatAttributeValue,
    'boolean': iec61850.IedServer_updateBooleanAttributeValue,
    'uint32': iec61850.IedServer_updateUnsignedAttributeValue,
}


def load_extra_do_args(config, args):
    def process_arg(arg):
        name = arg['name']
        _value = config.get(name, arg['default'])
        if name in ['options', 'controlOptions']:
            return reduce(lambda value, option: value | OPTION_MAP[name][option], _value, 0)
        else:
            return _value
    return list(map(lambda arg: process_arg(arg), args))


def load_data_object(ln, config):
    creator = CDC_CREATORS[config['cdc']]
    extra_args = load_extra_do_args(config, creator['extra_args'])
    do = {
        'inst': creator['fn'](
            config['name'],
            iec61850.toModelNode(ln['inst']),
            *extra_args),
        'controllable': (config['cdc'] in CONTROLLABLE_CDC),
        'data_attributes': {},
    }
    for da_config in config.get('data_attributes', []):
        child = iec61850.ModelNode_getChild(
            iec61850.toModelNode(do['inst']), da_config['name'])
        da_inst = iec61850.toDataAttribute(child)
        do['data_attributes'][da_config['name']] = {
            'inst': da_inst,
            'data_type': da_config['data_type'],
        }
    ln['data_objects'][config['name']] = do


def load_data_set(ln, config):
    data_set = iec61850.DataSet_create(config['name'], ln['inst'])
    for entry in config.get('entries', []):
        iec61850.DataSetEntry_create(data_set, entry['variable'], -1, None)


def load_logical_node(ld, config):
    ln = {
        'inst': iec61850.LogicalNode_create(config['name'], ld['inst']),
        'data_objects': {},
    }
    for do_config in config.get('data_objects', []):
        load_data_object(ln, do_config)
    for ds_config in config.get('data_sets', []):
        load_data_set(ln, ds_config)
    ld['logical_nodes'][config['name']] = ln


def load_logical_device(model, config):
    ld = {
        'inst': iec61850.LogicalDevice_create(config['name'], model['inst']),
        'logical_nodes': {}
    }
    for ln_config in config.get('logical_nodes', []):
        load_logical_node(ld, ln_config)
    model['logical_devices'][config['name']] = ld


def load_model(model_config):
    model = {
        'inst': iec61850.IedModel_create(model_config['name']),
        'logical_devices': {},
    }
    for ld_config in model_config.get('logical_devices', []):
        load_logical_device(model, ld_config)

    return model
