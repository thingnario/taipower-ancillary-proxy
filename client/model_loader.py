import json
import iec61850


ATTR_2_FC = {
    'AnalogueValue': {
        'i': {'type': 'int32'},
        'f': {'type': 'float'}
    },
    'Vector': {
        'mag': {'type': 'AnalogueValue'},
    },
    'MV': {
        'mag': {'fc': iec61850.IEC61850_FC_MX, 'type': 'AnalogueValue'},
    },
    'CMV': {
        'cVal': {'fc': iec61850.IEC61850_FC_MX, 'type': 'Vector'},
    },
    'SAV': {
        'instMag': {'fc': iec61850.IEC61850_FC_MX, 'type': 'AnalogueValue'},
        't': {'fc': iec61850.IEC61850_FC_MX, 'type': 'timestamp'},
    },
    'WYE': {
        'phsA': {'type': 'CMV'},
        'phsB': {'type': 'CMV'},
        'phsC': {'type': 'CMV'},
    },
    'SPS': {
        'stVal': {'fc': iec61850.IEC61850_FC_ST, 'type': 'boolean'},
    },
    'SPC': {
        'stVal': {'fc': iec61850.IEC61850_FC_ST, 'type': 'boolean'},
    },
    'INS': {
        'stVal': {'fc': iec61850.IEC61850_FC_ST, 'type': 'int32'},
    },
    'INC': {
        'stVal': {'fc': iec61850.IEC61850_FC_ST, 'type': 'int32'},
    },
    'BCR': {
        'actVal': {'fc': iec61850.IEC61850_FC_ST, 'type': 'int64'},
    },
}

MMS_LOADERS = {
    'int32': iec61850.MmsValue_toInt32,
    'int64': iec61850.MmsValue_toInt64,
    'float': iec61850.MmsValue_toFloat,
    'timestamp': iec61850.MmsValue_toUnixTimestamp,
}


def get_mms_loader(data_type):
    return MMS_LOADERS.get(data_type)


def get_point_type(cdc, path):
    parts = path.split('.')
    key = cdc
    type_info = ATTR_2_FC[key]
    last = len(parts) - 1
    fc = None
    for index, part in enumerate(parts):
        if part not in type_info:
            print('Error: cannot find {} in {}'.format(part, key))
            break

        attr_info = type_info[part]
        fc = attr_info.get('fc', fc)
        key = attr_info['type']
        if key in ATTR_2_FC:
            type_info = ATTR_2_FC[key]
        elif index == last:
            data_type = key
        else:
            print('Undefined data type {}'.format(key))
            break
    return fc, data_type


def load_data_object(model, parent_path, config):
    path = parent_path + '.' + config['name']
    cdc = config['cdc']
    for da_config in config.get('data_attributes', []):
        name = da_config['name']
        fc, data_type = get_point_type(cdc, name)
        model['points'].append({
            'path': path + '.' + name, 'fc': fc, 'type': data_type,
        })


def load_logical_node(model, parent_path, config):
    path = parent_path + '/' + config['name']
    for do_config in config.get('data_objects', []):
        load_data_object(model, path, do_config)
    for ds_config in config.get('data_sets', []):
        data_set_path = path + '.' + ds_config['name']
        model['data_sets'].append(data_set_path)


def load_logical_device(model, parent_path, config):
    path = parent_path + config['name']
    for ln_config in config.get('logical_nodes', []):
        load_logical_node(model, path, ln_config)


def load_model(config_path):
    with open(config_path) as f:
        model_config = json.load(f)

    model = {'points': [], 'data_sets': []}
    path = model_config['name']
    for ld_config in model_config.get('logical_devices', []):
        load_logical_device(model, path, ld_config)

    return model
