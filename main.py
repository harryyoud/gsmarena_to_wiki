from collections import OrderedDict

from bs4 import BeautifulSoup
import dateparser.search
import re
import requests
import sys
import yaml

from peripherals import PERIPHERALS

UNKNOWN = 'REQUIRED, BUT UNKNOWN'
CPU_CORES = {
    'Deca-core': 10,
    'Octa-core': 8,
    'Hexa-core': 6,
    'Quad-core': 4,
    'Dual-core': 2,
}


def parse_release_date(spec_tags: dict) -> dict:
    try:
        return {'release': dateparser.search.search_dates(spec_tags['year'][0])[0][1].date()}
    except (IndexError, KeyError):
        return {}


def parse_peripherals(spec_tags: dict) -> dict:
    out = []
    for peripheral in PERIPHERALS:
        try:
            for entry in spec_tags[peripheral.gsm_field]:
                if peripheral.gsm_name.lower() in entry.lower():
                    out.append(peripheral.wiki_spec_name)
        except KeyError:
            pass
    return {'peripherals': out}


def parse_battery(spec_tags: dict) -> dict:
    out = {}
    try:
        if 'non-removable' in spec_tags['batdescription1'][0].lower():
            out['removable'] = False
        out['capacity'] = str(spec_tags['batsize-hl'][0])
        out['tech'] = str(spec_tags['battype-hl'][0])
    except (IndexError, KeyError):
        pass
    return {'battery': out}


def parse_bluetooth_spec(spec_tags, additional_bt_specs):
    try:
        main_spec = re.findall(r'\b(\d+\.?\d*[a-zA-Z]?)\b', spec_tags['bluetooth'][0])[0]
        if main_spec == '5.0':
            main_spec = '5'
        bt_spec = [main_spec]
    except (IndexError, KeyError):
        return {}
    try:
        for add_prop in additional_bt_specs:
            if add_prop not in spec_tags['bluetooth'][0]:
                continue
            if add_prop == 'LE' and bt_spec[0] != '4.0':  # Only 4.0 has a additional LE spec
                continue
            bt_spec.append(add_prop)
    except (IndexError, KeyError):
        pass
    return {'spec': " + ".join(bt_spec)}


def parse_bluetooth_profile(spec_tags):
    bt_profs = []
    raw_bt_info = spec_tags['bluetooth'][0].split(', ')
    try:
        if 'aptX HD' in raw_bt_info:
            bt_profs.append('A2DP + aptX HD')
        elif 'aptX' in raw_bt_info:
            bt_profs.append('A2DP + aptX')
        elif 'A2DP' in raw_bt_info:
            bt_profs.append('A2DP')
    except KeyError:
        pass
    if bt_profs:
        return {'profiles': bt_profs}
    return {}


def parse_cpu_cores(spec_tags):
    try:
        for name, number in CPU_CORES.items():
            if name.lower() in spec_tags['cpu'][0].lower():
                return {'cpu_cores': str(number)}
    except (IndexError, KeyError):
        pass
    return {}


def parse_cpu_freqs(spec_tags):
    try:
        if raw_freqs := re.findall(r'(\d*)\s*x\s*(\d*\.\d*)\s* GHz', spec_tags['cpu'][0]):
            return {'cpu_freq': ' + '.join([f'{x[0]} x {x[1]} GHz' for x in raw_freqs])}
    except (IndexError, KeyError):
        pass
    return {}


def parse_cpu_model(spec_tags):
    try:
        cpu_tag = spec_tags['cpu'][0]
        if match := re.findall(r'Kryo( ?\d*)', cpu_tag):
            return {'cpu': f'Kryo{match[0]}'}
        elif match := re.findall(r'Krait( ?\d*)', cpu_tag):
            return {'cpu': f'Krait{match[0]}'}
        elif 'Atom' in cpu_tag:
            return {'cpu': 'Intel Atom'}
        elif 'Denver' in cpu_tag:
            return {'cpu': 'Denver'}
        elif 'Cortex' in spec_tags['cpu'][0]:
            match = list(map(lambda x: x.replace(' ', '-'), re.findall(r'Cortex[-\s]A\d*', cpu_tag)))
            return {'cpu': ' & '.join(*match)}
    except (IndexError, KeyError):
        pass
    return {}


def parse_gpu(spec_tags):
    try:
        if (match := re.findall(r'Adreno \d*', spec_tags['gpu'][0])) is not None:
            return {'gpu': match[0]}
        elif (match := re.findall(r'(Mali-[a-zA-Z]?\d* *[a-zA-Z]*\d*)', spec_tags['gpu'][0])) is not None:
            return {'gpu': f'ARM {match[0]}'}
    except (IndexError, KeyError):
        pass
    return {}


def parse_dimensions(spec_tags):
    dims = {}
    try:
        if raw_dims := re.findall(r'(\d*\.?\d*)\s*x\s*(\d*\.?\d*)\s*x\s*(\d*\.?\d*)', spec_tags['dimensions'][0]):
            dims['height'] = f'{raw_dims[0][0]} mm ({raw_dims[1][0]} in)'
            dims['width'] = f'{raw_dims[0][1]} mm ({raw_dims[1][1]} in)'
            dims['depth'] = f'{raw_dims[0][2]} mm ({raw_dims[1][2]} in)'
    except (IndexError, KeyError):
        pass
    return dims


def parse_model_name(spec_tags, vendor_list):
    out = {}
    try:
        for vendor in vendor_list:
            if vendor.lower() not in spec_tags['modelname'][0].lower():
                continue
            out['name'] = re.sub(vendor + r'\s?', '', spec_tags['modelname'][0], re.IGNORECASE)
            out['vendor'] = vendor
            out['vendor_short'] = vendor.lower()
            out['tree'] = f'android_device_{vendor.lower()}_CODENAME'
            out['kernel'] = f'android_kernel_{vendor.lower()}_CODENAME'
    except (IndexError, KeyError):
        pass
    return out


def parse_model_numbers(spec_tags):
    try:
        return {'models': spec_tags['models'][0].split(', ')}
    except (IndexError, KeyError):
        return {}


def parse_screen_size(spec_tags):
    try:
        screen_size = float(re.findall(r'\d*\.\d*', spec_tags['displaysize-hl'][0])[0])
        return {'screen': f"{round(screen_size * 25.4)} mm ({screen_size} in)"}
    except (IndexError, KeyError):
        return {}


def parse_mobile_networks(spec_tags):
    try:
        raw_network_rows = spec_tags['net2g'][0].find_parent('table').descendants
        raw_network_rows = [x for x in raw_network_rows if
                            x.name in ['tr', 'td'] and ('data-spec' in x.attrs or 'data-spec-optional' in x.attrs)]
        raw_network_info = OrderedDict()
        for child in raw_network_rows:
            if 'data-spec' in child.attrs and child.attrs['data-spec'] == 'speed':
                continue
            elif 'data-spec-optional' in child.attrs:
                for row in child.children:
                    if hasattr(row, 'attrs') and 'nfo' in row.attrs['class']:
                        k = next(reversed(raw_network_info.keys()))
                        raw_network_info[k].append(row.contents[0].strip())
            else:
                raw_network_info[child.attrs['data-spec']] = [child.contents[0].strip()]
    except (IndexError, KeyError):
        return {}

    networks = []
    if 'net2g' in raw_network_info:
        if any('GSM' in x for x in raw_network_info['net2g']):
            networks.append('2G GSM')
        if any('CDMA' in x for x in raw_network_info['net2g']):
            networks.append('2G CDMA')
    if 'net3g' in raw_network_info:
        if any('HSDPA' in x or 'UMTS' in x for x in raw_network_info['net3g']):
            networks.append('3G UMTS')
        if any('CDMA' in x for x in raw_network_info['net3g']):
            networks.append('3G CDMA2000')
    if 'net4g' in raw_network_info and len(raw_network_info['net4g']) > 0:
        networks.append('4G LTE')
    if 'net5g' in raw_network_info and len(raw_network_info['net5g']) > 0:
        networks.append('5G')

    return {'network': networks}


def parse_camera(spec_tags):
    cameras = []
    for cam in [*spec_tags.get('cam1modules', []), *spec_tags.get('cam2modules', [])]:
        if cam == '\n':
            continue
        if hasattr(cam, 'contents'):
            cam = cam.contents[0]
        if resolution := re.findall(r'(\d+\.?\d* MP)', cam):
            cameras.append({
                'flash': '',
                'info': resolution[0],
            })
    return {'cameras': cameras}


def parse_screen_res(spec_tags):
    out = {}
    if ppi := re.findall(r'(~?\d*) ppi density', spec_tags.get('displayresolution', [''])[0]):
        out['screen_ppi'] = ppi[0]
    if resolution := re.findall(r'(\d+)\s?x\s?(\d+)', spec_tags.get('displayresolution', [''])[0]):
        out['screen_res'] = f'{resolution[0][0]}x{resolution[0][1]}'
    return out


def parse_internalmem(spec_tags):
    ram = []
    storage = []
    try:
        if configs := re.findall(r'(\d+)\s?GB (\d+)\s?GB RAM', spec_tags['internalmemory'][0]):
            for config in configs:
                storage.append(config[0])
                ram.append(config[1])
        if ram.count(ram[0]) == len(ram):
            ram = [ram[0]]
        if storage.count(storage[0]) == len(storage):
            ram = [storage[0]]
    except (IndexError, KeyError):
        return {}
    return {
        'ram': f'{"/".join(ram)} GB',
        'storage': f'{"/".join(storage)} GB',
    }


def main():
    soup = BeautifulSoup(requests.get(f'https://www.gsmarena.com/{sys.argv[1]}.php').content, 'html.parser')

    wiki_spec = yaml.load(
        requests.get('https://raw.githubusercontent.com/LineageOS/lineage_wiki/master/test/schema-06.yml').content,
        yaml.SafeLoader)
    vendor_list = wiki_spec['properties']['vendor']['enum']
    additional_bt_specs = list(
        set([x.split(' + ')[1] for x in wiki_spec['properties']['bluetooth']['properties']['spec']['enum']
             if ' + ' in x]))

    specs = {
        **{k: UNKNOWN for k in wiki_spec['required']},
        'battery': {
            'removable': UNKNOWN,
            'capacity': UNKNOWN,
        },
        'bluetooth': {
            'spec': UNKNOWN
        },
    }

    raw_specs = {}

    for el in soup.find_all(['h1', 'td', 'span', 'div'], attrs={'data-spec': True}):
        raw_specs[el.attrs['data-spec']] = el.contents

    specs.update(parse_release_date(raw_specs))
    specs.update(parse_peripherals(raw_specs))
    specs.update(parse_battery(raw_specs))
    specs.update(parse_battery(raw_specs))
    specs['bluetooth'].update(parse_bluetooth_profile(raw_specs))
    specs.update(parse_cpu_cores(raw_specs))
    specs.update(parse_cpu_freqs(raw_specs))
    specs.update(parse_cpu_model(raw_specs))
    specs.update(parse_gpu(raw_specs))
    specs.update(parse_dimensions(raw_specs))
    specs.update(parse_model_numbers(raw_specs))
    specs.update(parse_screen_size(raw_specs))
    specs.update(parse_mobile_networks(raw_specs))
    specs.update(parse_camera(raw_specs))
    specs.update(parse_screen_res(raw_specs))

    specs.update(parse_model_name(raw_specs, vendor_list))
    specs['bluetooth'].update(parse_bluetooth_spec(raw_specs, additional_bt_specs))

    print(yaml.dump(specs))


if __name__ == '__main__':
    main()
