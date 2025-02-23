#!/usr/bin/env python3
import subprocess as sp
from pathlib import Path
import json
import tempfile
import requests
import hashlib

temp = Path('temp')

if not Path('original_modpack.zip').exists():
    sp.run(['wget', 'https://www.curseforge.com/api/v1/mods/663737/files/6198519/download', '-O', 'original_modpack.zip'])

if not temp.exists():
    temp.mkdir(exist_ok=True)
    sp.run(['unzip', Path('original_modpack.zip').resolve()], cwd=str(temp))

metadata = {
    'formatVersion': 1,
    'game': 'minecraft',
    'versionId': 1, # TODO
    'name': 'AE1',
    'dependencies': {},
    'files': []
}

# Convert manifest.json to modrinth format
manifest = json.loads((temp/'manifest.json').read_text())

metadata['dependencies']['minecraft'] = manifest['minecraft']['version']

for obj in manifest['minecraft']['modLoaders']:
    name, version = obj['id'].split('-', maxsplit=1)
    metadata['dependencies'][name] = version

session = requests.Session()
session.headers.update({
    'Accept': 'application/json'
})

with tempfile.TemporaryDirectory() as tmp:
    for file_obj in manifest['files']:
        cf_proj_id = file_obj['projectID']
        cf_file_id = file_obj['fileID']
        api_endpoint = f"https://www.curseforge.com/api/v1/mods/{cf_proj_id}/files/{cf_file_id}"
        download_url = api_endpoint + '/download'
        cf_file_meta = session.get(api_endpoint).json()['data']
        file_name = cf_file_meta['fileName']
        file_length = cf_file_meta['fileLength']
        # to calculate hashes, we need to download the file :(
        cf_file_content = session.get(api_endpoint+'/download').content
        sha1 = hashlib.sha1(cf_file_content).hexdigest()
        sha512 = hashlib.sha512(cf_file_content).hexdigest()
        metadata['files'].append(dict(downloads=[download_url], fileSize=len(cf_file_content), path='mods/'+file_name, hashes=dict(sha1=sha1, sha512=sha512)))
        print(f'Processed {file_name}')

temp.joinpath('modrinth.index.json').write_text(json.dumps(metadata, indent=4))