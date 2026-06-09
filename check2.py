import urllib.request, json

d = json.load(open('data/vector_store/metadata.json', encoding='utf-8'))
missing = []
ok = []
for p in d:
    for img in p.get('images', []):
        url = 'http://localhost:8000/images/' + img
        try:
            r = urllib.request.urlopen(url)
            ok.append(img)
        except Exception as e:
            missing.append((p['plant_name'], img, str(e)))

print('OK:', len(ok))
print('MISSING:', len(missing))
for m in missing:
    print(' -', m)
