import urllib.request, json
req = urllib.request.Request('http://localhost:8000/search', data=b'{\"query\":\"cough\"}', headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req)
d = json.loads(res.read())
for p in d['plants']:
    for img_url in p.get('images', []):
        try:
            urllib.request.urlopen(img_url)
            print('OK', img_url)
        except Exception as e:
            print('FAIL', img_url, e)

