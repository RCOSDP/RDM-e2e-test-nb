import json
import ssl
import sys
from urllib.request import Request, urlopen

client, mode, mapping = sys.argv[1:]
request = Request('https://127.0.0.1/test/sword-clients/' + client,
                  data=json.dumps({'mode': mode, 'mapping': int(mapping)}).encode(),
                  headers={'Content-Type': 'application/json'})
with urlopen(request, context=ssl.create_default_context(cafile='/certs/server.crt')) as response:
    print('Registered SWORD client:', response.status)
