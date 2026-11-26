"""FakeWEKO serves the RDM JAIRO Cloud integration notebooks over HTTPS."""
import os
import secrets
from functools import wraps
from urllib.parse import urlencode

from flask import Flask, abort, jsonify, redirect, render_template_string, request, session, url_for

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile
import json
import mimetypes
from itertools import count

from flask import send_file
from records import datasets, metadata

app = Flask(__name__)
app.json.ensure_ascii = False
app.jinja_env.policies['json.dumps_kwargs'] = {'ensure_ascii': False}
app.secret_key = secrets.token_bytes(32)
app.config.update(SESSION_COOKIE_NAME='weko_test', SESSION_COOKIE_SECURE=True)
admin = os.environ['WEKO_ADMIN_EMAIL']
accounts = {admin: os.environ['WEKO_ADMIN_PASSWORD'],
            os.environ['WEKO_USER_EMAIL']: os.environ['WEKO_USER_PASSWORD']}
clients = {}
codes = {}
tokens = {}


def signed_in(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'email' not in session:
            session['next'] = request.full_path
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


def administrator(view):
    @wraps(view)
    @signed_in
    def wrapped(*args, **kwargs):
        if session['email'] != admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.get('/')
def home():
    return render_template_string("""
    <title>FakeWEKO</title><h1>FakeWEKO</h1>
    {% if session.email %}
      <a href="/account/settings/profile/"><i class="fa fa-user"></i>Profile</a>
      <div class="navbar-form"><button class="dropdown-toggle" onclick="this.nextElementSibling.hidden=false">{{session.email}}</button>
      <div hidden><a href="/account/settings/applications/">Applications</a> <a href="/logout/">Logout</a></div></div>
      <a href="/workflow/">WorkFlow</a>
    {% else %}<a class="login-button" href="/login/">Login</a>{% endif %}
    """)


@app.route('/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        if email not in accounts or not secrets.compare_digest(accounts[email], request.form['password']):
            abort(401)
        session['email'] = email
        return redirect(session.pop('next', '/'))
    return '<form method="post"><input id="email" name="email"><input id="password" type="password" name="password"><button type="submit">Log in</button></form>'


@app.get('/logout/')
def logout():
    session.clear()
    return redirect('/')


@app.get('/account/settings/applications/')
@administrator
def applications():
    return '<strong>Developer Applications</strong> <a href="/account/settings/applications/new">New application</a>'


@app.route('/account/settings/applications/new', methods=['GET', 'POST'])
@administrator
def new_application():
    if request.method == 'GET':
        return """<strong>New OAuth Application</strong><form method="post">
        <input name="name" required><textarea name="description"></textarea><input name="website">
        <textarea name="redirect_uris" required></textarea><button type="submit">Register</button></form>"""
    key = secrets.token_urlsafe(18)
    clients[key] = {'uri': request.form['redirect_uris'], 'secret': secrets.token_urlsafe(32)}
    return render_template_string('<p><strong>Client ID</strong><code>{{key}}</code></p><p><strong>Client Secret</strong><code>{{secret}}</code></p>',
                                  key=key, secret=clients[key]['secret'])


@app.route('/oauth/authorize', methods=['GET', 'POST'])
@signed_in
def authorize():
    key = request.args['client_id']
    if key not in clients or clients[key]['uri'] != request.args['redirect_uri']:
        abort(400)
    if request.method == 'GET':
        return '<form method="post"><button type="submit">Authorize application</button></form>'
    code = secrets.token_urlsafe(32)
    codes[code] = (key, session['email'])
    return redirect(clients[key]['uri'] + '?' + urlencode({'state': request.args['state'], 'code': code}))


@app.post('/oauth/token')
def token():
    auth = request.authorization
    key, password = (auth.username, auth.password) if auth else (request.form['client_id'], request.form['client_secret'])
    if key not in clients or clients[key]['secret'] != password:
        abort(401)
    code = request.form['code']
    if code not in codes or codes[code][0] != key or request.form['redirect_uri'] != clients[key]['uri']:
        abort(400)
    access = secrets.token_urlsafe(32)
    tokens[access] = codes.pop(code)
    return jsonify(access_token=access, token_type='Bearer')


def identity():
    access = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if access not in tokens:
        abort(401)
    return tokens[access]


@app.get('/api/get_profile_info/')
def profile():
    return jsonify(results={'subitem_mail_address': identity()[1]})


@app.get('/api/tree')
def tree():
    language = request.accept_languages.best_match(['en', 'ja'])
    return jsonify([{'id': '1', 'name': 'サンプルインデックス' if language == 'ja' else 'Sample Index', 'children': []},
                    {'id': '2', 'name': '別のインデックス' if language == 'ja' else 'Other Index', 'children': []}])


record_ids = count(2000001)
records = {}
activities = {}


def api_record(record):
    fields = record['metadata']
    language = request.accept_languages.best_match(['ja', 'en']) or 'ja'
    title = record['titles_by_language'].get(language, fields['item_title'])
    return {'id': record['id'], 'metadata': dict(fields, title=[title]), 'updated': fields['updated']}


@app.get('/api/index/')
def index():
    selected = [api_record(r) for r in records.values() if r['public'] and request.args['q'] in r['indices']]
    size, page = int(request.args.get('size', 1000)), int(request.args.get('page', 1))
    return jsonify(hits={'hits': selected[(page - 1)*size:page*size], 'total': len(selected)})


@app.get('/api/records/<int:key>')
def api_item(key):
    if key not in records or not records[key]['public']:
        abort(404)
    return jsonify(api_record(records[key]))


@app.post('/sword/service-document')
@app.put('/sword/deposit/<int:key>')
def deposit(key=None):
    client, _ = identity()
    registration = clients[client].get('registration')
    if registration is None:
        abort(403)
    if key is not None and (key not in records or records[key]['client'] != client):
        abort(404)
    review = registration['mode'] == 'workflow'
    pending = {}
    item_keys = {}
    with ZipFile(request.files['file'].stream) as bag:
        crate = json.loads(bag.read('data/ro-crate-metadata.json'))
        items = datasets(crate)
        if not items or (key is not None and len(items) != 1):
            abort(400)
        # WEKO registers supporting datasets before the manuscript that links to them.
        items.sort(key=lambda item: any(link['value'] == 'isSupplementedBy' for link in item.get('wk:itemLinks', [])))
        for item in items:
            identifier = key if key is not None else next(record_ids)
            item_keys[item['@id']] = identifier
            fields = metadata(item, registration['mapping'])
            title = item.get('dc:title', item.get('name', []))
            variants = title if isinstance(title, list) else [title]
            translations = {v['language']: v['value'] for v in variants if isinstance(v, dict) and 'language' in v}
            titles = [t['value'] if isinstance(t, dict) else t for t in variants]
            primary_title = item.get('name') or next(iter(titles), '')
            files = {}
            file_field = next((f for f in fields if fields[f].get('attribute_type') == 'file'), 'item_files')
            file_metadata = fields.get(file_field, {}).get('attribute_value_mlt', [])
            file_entries = []
            for pos, part in enumerate(item.get('hasPart', [])):
                path = part['@id'].removeprefix('./')
                if not path.startswith('files/'):
                    continue
                filename = path.removeprefix('files/')
                files[filename] = bag.read('data/' + path)
                entry = file_metadata[pos].copy() if pos < len(file_metadata) else {}
                content_type = entry.get('format') or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                entry.update(filename=filename, version_id=str(uuid4()), format=content_type, mimetype=content_type,
                             url={'url': url_for('file_download', key=identifier, name=filename, _external=True), 'label': filename})
                file_entries.append(entry)
            file_info = fields.setdefault(file_field, {'attribute_name': 'File', 'attribute_type': 'file'})
            file_info['attribute_value_mlt'] = file_entries
            fields.update(item_title=primary_title, title=[primary_title], updated=datetime.now(timezone.utc).isoformat())
            indices = item['wk:index']
            indices = indices if isinstance(indices, list) else [indices]
            pending[identifier] = dict(id=identifier, titles_by_language=translations, indices=[str(index) for index in indices], metadata=fields, public=not review, client=client, files=files)
    for item in items:
        record = pending[item_keys[item['@id']]]
        record['related'] = [item_keys[relation['identifier']] for relation in item.get('wk:itemLinks', [])
                             if relation['identifier'] in item_keys]
    records.update(pending)
    if review:
        activities.update(dict.fromkeys(pending, False))
    state = 'inWorkflow' if review else 'ingested'
    result_url = url_for('activity' if review else 'item_page', key=identifier, _external=True)
    links = [{'@id': result_url, 'rel': ['alternate'], 'contentType': 'text/html'}]
    return jsonify({'@context': 'https://swordapp.github.io/swordv3/swordv3.jsonld',
                    '@type': 'ServiceDocument' if review else 'Status',
                    '@id': request.url_root + 'sword/deposit/' + str(identifier),
                    'state': [{'@id': 'http://purl.org/net/sword/3.0/state/' + state}], 'links': links}), 201


@app.get('/records/<int:key>')
def item_page(key):
    record = records.get(key)
    if not record or not record['public']:
        abort(404)
    related = [records[i] for i in record['related'] if i in records and records[i]['public']]
    return render_template_string("""
      <aside id="test-notice">FakeWEKO
        <button onclick="sessionStorage.setItem('wekoNotice','accepted');this.parentElement.hidden=true">That's ok</button></aside>
      <script>document.getElementById('test-notice').hidden = !!sessionStorage.getItem('wekoNotice')</script>
      <a href="/workflow/">WorkFlow</a><h1>{{record.metadata.title|join(' / ')}}</h1><p id="public_status_form">Public</p>
      <a href="{{url_for('export_json',key=record.id)}}">JSON</a>
      {% for name in record.files %}<span class="filename"><a href="{{url_for('file_download',key=record.id,name=name)}}">{{name}}</a></span>{% endfor %}
      {% for other in related %}<a href="{{url_for('item_page',key=other.id)}}">{{other.metadata.item_title}}</a>{% endfor %}
      {% if session.email == admin %}
        <a id="btn_delete" href="#confirm-delete" onclick="document.getElementById('confirm-delete').hidden=false">Delete</a>
        <form id="confirm-delete" hidden method="post" action="{{url_for('delete_item',key=record.id)}}">
          <button id="confirm_delete_button" type="submit">Confirm deletion</button></form>
      {% endif %}
      <table class="detail-table">{% for field in record.metadata.values() if field is mapping and field.get('attribute_type') != 'file' %}
      <tr><th>{{field.attribute_name}}</th><td class="multiple-line">{{field.get('attribute_value_mlt', field.get('attribute_value'))|tojson}}</td></tr>
      {% endfor %}</table>""", record=record, related=related, admin=admin)


@app.post('/records/<int:key>/delete')
@administrator
def delete_item(key):
    if key not in records:
        abort(404)
    del records[key]
    activities.pop(key, None)
    return 'This item has been deleted'


@app.get('/records/<int:key>/export/json')
def export_json(key):
    if key not in records or not records[key]['public']:
        abort(404)
    return jsonify(id=key, metadata=records[key]['metadata'])


@app.get('/records/<int:key>/files/<path:name>')
def file_download(key, name):
    if key not in records or not records[key]['public'] or name not in records[key]['files']:
        abort(404)
    return send_file(BytesIO(records[key]['files'][name]), download_name=name, as_attachment=True)


@app.get('/workflow/')
@administrator
def workflow():
    return render_template_string("""
      <div id="myTabContent"><div class="table-responsive"><table><tr><th>Activity</th></tr>
      {% for key in keys %}<tr><td><a class="activity-link" href="{{url_for('activity',key=key)}}">{{key}}</a></td></tr>{% endfor %}
      </table></div></div>""", keys=reversed(activities))


@app.route('/workflow/activity/detail/<int:key>', methods=['GET', 'POST'])
@administrator
def activity(key):
    if key not in activities:
        abort(404)
    if request.method == 'POST':
        activities[key] = True
        records[key]['public'] = True
    if activities[key]:
        return render_template_string('<form action="{{url_for(\'item_page\',key=key)}}"><button>Access</button></form>', key=key)
    return '<form method="post"><button>Approval</button></form>'


@app.post('/test/sword-clients/<client>')
def register(client):
    if request.remote_addr not in {'127.0.0.1','::1'}:
        abort(403)
    if client not in clients:
        abort(404)
    data = request.get_json()
    if data['mode'] not in {'direct','workflow'} or data['mapping'] not in {30002,51000}:
        abort(400)
    clients[client]['registration'] = data
    return '', 204
