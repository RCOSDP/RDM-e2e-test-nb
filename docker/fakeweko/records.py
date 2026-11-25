"""Map the received RO-Crate into the record fields consumed by RDM."""
import json
from pathlib import Path


def datasets(crate):
    graph = {entry['@id']: entry for entry in crate['@graph']}

    def expand(value, parents):
        if isinstance(value, list):
            return [expand(item, parents) for item in value]
        if not isinstance(value, dict):
            return value
        key = value.get('@id')
        if value.keys() == {'@id'} and key in graph and key not in parents:
            return expand(graph[key], parents | {key})
        return {name: expand(child, parents) for name, child in value.items()}

    root = expand(graph['ro-crate-metadata.json']['about'], set())
    return root['hasPart'] if root.get('wk:isSplited') else [root]


def values_at(data, path):
    values = [data]
    for key in path:
        children = []
        for value in values:
            if isinstance(value, dict) and key in value:
                child = value[key]
                children.extend(child if isinstance(child, list) else [child])
        values = children
    return values


def mapped(field, source, prefix=''):
    path = field['path']
    if path is None:
        path = prefix
    if path.startswith('$'):
        return path[1:]
    relative = path.removeprefix(prefix + '.') if prefix else path
    values = [source] if path == prefix else values_at(source, relative.split('.'))
    result = []
    for value in values:
        if field['children']:
            entry = {}
            for child in field['children']:
                item = mapped(child, value, path)
                if item is not None:
                    entry[child['key']] = item
            if entry:
                result.append(entry)
        else:
            if field['key'] == 'resourceuri' and isinstance(value, str) and value.startswith('http://purl.org/coar/resource_type/'):
                value = value.rstrip('/')
            result.append(value)
    if result:
        return result if field['many'] else result[0]


def metadata(dataset, mapping_id):
    fields = json.loads(Path(__file__).with_name(f'item-{mapping_id}.json').read_text())
    output = {}
    for field in fields:
        value = mapped(field, dataset)
        if value is not None:
            record_field = {'attribute_name': field['title']}
            if field['key'] == 'pubdate':
                record_field['attribute_value'] = value
            else:
                record_field['attribute_value_mlt'] = value if isinstance(value, list) else [value]
            if field['path'] == 'hasPart':
                record_field['attribute_type'] = 'file'
            if field['title'] == 'Creator':
                record_field['attribute_type'] = 'creator'
            output[field['key']] = record_field
    return output
