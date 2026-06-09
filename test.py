import urllib.request, json
req = urllib.request.Request('http://localhost:8000/search', data=b'{\"query\":\"cough\"}', headers={'Content-Type': 'application/json'})
res = urllib.request.urlopen(req)
d = json.loads(res.read())
for p in d['plants']:
    print(p['plant_name'], p.get('images', []))

