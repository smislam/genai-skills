# Python: security review guide

Covers Django (including Django REST Framework), Flask, FastAPI, SQLAlchemy, and Celery workers, plus scripts and CLIs that process untrusted files. Tool commands are in `tools.md`; triage rules in `triage.md`.

## Sources

| Entry point | Concrete APIs |
|---|---|
| Django | `request.GET`, `request.POST`, `request.body`, `request.FILES`, `request.headers`, `request.COOKIES`, `request.META`, URL kwargs; DRF `request.data`, `request.query_params`, serializer input |
| Flask | `request.args`, `request.form`, `request.values`, `request.json`/`get_json()`, `request.files`, `request.headers`, `request.cookies`, view arguments |
| FastAPI | Path, query, header, cookie, body, and form parameters (`Query`, `Path`, `Header`, `Cookie`, `Body`, `Form`, `UploadFile`); Pydantic models; `Request` |
| Workers | Celery task arguments (they arrive from the broker), Kafka or SQS consumers, cron jobs reading shared storage |
| Other | `sys.argv` and `os.environ` in tools invoked by services, uploaded files parsed by pandas or openpyxl, WebSocket messages, LLM output |

## Sinks by vulnerability class

| Class (CWE) | Dangerous APIs and patterns | Safe pattern |
|---|---|---|
| SQL injection (CWE-89) | `cursor.execute(f"... {x}")`, `%` formatting or `+` in SQL; Django `raw()`, `extra()`, `RawSQL` with interpolation; SQLAlchemy `text(f"...")`, `session.execute` with formatted strings; dynamic `order_by` from input | DB-API parameters (`cursor.execute(sql, (x,))`); Django ORM lookups and `raw(sql, params)`; SQLAlchemy bound parameters (`text("... :id")` with params); allow-listed sort fields |
| NoSQL injection (CWE-943) | `pymongo` filters taken directly from `request.json` (operator injection); `$where` | Validate types with Pydantic or a serializer; build filters explicitly |
| OS command (CWE-78) | `os.system`, `os.popen`, `subprocess.*` with `shell=True` and input; `commands` in legacy code | `subprocess.run([...], shell=False)` with an argument list; `shlex.quote` only as a last resort |
| Code injection (CWE-94, CWE-95) | `eval`, `exec`, `compile` on input; `__import__(input)`; `importlib.import_module(input)` | `ast.literal_eval` for literals; fixed dispatch dictionaries |
| Template injection (CWE-1336) | `render_template_string(input)` in Flask; `jinja2.Template(input)`; Django `Template(input)` | Fixed templates with variables passed in context; `jinja2.sandbox.SandboxedEnvironment` if user templates are a feature |
| XSS (CWE-79) | Django `mark_safe`, `\|safe`, `{% autoescape off %}`, `format_html` misuse; Jinja2 `Markup(input)`, `\|safe`, `autoescape=False` in a manually built `Environment`; returning HTML strings built from input | Autoescaping (Django and Flask defaults); `format_html` with arguments; `bleach` or `nh3` when markup is required |
| Path traversal (CWE-22) | `open(os.path.join(base, input))` (an absolute `input` replaces `base`); `send_file(input)`; `FileResponse(open(...))`; `UploadedFile.name` used as a path; `zipfile.extractall` and `tarfile.extractall` on untrusted archives | `werkzeug.utils.secure_filename`; Flask `send_from_directory`; resolve with `os.path.realpath` and check the prefix; `tarfile` extraction filters (`filter="data"`, Python 3.12+) |
| SSRF (CWE-918) | `requests.get(input)`, `httpx`, `urllib.request.urlopen(input)`, `aiohttp` with a URL from input; URL preview and webhook features | A host allow-list; resolve and block private and link-local ranges; `allow_redirects=False` or re-validate after each redirect |
| Open redirect (CWE-601) | `redirect(request.args["next"])`; Django `HttpResponseRedirect(input)` | Django `url_has_allowed_host_and_scheme`; relative paths only |
| Deserialization (CWE-502) | `pickle.loads`, `pickle.load`, `cPickle`, `dill`, `shelve`, `joblib.load`, `numpy.load(..., allow_pickle=True)`, `torch.load` on untrusted files (unsafe before PyTorch 2.6, which defaults to `weights_only=True`, or with an explicit `weights_only=False`); `yaml.load` with `Loader=yaml.Loader` or `UnsafeLoader`; `jsonpickle.decode` | JSON plus schema validation; `yaml.safe_load`; `torch.load(weights_only=True)`; safetensors for model weights |
| XXE (CWE-611) | Standard-library parsers don't resolve external entities by default (`xml.sax` since 3.7.1), but are open to entity-expansion denial of service with expat before 2.4.1; `xml.sax` with `feature_external_ges` enabled; `lxml` before 5.0 with default settings, or any version with `resolve_entities=True` or `no_network=False` | `defusedxml`; `lxml` with a hardened `XMLParser(resolve_entities=False, no_network=True)` |
| LDAP and XPath injection (CWE-90, CWE-643) | `ldap3` or `python-ldap` filters built with f-strings; `lxml` `xpath()` with concatenated input | `ldap3.utils.conv.escape_filter_chars`; XPath variables (`tree.xpath("//u[@id=$id]", id=value)`) |
| Log injection (CWE-117) | Logging raw input with CR/LF | `logging` with `%s` arguments and a structured formatter |
| Crypto misuse (CWE-327, CWE-329, CWE-330, CWE-916) | `hashlib.md5` or `sha1` for passwords or signatures; `random.random`, `random.choice`, `random.randint` for tokens; PyCryptodome `AES.MODE_ECB`; a static IV or nonce; `requests(..., verify=False)`; `ssl._create_unverified_context` | `secrets` module; `cryptography` AESGCM with a random nonce; Django password hashers, `argon2-cffi`, `bcrypt`, or `hashlib.scrypt`; default certificate verification |
| ReDoS (CWE-1333) | `re.compile(user_pattern)`; catastrophic patterns on input | Don't accept user regexes; limit input length; the `regex` module's timeout, or `google-re2` |
| File upload (CWE-434) | Saving uploads under static or media roots served without checks; trusting `content_type` | Generated names; storage outside served paths; type checks on content; size limits (Flask `MAX_CONTENT_LENGTH`; Django has no built-in maximum file size, so use a web server or proxy body limit such as nginx `client_max_body_size`, or a custom upload handler; `DATA_UPLOAD_MAX_MEMORY_SIZE` covers only non-file body data) |

## Authentication, authorization, and session

- **Django views without protection.** Function views missing `@login_required` or `@permission_required`; class views missing `LoginRequiredMixin` or `PermissionRequiredMixin`. Check the URL configuration for views exposed outside the intended prefix.
- **`@csrf_exempt`.** It disables CSRF on a cookie-authenticated view; justified only for webhook endpoints with their own signature checks.
- **DRF permissions.** `DEFAULT_PERMISSION_CLASSES` set to `AllowAny` (the default when unset), or views overriding `permission_classes = []`. Object-level checks only run if the view calls `get_object()` or `check_object_permissions`; a custom queryset that isn't filtered by `request.user` is an IDOR (CWE-639, API1).
- **Mass assignment (CWE-915).** A Django `ModelForm` or DRF `ModelSerializer` with `fields = "__all__"` exposes `is_staff`, `is_superuser`, and `owner`; use explicit `fields` plus `read_only_fields`. Pydantic models default to *ignoring* extra fields, but `model_config = ConfigDict(extra="allow")`, or spreading `**payload.dict()` into ORM constructors, reintroduces the problem.
- **Flask.** Routes without a `login_required`-style decorator; decorators applied in the wrong order (`@app.route` must be outermost); `SECRET_KEY` hard-coded or weak, which allows forging session cookies.
- **FastAPI.** Endpoints missing the `Depends(get_current_user)` dependency; routers included without router-level dependencies; OAuth2 scopes declared but not checked.
- **JWT.** PyJWT before 2.0 `jwt.decode` without `algorithms=[...]` (2.0+ raises an error); `algorithms` listing both HS* and RS* when verifying with a public key; `options={"verify_signature": False}`; no `audience` or `issuer` checks.
- **Sessions and cookies.** Django `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`; Flask `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`.
- **CORS.** `django-cors-headers` `CORS_ALLOW_ALL_ORIGINS = True` with `CORS_ALLOW_CREDENTIALS = True`; FastAPI `CORSMiddleware(allow_origins=["*"], allow_credentials=True)`, or `allow_origin_regex` set too broad.

## Language-specific issues

- **Unsafe deserialization is everywhere in data and ML code.** `pickle`, `joblib`, `torch.load`, and `numpy.load(allow_pickle=True)` on uploaded or downloaded files are RCE. This includes model files pulled from public hubs (OWASP LLM03 and LLM04).
- **`yaml.load` without `SafeLoader`,** and `eval` used as a config parser.
- **`subprocess` with `shell=True`,** and `os.system` in management commands that take arguments from users or tickets.
- **Jinja2 autoescape off.** A manually built `jinja2.Environment()` has autoescape **off** by default, unlike Flask's configured environment. Look for `Environment(` without `autoescape=select_autoescape(...)` rendering HTML.
- **`DEBUG = True` in production.** Django's debug page and the Werkzeug debugger (Flask `debug=True`) expose settings, and the Werkzeug console allows code execution.
- **`assert` used for security checks.** Asserts are stripped when Python runs with `-O`.
- **Celery.** Pickle serialization (`task_serializer="pickle"`, `accept_content` including pickle) on a broker that untrusted parties can reach is RCE.

## Configuration

- Django `settings.py` and environment-specific settings modules:
  - `DEBUG`, `ALLOWED_HOSTS = ["*"]`, `SECRET_KEY` committed
  - `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SECURE_PROXY_SSL_HEADER`
  - Cookie flags (see above), `CSRF_TRUSTED_ORIGINS`, `PASSWORD_HASHERS` order
  - Admin exposed at the default `/admin/` path with no extra protection
- Flask config: `DEBUG`, `SECRET_KEY`, `SESSION_COOKIE_*`, `MAX_CONTENT_LENGTH`.
- FastAPI: `docs_url` and `openapi_url` exposed in production, `debug=True`, exception handlers that return tracebacks.
- Celery: `broker_url` with embedded credentials, serializer settings.
- `.env` files and `config.py` modules containing secrets.

## Dependencies and build

- Read `requirements*.txt`, `constraints.txt`, `pyproject.toml`, `poetry.lock`, `uv.lock`, `Pipfile.lock`, `setup.cfg`, and `setup.py`.
- **Installing runs code.** `pip install` of a source distribution executes `setup.py` or build backends, and `pip-audit` on a project directory may build it. pip-audit's own docs warn: "If you wouldn't `pip install` it, you should not `pip audit` it." Prefer auditing pinned requirement or lock files, and ask before installing or building the project.
- Check for `--extra-index-url` (dependency confusion risk), packages from git URLs without commit pins, and unpinned dependencies in production requirements.

## Quick search patterns

These find candidates only; every hit still goes through `triage.md`.

```
execute\(\s*f["']|execute\(\s*["'].*%|\.raw\(|\.extra\(|RawSQL\(|text\(\s*f["']
os\.system\(|os\.popen\(|shell\s*=\s*True
\beval\(|\bexec\(|__import__\(|import_module\(
render_template_string\(|jinja2\.Template\(|Environment\(
mark_safe\(|\|\s*safe|autoescape off|Markup\(
pickle\.loads?\(|joblib\.load\(|torch\.load\(|allow_pickle\s*=\s*True|yaml\.load\(|jsonpickle
send_file\(|os\.path\.join\(.*request|extractall\(
requests\.(get|post)\(.*request\.|urlopen\(
redirect\(\s*request\.|HttpResponseRedirect\(
hashlib\.(md5|sha1)\(|random\.(random|randint|choice)\(|MODE_ECB|verify\s*=\s*False
csrf_exempt|AllowAny|fields\s*=\s*["']__all__["']|extra\s*=\s*["']allow["']
DEBUG\s*=\s*True|debug\s*=\s*True|ALLOWED_HOSTS\s*=\s*\[\s*["']\*["']
```
