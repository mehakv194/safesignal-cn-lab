import threading
import urllib.error
import urllib.request

import pytest
import waitress

from safesignal.hosted import main


def test_actual_waitress_ingress_preserves_https_and_rejects_forwarded_host(monkeypatch,tmp_path):
    for key,value in dict(SAFESIGNAL_SENDER_TOKEN='s'*32,SAFESIGNAL_RESPONDER_TOKEN='r'*32,
                          SAFESIGNAL_SESSION_SECRET='k'*32,SAFESIGNAL_DATA_DIR=str(tmp_path),
                          SAFESIGNAL_ALLOWED_HOSTS='campus.example').items():
        monkeypatch.setenv(key,value)
    monkeypatch.delenv('RENDER_EXTERNAL_HOSTNAME',raising=False)

    def serve_and_check(app,**options):
        server=waitress.create_server(app,**dict(options,host='127.0.0.1',port=0,asyncore_loop_timeout=.05))
        thread=threading.Thread(target=server.run,daemon=True)
        thread.start()
        try:
            url=f'http://127.0.0.1:{server.effective_port}/sender/login'
            request=urllib.request.Request(url,headers={'Host':'campus.example','X-Forwarded-Proto':'https','X-Forwarded-Host':'evil.example'})
            with urllib.request.urlopen(request,timeout=5) as reply:
                assert reply.status==200
                assert 'Secure' in reply.headers['Set-Cookie']
                page=reply.read()
                assert b'name="email"' in page and b'name="password"' in page and b'Access token' not in page
            for headers in ({'Host':'campus.example'},{'Host':'evil.example','X-Forwarded-Proto':'https'}):
                with pytest.raises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=5)
                assert error.value.code==400
        finally:
            server.close()
            server.task_dispatcher.shutdown()
            thread.join(timeout=2)
    monkeypatch.setattr(waitress,'serve',serve_and_check)
    main()
