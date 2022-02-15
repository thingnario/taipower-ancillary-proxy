import json
import iec61850


MMS_LOADERS = {
    'int32': iec61850.MmsValue_toInt32,
    'int64': iec61850.MmsValue_toInt64,
    'float': iec61850.MmsValue_toFloat,
    'boolean': iec61850.MmsValue_getBoolean,
}

FC_MAPPING = {
    'MX': iec61850.IEC61850_FC_MX,
    'ST': iec61850.IEC61850_FC_ST,
    'CO': iec61850.IEC61850_FC_CO,
}


def get_mms_loader(data_type):
    return MMS_LOADERS.get(data_type)


def load_data_object(model, parent_path, config):
    path = parent_path + '.' + config['name']
    for da_config in config.get('data_attributes', []):
        name = da_config['name']
        fc = FC_MAPPING[da_config['fc']]
        data_type = da_config['data_type']
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
