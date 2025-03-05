#!/usr/bin/env python3
import subprocess as sp
from pathlib import Path
import json
import shutil
import requests
import hashlib

session = requests.Session()
session.headers.update({
    'Accept': 'application/json'
})

METADATA_CACHE_FILE = Path('cf_metadata_cache.json')
METADATA_CACHE = None
def get_cf_metadata():
    global METADATA_CACHE
    if METADATA_CACHE:
        return METADATA_CACHE
    
    if not METADATA_CACHE_FILE.exists():
        METADATA_CACHE_FILE.write_text('{}')
    METADATA_CACHE = json.loads(METADATA_CACHE_FILE.read_text())
    return METADATA_CACHE

def update_cf_metadata():
    assert METADATA_CACHE
    METADATA_CACHE_FILE.write_text(json.dumps(METADATA_CACHE))

def download(proj_id, file_id) -> bytes:
    content = session.get(f'https://www.curseforge.com/api/v1/mods/{proj_id}/files/{file_id}/download').content
    return content

def ensure_dir(build_dir: Path, kind, modpack_id, file_id) -> Path:
    dir = build_dir.joinpath(kind) # 'client' or 'server'
    if not dir.exists():
        zip = build_dir.joinpath(kind+'.zip')
        zip.touch()
        zip.write_bytes(download(proj_id=modpack_id, file_id=file_id))
        dir.mkdir()
        sp.run(['unzip', zip.resolve()], cwd=dir)
    return dir

def build(modpack_id=663737, client_file_id=6198519, server_file_id=6198550):
    build_dir = Path('build')
    build_dir.mkdir(exist_ok=True)
    client_dir = ensure_dir(build_dir, 'client', modpack_id, client_file_id)
    server_dir = ensure_dir(build_dir, 'server', modpack_id, server_file_id)
    client_manifest = json.loads(client_dir.joinpath('manifest.json').read_text())
    server_manifest = json.loads(server_dir.joinpath('manifest.json').read_text())

    metadata = {
        'formatVersion': 1,
        'game': 'minecraft',
        'versionId': 1, # TODO
        'name': 'AE1',
        'dependencies': {},
        'files': []
    }

    metadata['dependencies']['minecraft'] = client_manifest['minecraft']['version']

    for obj in client_manifest['minecraft']['modLoaders']:
        name, version = obj['id'].split('-', maxsplit=1)
        metadata['dependencies'][name] = version

    all_mods = {}
    client_mods_mapping = {}
    for mod in client_manifest['files']:
        proj_id = mod['projectID']
        file_id = mod['fileID']
        mod_meta = process_file(proj_id, file_id)
        mod_meta['env'] = dict(client='required', server='unsupported')
        client_mods_mapping[mod_meta['path']] = (proj_id, file_id)
        all_mods[(proj_id, file_id)] = mod_meta
    for file in server_dir.glob('mods/*.jar'):
        if f'mods/{file.name}' in client_mods_mapping:
            ids=client_mods_mapping[f'mods/{file.name}']
            all_mods[ids]['env']['server'] = 'required'

    for mod in json.loads(Path('mods_to_add.json').read_text()):
        proj_id = mod['projectID']
        file_id = mod['fileID']
        mod_meta = process_file(proj_id, file_id)
        if 'env' in mod:
            mod_meta['env'] = mod['env']
        else:
            mod_meta['env'] = dict(client='required', server='required')
    
    metadata['files'] = list(all_mods.values())
    out = build_dir.joinpath('out')
    out.mkdir(exist_ok=True)
    out.joinpath('modrinth.index.json').write_text(json.dumps(metadata, indent=4))
    shutil.copytree(client_dir.joinpath('overrides'), out.joinpath('client-overrides'))

    def ignore_server_files(src: str, names: list[str]) -> list[str]:
        if src == str(server_dir):
            return ['mods']
        return []
    
    shutil.copytree(server_dir, out.joinpath('server-overrides'), ignore=ignore_server_files)
    sp.run(['zip', '-r', build_dir.joinpath('output.mrpack').resolve(), '.'], cwd=out)
    print('Done!')

def process_file(cf_proj_id, cf_file_id):
    key = f'{cf_proj_id}:{cf_file_id}'
    cache = get_cf_metadata()
    if key in cache:
        return cache[key]
    api_endpoint = f"https://www.curseforge.com/api/v1/mods/{cf_proj_id}/files/{cf_file_id}"
    download_url = api_endpoint + '/download'
    cf_file_meta = session.get(api_endpoint).json()['data']
    file_name = cf_file_meta['fileName']
    # to calculate hashes, we need to download the file :(
    cf_file_content = session.get(api_endpoint+'/download').content
    sha1 = hashlib.sha1(cf_file_content).hexdigest()
    sha512 = hashlib.sha512(cf_file_content).hexdigest()
    res = dict(downloads=[download_url], fileSize=len(cf_file_content), path='mods/'+file_name, hashes=dict(sha1=sha1, sha512=sha512))

    # update cache
    cache[key] = res
    update_cf_metadata()

    
    print(f'Processed {file_name}')
    return res

build()

#with tempfile.TemporaryDirectory() as tmp:
#    for file_obj in manifest['files']:
#        res = process_file(file_obj['projectID'], file_obj['fileID'])
#        metadata['files'].append(res)

#temp.joinpath('modrinth.index.json').write_text(json.dumps(metadata, indent=4))

#sp.run(['zip', '-r', '../output.mrpack', 'overrides', 'modrinth.index.json'], cwd=temp)
