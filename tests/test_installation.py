import json
import struct

from werkzeug.test import Client
from werkzeug.wrappers import Response

from safesignal.hosted import hosted_runtime


def test_public_install_assets_and_private_pages(tmp_path):
    config = dict(identity=True, hosted=True, session_secret='fixture-key',
                  sender_token='fixture-sender', responder_token='fixture-responder',
                  allowed_hosts=('campus.example',), mail=None)
    with hosted_runtime(config, tmp_path) as app:
        client = Client(app, Response)
        origin = 'https://campus.example'
        manifest_path = '/static/safesignal.webmanifest'
        for page in ('/', '/sender/login', '/responder/login'):
            response = client.get(page, base_url=origin)
            assert f'rel="manifest" href="{manifest_path}"' in response.text
            assert 'no-store' in response.headers['Cache-Control']
        response = client.get(manifest_path, base_url=origin)
        assert response.mimetype == 'application/manifest+json'
        manifest = json.loads(response.data)
        assert manifest['start_url'] == manifest['scope'] == '/'
        assert manifest['display'] == 'standalone'
        assert {icon['sizes'] for icon in manifest['icons']} == {'192x192', '512x512'}
        for icon in manifest['icons']:
            asset = client.get('/static/' + icon['src'], base_url=origin)
            assert asset.mimetype == 'image/png'
            assert asset.data.startswith(b'\x89PNG\r\n\x1a\n')
            assert struct.unpack('!II', asset.data[16:24]) == tuple(map(int, icon['sizes'].split('x')))
        assert client.get('/sender/walks', base_url=origin).status_code == 302
