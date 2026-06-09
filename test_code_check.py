code = open('frontend/app.py', encoding='utf-8').read()
checks = {
  'rag_init': 'rag = get_rag_engine()',
  'voice_q_param': 'voice_q = st.query_params.get',
  'last_voice_q': 'last_voice_q',
  'components_html': 'components.html',
  'injectVT': 'injectVT',
  'parent_location_redirect': 'window.parent.location.href',
  'no_query_params_clear': 'st.query_params.clear()' not in code,
}
for label, v in checks.items():
    if isinstance(v, bool):
        print(label + ': ' + ('PASS' if v else 'FAIL'))
    else:
        print(label + ': ' + ('PASS' if v in code else 'FAIL'))
