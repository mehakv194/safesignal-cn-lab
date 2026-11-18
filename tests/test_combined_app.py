import re
import time

from werkzeug.test import Client
from werkzeug.wrappers import Response

from safesignal.hosted import hosted_runtime


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"',response.get_data(as_text=True)).group(1)


def test_one_origin_dashboards_and_persistence(tmp_path):
    config=dict(sender_token='s'*32,responder_token='r'*32,session_secret='k'*32,
                allowed_hosts=('campus.example',))
    with hosted_runtime(config,tmp_path,True) as app:
        client=Client(app,Response)
        assert client.get('/',base_url='https://campus.example').status_code==200
        assert client.get('/healthz',base_url='https://campus.example').json['ready'] is True
        assert client.get('/sender/login',base_url='https://evil.example').status_code==400
        assert client.get('/sender/login',base_url='http://campus.example').status_code==400
        page=client.get('/sender/login',base_url='https://campus.example')
        assert 'Secure' in page.headers['Set-Cookie'] and 'Path=/sender' in page.headers['Set-Cookie']
        login=client.post('/sender/login',base_url='https://campus.example',data={'csrf':csrf(page),'token':'s'*32})
        assert login.location=='/sender/'
        home=client.get('/sender/',base_url='https://campus.example')
        assert '/sender/submit' in home.get_data(as_text=True)
        assert '/responder/' in home.get_data(as_text=True)
        assert client.post('/sender/examples',base_url='https://campus.example',data={}).status_code==400
        assert client.post('/sender/examples',base_url='https://campus.example',data={'csrf':csrf(home)}).status_code==302
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            page=client.get('/sender/',base_url='https://campus.example')
            if 'Queued ·' not in page.get_data(as_text=True) and 'TEST ONLY: first-aid' in page.get_data(as_text=True):
                break
            time.sleep(.1)
        assert 'TEST ONLY: first-aid' in page.get_data(as_text=True)
        responder_login=client.get('/responder/login',base_url='https://campus.example')
        assert client.post('/responder/login',base_url='https://campus.example',data={'csrf':csrf(responder_login),'token':'r'*32}).status_code==302
        assert client.get('/responder/',base_url='https://campus.example').status_code==200
        assert client.get('/sender/?view=network',base_url='https://campus.example').status_code==200
        assert client.get('/sender/evidence',base_url='https://campus.example').status_code==200
    # A full runtime restart keeps both persistent SQLite databases.
    with hosted_runtime(config,tmp_path) as app:
        client=Client(app,Response)
        page=client.get('/sender/login',base_url='https://campus.example')
        client.post('/sender/login',base_url='https://campus.example',data={'csrf':csrf(page),'token':'s'*32})
        page=client.get('/sender/',base_url='https://campus.example')
        assert 'TEST ONLY: first-aid' in page.get_data(as_text=True)
