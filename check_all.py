import urllib.request, json
d = json.load(open('data/vector_store/metadata.json', encoding='utf-8'))
missing=[]
for p in d:
  for img in p.get('images', []):
    try:
      urllib.request.urlopen('http://localhost:8000/images/' + urllib.parse.quote(img))
    except Exception as e:
      missing.append((img, str(e)))
print('Total broken backend links:', len(missing))
print(missing[:10])
